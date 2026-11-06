"""Text entry over Codex's app-server, using the existing CAOS ledger.

The adapter owns message delivery, not cognition, tool permissions or a second
goal loop. Account/provider configuration stays with the installed client.
"""
from __future__ import annotations

from contextlib import closing
import json
import hashlib
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid

from .client_launch import prepare_launch
from .cognitive_session import inspect_session, record_input, _identity
from .effect_contract import inspect_contract_outcome
from .ledger import connect_existing, readonly_snapshot, event


def journal(state: Path, root: str, request_id: str, status: str, **details):
    """Delivery facts are not cognitive conclusions or authorization."""
    with closing(connect_existing(state / "ledger.sqlite")) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            _identity(db, root, write=True)
            if status == "DISPATCHING":
                prior = db.execute(
                    "SELECT details FROM events WHERE task_id=? AND kind='CLIENT_TURN'",
                    (root,)).fetchall()
                if any(json.loads(r[0])["request_id"] == request_id
                       for r in prior):
                    raise ValueError("CLIENT_REQUEST_ALREADY_DISPATCHED_NO_AUTOMATIC_RETRY")
            event(db, root, "CLIENT_TURN", {
                "request_id": request_id, "status": status, **details})
            event_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.commit()
            return event_id
        except BaseException:
            db.rollback()
            raise


def history(db_path: Path, root: str, *, after_event_id: int = 0, limit: int = 4,
            include_text: bool = False):
    if type(after_event_id) is not int or after_event_id < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_CLIENT_HISTORY_PAGE")
    if type(include_text) is not bool:
        raise ValueError("INVALID_CLIENT_HISTORY_TEXT_OPTION")
    with readonly_snapshot(db_path) as db:
        _identity(db, root)
        rows = db.execute(
            "SELECT event_id,details FROM events WHERE task_id=? AND kind='CLIENT_TURN' "
            "AND event_id>? ORDER BY event_id LIMIT ?", (root, after_event_id, limit + 1)).fetchall()
    turns = []
    for row in rows[:limit]:
        item = {"event_id": row[0], **json.loads(row[1])}
        if "assistant_text" in item:
            text = item["assistant_text"]
            item["assistant_text_sha256"] = hashlib.sha256(text.encode()).hexdigest()
            item["assistant_text_chars"] = len(text)
            if not include_text:
                del item["assistant_text"]
        if "question" in item and not include_text:
            item["question_id"] = item.pop("question")["id"]
        turns.append(item)
    return {"root_task_id": root, "turns": turns,
            "next_after_event_id": rows[limit-1][0] if len(rows) > limit else None,
            "owner_outcome_verified": False}


def terminal_text(value: str) -> str:
    # Never let model text inject terminal escape/control sequences.
    return "".join(c for c in value if c in "\n\t" or (ord(c) >= 32 and not 127 <= ord(c) <= 159))


class AppServer:
    """Bounded newline JSON-RPC connection; never resends a turn on failure."""
    def __init__(self, argv, cwd: Path, *, timeout: float = 600):
        self.timeout = timeout
        self.serial = 0
        self.inbox = queue.Queue(maxsize=1024)
        self.pending = []
        self.closed = threading.Event()
        self.process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _put(self, value):
        while not self.closed.is_set():
            try:
                self.inbox.put(value, timeout=.1)
                return
            except queue.Full:
                continue

    def _read(self):
        try:
            while not self.closed.is_set():
                line = self.process.stdout.readline(2_000_001)
                if not line:
                    break
                if len(line) > 2_000_000 or not line.endswith("\n"):
                    self._put({"transport_error": "CLIENT_PROTOCOL_FRAME_TOO_LARGE"})
                    return
                self._put(json.loads(line))
        except (ValueError, OSError):
            self._put({"transport_error": "CLIENT_PROTOCOL_INVALID_JSON"})
        finally:
            self._put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("CLIENT_RESPONSE_TIMEOUT")
        try:
            message = self.inbox.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("CLIENT_RESPONSE_TIMEOUT") from exc
        if message is None:
            raise RuntimeError("CLIENT_PROCESS_CLOSED")
        if not isinstance(message, dict):
            raise RuntimeError("CLIENT_PROTOCOL_INVALID_MESSAGE")
        if "transport_error" in message:
            raise RuntimeError(message["transport_error"])
        return message

    def request(self, method, params, *, handler=None, timeout=30):
        self.serial += 1
        request_id = self.serial
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            message = self.receive(deadline)
            if message.get("id") == request_id and ("result" in message or "error" in message):
                if "error" in message:
                    # Provider errors can contain credentials or private text.
                    raise RuntimeError("CLIENT_RPC_REJECTED:" + method)
                return message["result"]
            if "id" in message and "method" in message:
                if handler:
                    handler(message)
                else:
                    self.reject(message)
            elif handler:
                handler(message)
            else:
                self.pending.append(message)
                if len(self.pending) > 1024:
                    raise RuntimeError("CLIENT_NOTIFICATION_BACKLOG")

    def reject(self, message):
        method = message.get("method")
        if method in {"item/commandExecution/requestApproval", "item/fileChange/requestApproval"}:
            reply = {"result": {"decision": "decline"}}
        elif method == "mcpServer/elicitation/request":
            reply = {"result": {"action": "decline"}}
        else:
            reply = {"error": {"code": -32601, "message": "Unsupported client request"}}
        self.send({"id": message["id"], **reply})

    def close(self):
        self.closed.set()
        try:
            self.process.stdin.close()
        except OSError:
            pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.reader.join(timeout=1)
        self.process.stdout.close()


