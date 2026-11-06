"""Delivery invariants using a real subprocess protocol peer, not a model eval."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from cognition_agent_os import client_chat
from cognition_agent_os.cognitive_session import inspect_inputs, inspect_session
from cognition_agent_os.native_decision import register_native_goal
from cognition_agent_os.session_cli import provision


PEER = r'''
import json, sys, sqlite3
from pathlib import Path
# JSON-RPC is UTF-8 even when the Windows console uses a legacy code page.
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
state, mode, root = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
goal = json.loads((state/'native-goal.json').read_text()) if mode.startswith('goal_resume') else None
activated = False
def emit(value):
    print(json.dumps(value), flush=True)
def notify(method, params):
    emit({'method':method, 'params':params})
for line in sys.stdin:
    msg=json.loads(line)
    method=msg.get('method')
    if method=='initialize':
        if mode=='startup_failure': sys.exit(4)
        emit({'id':msg['id'], 'result':{'userAgent':'test-peer'}})
    elif method=='thread/start':
        assert msg['params']['sandbox']=='read-only'
        assert msg['params']['approvalPolicy']=='never'
        assert msg['params']['ephemeral'] is (not mode.startswith('goal_'))
        emit({'id':msg['id'], 'result':{'thread':{'id':'thread-1'}}})
    elif method=='thread/read':
        emit({'id':msg['id'],'result':{'thread':{'id':'thread-1','cwd':str(state/('wrong' if mode=='goal_resume_wrong_workspace' else 'workspace'))}}})
    elif method=='thread/resume':
        assert goal['status']=='paused'
        with sqlite3.connect(state/'ledger.sqlite') as db:
            deliveries=[json.loads(r[0]) for r in db.execute("SELECT details FROM events WHERE task_id=? AND kind='CLIENT_TURN'",(root,))]
            assert deliveries[-1]['status']=='DISPATCHING' and deliveries[-1]['native_resume']
        assert goal['tokensUsed']==4000
        (state/'resume-observed.json').write_text(json.dumps(goal))
        emit({'id':msg['id'],'result':{'thread':{'id':'thread-1'}}})
    elif method=='thread/goal/set':
        p=msg['params']
        if p['status']=='paused':
            if goal is None:
                assert root in p['objective']
                goal={'status':'paused','tokenBudget':p['tokenBudget'],'objective':p['objective'],'tokensUsed':0,'createdAt':123}
            else:
                goal['status']='paused'
                if 'tokenBudget' in p:goal['tokenBudget']=p['tokenBudget']
                (state/'paused-on-close').write_text('paused')
            emit({'id':msg['id'],'result':{'goal':goal}})
            notify('thread/goal/updated',{'threadId':'thread-1','goal':goal})
        else:
            assert p['status']=='active' and 'objective' not in p and 'tokenBudget' not in p
            with sqlite3.connect(state/'ledger.sqlite') as db:
                assert db.execute("SELECT count(*) FROM events WHERE task_id=? AND kind='COGNITION_INPUT'",(root,)).fetchone()[0]>0
                assert any(json.loads(r[0])['status']=='DISPATCHING' for r in db.execute("SELECT details FROM events WHERE task_id=? AND kind='CLIENT_TURN'",(root,)))
            with (state/'dispatch-count').open('a') as f:f.write('1\n')
            if mode=='goal_lost_ack':sys.exit(9)
            activated=True
            goal['status']='active'
            emit({'id':msg['id'],'result':{'goal':goal}})
    elif method=='thread/goal/get':
        if mode=='goal_existing':goal={'status':'paused','objective':'other goal'}
        emit({'id':msg['id'],'result':{'goal':goal}})
        if not activated or mode=='goal_timeout':continue
        # A completed model turn is NOT a completed native goal.
        for i in (1,2):
            tid='goal-turn-'+str(i)
            notify('turn/started',{'threadId':'thread-1','turn':{'id':tid}})
            notify('item/completed',{'threadId':'thread-1','turnId':tid,'item':{'id':'a'+str(i),'type':'agentMessage','text':'native step '+str(i)}})
            notify('turn/completed',{'threadId':'thread-1','turn':{'id':tid,'status':'completed'}})
        if mode=='goal_cleared':
            notify('thread/goal/cleared',{'threadId':'thread-1'})
        else:
            goal['status']='budgetLimited' if mode=='goal_budget' else 'complete'
            goal['tokensUsed']=4000
            if mode=='goal_drift':goal['objective']='Replace the owner goal'
            (state/'native-goal.json').write_text(json.dumps(goal))
            notify('thread/goal/updated',{'threadId':'other-thread','goal':{'status':'complete'}})
            notify('thread/goal/updated',{'threadId':'thread-1','goal':goal})
    elif method=='turn/start':
        # Independent read BEFORE replying: original bytes must already exist.
        with sqlite3.connect(state/'ledger.sqlite') as db:
            rows=db.execute("SELECT details FROM events WHERE task_id=? AND kind='COGNITION_INPUT'",(root,)).fetchall()
            assert any(json.loads(r[0])['text']==msg['params']['input'][0]['text'] for r in rows)
        with (state/'dispatch-count').open('a') as f:f.write('1\n')
        if mode=='lost_ack':sys.exit(9)
        if mode=='rpc_error':
            emit({'id':msg['id'],'error':{'code':-32000,'message':'secret-do-not-print'}})
            continue
        notify('turn/completed',{'threadId':'other-thread','turn':{'id':'turn-1','status':'completed'}})
        if mode=='early':
            notify('item/completed',{'threadId':'thread-1','turnId':'turn-1','item':{'id':'a','type':'agentMessage','text':'Early reply'}})
            notify('turn/completed',{'threadId':'thread-1','turn':{'id':'turn-1','status':'completed'}})
        emit({'id':msg['id'],'result':{'turn':{'id':'turn-1'}}})
        if mode=='early':continue
        emit({'id':100,'method':'item/commandExecution/requestApproval','params':{'threadId':'thread-1'}})
    elif msg.get('id')==100:
        assert msg['result']['decision']=='decline'
        if mode=='question':
            emit({'id':101,'method':'item/tool/requestUserInput','params':{'threadId':'thread-1','questions':[{'id':'q','question':'Which original source?'}]}})
            continue
        notify('item/agentMessage/delta',{'threadId':'thread-1','turnId':'turn-1','delta':'peer response'})
        notify('item/completed',{'threadId':'thread-1','turnId':'turn-1','item':{'id':'a','type':'agentMessage','text':'Unverified proposal'}})
        notify('turn/completed',{'threadId':'thread-1','turn':{'id':'turn-1','status':'failed' if mode=='failed' else 'completed'}})
    elif msg.get('id')==101:
        with sqlite3.connect(state/'ledger.sqlite') as db:
            rows=db.execute("SELECT details FROM events WHERE task_id=? AND kind='COGNITION_INPUT'",(root,)).fetchall()
            assert any(json.loads(r[0])['text']=='use the original' for r in rows)
        assert msg['result']['answers']['q']['answers']==['use the original']
        notify('turn/completed',{'threadId':'thread-1','turn':{'id':'turn-1','status':'completed'}})
'''


class ClientChat(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = provision(self.base / "私有 state")
        self.root = register_native_goal(self.state / "ledger.sqlite", "完整目标不能被临时建议替换",
            managed_session=True, client_request_id="chat-goal-test-0001")
        self.peer = self.base / "peer.py"
        self.peer.write_text(PEER, encoding="utf-8")
        self.outputs = []

    def chat(self, mode="normal", *, goal_budget=None, resume_client=None):
        with patch("cognition_agent_os.client_launch.importlib.util.find_spec", return_value=object()):
            chat = client_chat.ChatSession(self.state, self.root, executable=sys.executable,
                timeout=3, display=self.outputs.append, ask=lambda _: "use the original",
                goal_budget=goal_budget or (4000 if mode.startswith("goal_") else None),
                resume_client=resume_client)
        self.addCleanup(chat.close)
        real = client_chat.AppServer
        def peer(argv, cwd, **kw):
            self.assertEqual(argv[1:4], ["app-server", "--listen", "stdio://"])
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", argv)
            if mode.startswith("goal_"):
                self.assertIn("max_goal_token_budget=" + str(goal_budget or 4000), argv)
            return real([sys.executable, str(self.peer), str(self.state), mode, self.root], cwd, **kw)
        return chat, patch("cognition_agent_os.client_chat.AppServer", side_effect=peer)

    def test_original_message_is_committed_before_dispatch_and_reply_is_not_truth(self):
        chat, mock = self.chat()
        text = '暂时看看 Graph。不要改目标，也不要删除历史。\n含 "引号" 与 $shell。'
        with mock:
            result = chat.submit(text, request_id="request-1")
        self.assertEqual(result["status"], "CLIENT_TURN_COMPLETED")
        self.assertFalse(result["contract_outcome_verified"])
        self.assertFalse(result["product_ready"])
        saved = inspect_inputs(self.state / "ledger.sqlite", self.state / "sources", self.root)
        self.assertEqual(saved["inputs"][0]["text"], text)
        self.assertEqual(inspect_session(self.state / "ledger.sqlite", self.state / "sources", self.root)["goal_revision"], 0)
        turns = client_chat.history(self.state / "ledger.sqlite", self.root)["turns"]
        self.assertEqual([t["status"] for t in turns], ["DISPATCHING", "COMPLETED"])
        self.assertFalse(turns[-1]["assistant_text_trusted"])

    def test_lost_ack_cannot_automatically_resend_same_request(self):
        chat, mock = self.chat("lost_ack")
        with mock:
            with self.assertRaisesRegex(RuntimeError, "CLIENT_PROCESS_CLOSED"):
                chat.submit("原话保留", request_id="request-lost")
            with self.assertRaisesRegex(ValueError, "ALREADY_DISPATCHED"):
                chat.submit("原话保留", request_id="request-lost")
        self.assertEqual((self.state / "dispatch-count").read_text().splitlines(), ["1"])
        turns = client_chat.history(self.state / "ledger.sqlite", self.root)["turns"]
        self.assertEqual(turns[-1]["status"], "DELIVERY_UNKNOWN")

    def test_connection_failure_preserves_input_without_claiming_dispatch(self):
        chat, mock = self.chat("startup_failure")
        with mock:
            with self.assertRaisesRegex(RuntimeError, "CLIENT_PROCESS_CLOSED"):
                chat.submit("不要丢失这个纠正", request_id="startup-1")
        self.assertEqual(inspect_inputs(self.state / "ledger.sqlite", self.state / "sources", self.root)["input_count"], 1)
        self.assertFalse((self.state / "dispatch-count").exists())
        self.assertEqual(client_chat.history(self.state / "ledger.sqlite", self.root)["turns"], [])

    def test_early_notifications_and_other_thread_cannot_false_complete(self):
        chat, mock = self.chat("early")
        with mock:
            result = chat.submit("original", request_id="early-1")
        self.assertEqual(result["status"], "CLIENT_TURN_COMPLETED")
        self.assertNotIn("assistant_text", client_chat.history(self.state / "ledger.sqlite", self.root)["turns"][-1])
        self.assertEqual(client_chat.history(self.state / "ledger.sqlite", self.root, include_text=True)["turns"][-1]["assistant_text"], "Early reply")

    def test_failed_turn_is_not_success(self):
        chat, mock = self.chat("failed")
        with mock:
            result = chat.submit("original", request_id="failed-1")
        self.assertEqual(result["status"], "CLIENT_TURN_FAILED")

    def test_clarification_is_saved_before_answer_forwarded(self):
        chat, mock = self.chat("question")
        with mock:
            chat.submit("original", request_id="question-1")
        inputs = inspect_inputs(self.state / "ledger.sqlite", self.state / "sources", self.root)["inputs"]
        self.assertEqual([i["text"] for i in inputs], ["original", "use the original"])
        self.assertIn("response to event", inputs[1]["locator"])
        transcript = client_chat.history(self.state / "ledger.sqlite", self.root, include_text=True)
        self.assertEqual(transcript["turns"][1]["question"]["question"], "Which original source?")

    def test_rpc_error_is_bounded_and_does_not_expose_private_payload(self):
        chat, mock = self.chat("rpc_error")
        with mock:
            with self.assertRaisesRegex(RuntimeError, "CLIENT_RPC_REJECTED:turn/start") as exc:
                chat.submit("original", request_id="rpc-1")
        self.assertNotIn("secret", str(exc.exception))

    def test_cold_history_pagination_and_root_isolation(self):
        client_chat.journal(self.state, self.root, "one", "DISPATCHING")
        client_chat.journal(self.state, self.root, "one", "DELIVERY_UNKNOWN")
        other = register_native_goal(self.state / "ledger.sqlite", "另一个目标", managed_session=True,
                                     client_request_id="other-goal-test-0001")
        first = client_chat.history(self.state / "ledger.sqlite", self.root, limit=1)
        second = client_chat.history(self.state / "ledger.sqlite", self.root,
                                     after_event_id=first["next_after_event_id"], limit=1)
        self.assertEqual(second["turns"][0]["status"], "DELIVERY_UNKNOWN")
        self.assertEqual(client_chat.history(self.state / "ledger.sqlite", other)["turns"], [])

    def test_terminal_output_strips_controls(self):
        self.assertNotIn("\x1b", client_chat.terminal_text("\x1b[2Jclear\x00"))

    def test_plain_text_file_routes_without_user_authored_json(self):
        file = self.base / "message.txt"
        file.write_text("这是新的建议，不覆盖完整目标。", encoding="utf-8")
        chat, mock = self.chat()
        with mock, patch("cognition_agent_os.client_chat.ChatSession", return_value=chat):
            result = client_chat.run_chat(self.state, message_file=file, request_id="file-1",
                                         display=self.outputs.append)
        self.assertEqual(result["status"], "CLIENT_TURN_COMPLETED")
        original = inspect_session(self.state / "ledger.sqlite", self.state / "sources", self.root)["goal"]["original"]
        self.assertEqual(original, "完整目标不能被临时建议替换")

    def test_multiple_goals_do_not_silently_choose_newest(self):
        register_native_goal(self.state / "ledger.sqlite", "Distinct goal", managed_session=True,
                             client_request_id="another-goal-0001")
        file = self.base / "message.txt"
        file.write_text("continue", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "MULTIPLE_GOALS"):
            client_chat.run_chat(self.state, message_file=file)
        self.assertEqual(inspect_inputs(self.state / "ledger.sqlite", self.state / "sources", self.root)["input_count"], 0)

    def test_eof_during_clarification_does_not_turn_unknown_delivery_into_success(self):
        chat, mock = self.chat("question")
        def eof(_):
            raise EOFError("INPUT_CLOSED_DURING_TURN")
        chat.ask = eof
        with mock, self.assertRaises(EOFError):
            chat.submit("original", request_id="eof-1")
        self.assertEqual(client_chat.history(self.state / "ledger.sqlite", self.root)["turns"][-1]["status"], "DELIVERY_UNKNOWN")

    def test_native_goal_keeps_listening_across_completed_turns(self):
        chat, peer = self.chat("goal_complete")
        with peer:
            result = chat.submit("Continue the whole goal", request_id="loop-1")
        self.assertEqual(result["status"], "CLIENT_GOAL_COMPLETE")
        self.assertFalse(result["contract_outcome_verified"])
        self.assertFalse(result["product_ready"])
        events = client_chat.history(self.state / "ledger.sqlite", self.root, limit=20, include_text=True)["turns"]
        self.assertEqual([e["status"] for e in events],
                         ["DISPATCHING", "NATIVE_TURN_ENDED", "NATIVE_TURN_ENDED", "GOAL_COMPLETE"])
        self.assertEqual(events[-1]["assistant_text"], "native step 1\nnative step 2")
        self.assertEqual((self.state / "dispatch-count").read_text().splitlines(), ["1"])
        with self.assertRaisesRegex(ValueError, "INVOCATION_ALREADY_USED"):
            chat.submit("Continue again", request_id="loop-2")

    def test_native_budget_limit_does_not_claim_goal_completion(self):
        chat, peer = self.chat("goal_budget")
        with peer:
            result = chat.submit("Continue", request_id="budget-1")
        self.assertEqual(result["status"], "CLIENT_GOAL_BUDGETLIMITED")
        self.assertFalse(result["contract_outcome_verified"])

    def test_native_goal_activation_lost_ack_is_not_retried(self):
        chat, peer = self.chat("goal_lost_ack")
        with peer, self.assertRaisesRegex(RuntimeError, "CLIENT_PROCESS_CLOSED"):
            chat.submit("Continue", request_id="goal-lost-1")
        self.assertEqual(client_chat.history(self.state / "ledger.sqlite", self.root)["turns"][-1]["status"], "DELIVERY_UNKNOWN")
        self.assertEqual((self.state / "dispatch-count").read_text().splitlines(), ["1"])

    def test_native_goal_timeout_requests_pause_and_preserves_unknown(self):
        chat, peer = self.chat("goal_timeout")
        chat.timeout = 1
        with peer, self.assertRaises(TimeoutError):
            chat.submit("Continue", request_id="goal-timeout-1")
        self.assertTrue((self.state / "paused-on-close").exists())
        self.assertEqual(client_chat.history(self.state / "ledger.sqlite", self.root)["turns"][-1]["status"], "DELIVERY_UNKNOWN")

    def test_existing_native_goal_is_never_overwritten(self):
        chat, peer = self.chat("goal_existing")
        with peer, self.assertRaisesRegex(RuntimeError, "EXISTING_GOAL"):
            chat.submit("Continue", request_id="goal-existing-1")
        self.assertFalse((self.state / "dispatch-count").exists())

    def test_cleared_native_goal_is_not_success(self):
        chat, peer = self.chat("goal_cleared")
        with peer, self.assertRaisesRegex(RuntimeError, "GOAL_CLEARED"):
            chat.submit("Continue", request_id="goal-cleared-1")
        events = client_chat.history(self.state / "ledger.sqlite", self.root, limit=20)["turns"]
        self.assertEqual(events[-1]["status"], "DELIVERY_UNKNOWN")

    def test_native_goal_replacement_does_not_replace_caos_goal(self):
        chat, peer = self.chat("goal_drift")
        with peer, self.assertRaisesRegex(RuntimeError, "BINDING_CHANGED"):
            chat.submit("Continue", request_id="goal-drift-1")
        view = inspect_session(self.state / "ledger.sqlite", self.state / "sources", self.root)
        self.assertEqual(view["goal"]["original"], "完整目标不能被临时建议替换")
        self.assertEqual(view["goal_revision"], 0)

    def test_cold_native_resume_preserves_thread_objective_and_used_budget(self):
        first, peer = self.chat("goal_budget")
        with peer:
            first.submit("Start", request_id="resume-first")
        first.close()
        second, peer = self.chat("goal_resume", goal_budget=8000, resume_client="auto")
        with peer:
            result = second.submit("Continue existing work", request_id="resume-second")
        self.assertEqual(result["status"], "CLIENT_GOAL_COMPLETE")
        observed = json.loads((self.state / "resume-observed.json").read_text())
        self.assertEqual(observed["tokensUsed"], 4000)
        self.assertEqual(observed["tokenBudget"], 8000)
        self.assertEqual(observed["createdAt"], 123)
        self.assertEqual((self.state / "dispatch-count").read_text().splitlines(), ["1", "1"])
        self.assertEqual(client_chat.resumable_thread(self.state, self.root, "auto"), "thread-1")

    def test_used_budget_refuses_activation_without_destroying_resumability(self):
        first, peer = self.chat("goal_budget")
        with peer:
            first.submit("Start", request_id="budget-first")
        first.close()
        second, peer = self.chat("goal_resume", goal_budget=4000, resume_client="auto")
        with peer, self.assertRaisesRegex(ValueError, "BUDGET_ALREADY_USED"):
            second.submit("Continue", request_id="budget-second")
        self.assertEqual(client_chat.resumable_thread(self.state, self.root, "auto"), "thread-1")
        self.assertFalse((self.state / "resume-observed.json").exists())
        self.assertEqual(inspect_inputs(self.state / "ledger.sqlite", self.state / "sources", self.root)["input_count"], 2)

    def test_resume_rejects_wrong_workspace_before_native_mutation(self):
        first, peer = self.chat("goal_budget")
        with peer:
            first.submit("Start", request_id="workspace-first")
        first.close()
        before = (self.state / "native-goal.json").read_bytes()
        second, peer = self.chat("goal_resume_wrong_workspace", goal_budget=8000, resume_client="thread-1")
        with peer, self.assertRaisesRegex(RuntimeError, "WORKSPACE_MISMATCH"):
            second.submit("Continue", request_id="workspace-second")
        self.assertEqual((self.state / "native-goal.json").read_bytes(), before)
        self.assertFalse((self.state / "resume-observed.json").exists())

    def test_unknown_delivery_and_other_root_are_not_native_resume_candidates(self):
        first, peer = self.chat("goal_lost_ack")
        with peer, self.assertRaises(RuntimeError):
            first.submit("Start", request_id="unknown-resume")
        with self.assertRaisesRegex(ValueError, "RECONCILIATION"):
            client_chat.resumable_thread(self.state, self.root, "thread-1")
        other = register_native_goal(self.state / "ledger.sqlite", "Different goal", managed_session=True,
                                     client_request_id="resume-other-goal-0001")
        with self.assertRaisesRegex(ValueError, "NOT_BOUND"):
            client_chat.resumable_thread(self.state, other, "thread-1")

    def test_resume_does_not_choose_the_latest_of_multiple_native_threads(self):
        for i in (1,2):
            client_chat.journal(self.state, self.root, str(i), "DISPATCHING", thread_id="thread-"+str(i), goal_budget=4000)
            client_chat.journal(self.state, self.root, str(i), "GOAL_PAUSED")
        with self.assertRaisesRegex(ValueError, "SELECT_ONE"):
            client_chat.resumable_thread(self.state, self.root, "auto")
        self.assertEqual(client_chat.resumable_thread(self.state, self.root, "thread-1"), "thread-1")

    def test_resume_cannot_create_a_parallel_new_goal(self):
        with self.assertRaisesRegex(ValueError, "EXISTING_GOAL"):
            client_chat.run_chat(self.state, new=True, resume_client="auto", goal_budget=8000,
                                 ask=lambda _: self.fail("Must reject before asking for a new task"))


if __name__ == "__main__":
    unittest.main()