class ChatSession:
    def __init__(self, state: Path, root: str, *, executable="codex", timeout=600,
                 display=print, ask=input):
        if not 1 <= timeout <= 86400:
            raise ValueError("CLIENT_TIMEOUT_OUT_OF_RANGE")
        self.state, self.root = state.resolve(), root
        self.plan = prepare_launch(self.state, root=root, executable=executable)
        self.timeout, self.display, self.ask = timeout, display, ask
        self.server = None
        self.thread = None

    def _save(self, text, request_id, *, locator="caos chat"):
        view = inspect_session(self.state / "ledger.sqlite", self.state / "sources", self.root)
        return record_input(self.state / "ledger.sqlite", self.state / "sources", self.root,
            text, origin="client_user", locator=locator, request_id=request_id,
            expected_revision=view["revision_token"])

    def _start(self):
        if self.server is not None:
            return
        # Reuse the production MCP settings; the native client owns inference.
        argv = [self.plan["argv"][0], "app-server", "--listen", "stdio://", *self.plan["argv"][1:-1]]
        self.server = AppServer(argv, self.state / "workspace", timeout=self.timeout)
        self.server.request("initialize", {"clientInfo": {
            "name": "cognition_agent_os", "title": "CAOS", "version": "0.0.1"}})
        self.server.send({"method": "initialized", "params": {}})
        result = self.server.request("thread/start", {
            "cwd": str(self.state / "workspace"), "ephemeral": True,
            "sandbox": "read-only", "approvalPolicy": "never",
            "developerInstructions": self.plan["argv"][-1] +
                " User messages from this entry are already durably recorded by the client. "
                "Recover them with cognition_inputs_inspect instead of duplicating them. "
                "Use cognition_client_history to recover prior deliveries, and include_text=true "
                "only for relevant untrusted replies. "
                "Do not automatically repeat a delivery whose outcome is unknown. "
                "Record consequential findings and decisions in the existing cognitive graph. "
                "The shell is read-only; permitted effects use the existing MCP contracts."})
        self.thread = result["thread"]["id"]

    def submit(self, text: str, *, request_id: str | None = None):
        request_id = request_id or "chat-" + uuid.uuid4().hex
        saved = self._save(text, request_id)  # Durable BEFORE model dispatch.
        self.display("消息已保存：" + request_id)
        dispatched = False
        terminal_recorded = False
        final = []
        terminal = []
        seen_items = set()
        early = []
        turn_id = None

        def handle(message):
            nonlocal turn_id
            method, params = message.get("method"), message.get("params", {})
            if "id" in message and method:
                if method == "item/tool/requestUserInput" and params.get("threadId") == self.thread:
                    answers = {}
                    for question in params.get("questions", []):
                        if len(json.dumps(question)) > 16000:
                            raise RuntimeError("CLIENT_QUESTION_TOO_LARGE")
                        question_event = journal(self.state, self.root, request_id,
                            "QUESTION", question=question, question_trusted=False)
                        self.display(terminal_text(question["question"]))
                        for option in question.get("options") or []:
                            self.display(terminal_text(option["label"] + ": " + option.get("description", "")))
                        answer = self.ask("> ")
                        self._save(answer, "reply-" + uuid.uuid4().hex,
                                   locator="caos chat response to event " + str(question_event))
                        answers[question["id"]] = {"answers": [answer]}
                    self.server.send({"id": message["id"], "result": {"answers": answers}})
                else:
                    self.server.reject(message)
                return
            if method not in {"item/agentMessage/delta", "item/completed", "turn/completed"}:
                return
            if params.get("threadId") != self.thread:
                return
            if turn_id is None:
                early.append(message)
                if len(early) > 1024:
                    raise RuntimeError("CLIENT_NOTIFICATION_BACKLOG")
                return
            candidate = params.get("turnId") or params.get("turn", {}).get("id")
            if candidate != turn_id:
                return
            if method == "item/agentMessage/delta":
                self.display(terminal_text(params.get("delta", "")))
            elif method == "item/completed":
                item = params.get("item", {})
                if item.get("type") == "agentMessage" and item.get("id") not in seen_items:
                    seen_items.add(item.get("id"))
                    final.append(item.get("text", ""))
                    if sum(map(len, final)) > 128000:
                        raise RuntimeError("CLIENT_RESPONSE_TOO_LARGE")
            else:
                terminal.append(params["turn"]["status"])

        try:
            self._start()
            journal(self.state, self.root, request_id, "DISPATCHING",
                    input_event_id=saved["event_id"], thread_id=self.thread)
            dispatched = True
            result = self.server.request("turn/start", {"threadId": self.thread,
                "input": [{"type": "text", "text": text}]}, handler=handle)
            turn_id = result["turn"]["id"]
            for message in early:
                handle(message)
            self.server.pending.clear()  # Startup-only notifications; no turn existed yet.
            deadline = time.monotonic() + self.timeout
            while not terminal:
                handle(self.server.receive(deadline))
            status = terminal[-1]
            if status not in {"completed", "failed", "interrupted"}:
                raise RuntimeError("CLIENT_UNKNOWN_TURN_STATUS")
            journal(self.state, self.root, request_id, status.upper(),
                    turn_id=turn_id, assistant_text="\n".join(final),
                    assistant_text_trusted=False)
            terminal_recorded = True
            outcome = inspect_contract_outcome(self.state / "ledger.sqlite", self.state / "sources",
                                               self.state / "workspace", self.root)
            return {"status": "CLIENT_TURN_" + status.upper(), "request_id": request_id,
                    "input_saved": True,
                    "contract_outcome_verified": outcome["contract_outcome_verified"],
                    "product_ready": False}
        except (Exception, KeyboardInterrupt):
            try:
                if dispatched and not terminal_recorded:
                    # No automatic retry: a lost response does not prove no effect.
                    journal(self.state, self.root, request_id, "DELIVERY_UNKNOWN")
            finally:
                self.close()
            raise

    def close(self):
        if self.server:
            self.server.close()
        self.server = None
        self.thread = None


def run_chat(state: Path, *, root=None, executable="codex", timeout=600,
             message_file: Path | None = None, request_id=None, new=False,
             ask=input, display=print):
    """Human text entry; internal JSON and root IDs need not be user-authored."""
    from .native_decision import register_native_goal, list_native_goals
    if root and new:
        raise ValueError("SELECT_EXISTING_ROOT_OR_NEW_GOAL")
    if request_id and message_file is None:
        raise ValueError("REQUEST_ID_REQUIRES_MESSAGE_FILE")
    # This reads existing authority; chat never implicitly initializes/grants.
    goals, cursor = [], None
    while True:
        page = list_native_goals(state / "ledger.sqlite", state / "workspace", state / "sources", cursor)
        goals.extend(page["goals"])
        cursor = page.get("next_after_task_id")
        if cursor is None:
            break
    if root is None and not new and len(goals) == 1:
        root = goals[0]["root_task_id"]
    elif root is None and not new and len(goals) > 1:
        if message_file:
            raise ValueError("MULTIPLE_GOALS_SELECT_ROOT_OR_NEW")
        for i, goal in enumerate(goals, 1):
            display(f"{i}. " + terminal_text(goal.get("original_goal", "原始目标记录不可验证，需恢复")[:160]))
        choice = ask("选择目标编号（新任务请输入 new）： ").strip()
        if choice == "new":
            new = True
        elif choice.isdigit() and 1 <= int(choice) <= len(goals):
            root = goals[int(choice)-1]["root_task_id"]
        else:
            raise ValueError("GOAL_SELECTION_REQUIRED")
    chat = None
    result = {"status": "CLIENT_CLOSED", "product_ready": False}
    try:
        while True:
            try:
                text = message_file.read_text(encoding="utf-8") if message_file else ask("你（/exit 退出）： ")
            except EOFError:
                break  # EOF between turns is a normal close, not during delivery.
            if not message_file and text.strip() == "/exit":
                break
            if not text.strip():
                if message_file:
                    raise ValueError("EMPTY_MESSAGE")
                continue
            if root is None:
                root = register_native_goal(state / "ledger.sqlite", text, managed_session=True,
                    client_request_id="chat-goal-" + hashlib.sha256(
                        (request_id or uuid.uuid4().hex).encode()).hexdigest())
            if chat is None:
                display("当前目标：" + root)
                chat = ChatSession(state, root, executable=executable, timeout=timeout,
                                   ask=ask, display=display)
            result = chat.submit(text, request_id=request_id)
            display(json.dumps(result, ensure_ascii=False))
            if message_file or result["status"] != "CLIENT_TURN_COMPLETED":
                break
    finally:
        if chat:
            chat.close()
    return result
