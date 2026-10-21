"""P32 external APScheduler #1116 FULL ORIGINAL WHEEL, TWO ORIGINAL MODULES.

Read-only, non-root, no-network Docker executes genuine 4.0.0a6 APScheduler
and pinned real dependencies. The two reported KeyError sinks are probed via
real instances, events, datastore methods and async executor, not AST stubs.
Model phase separately opt-in, never auto-run with normal CI.
"""
from __future__ import annotations
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import zipfile

ISSUE="https://github.com/agronholm/apscheduler/issues/1116"
PACKAGES={
    "APScheduler":"4.0.0a6",
    "anyio":"4.9.0","attrs":"25.3.0","tenacity":"9.1.2",
    "tzlocal":"5.3.1","idna":"3.10","sniffio":"1.3.1",
    "typing_extensions":"4.13.2",
}
WHEEL_SHA256={
    "anyio-4.9.0-py3-none-any.whl":"9f76d541cad6e36af7beb62e978876f3b41e3e04f2c1fbf0884604c0a9c4d93c",
    "apscheduler-4.0.0a6-py3-none-any.whl":"87031f7537aaa6ea2d3e69fdd9454b641f18938fc8cd0c589972006eceba8ee9",
    "attrs-25.3.0-py3-none-any.whl":"427318ce031701fea540783410126f03899a97ffc6f61596ad581ac2e40e3bc3",
    "idna-3.10-py3-none-any.whl":"946d195a0d259cbba61165e88e65941f16e9b36ea6ddb97f00452bae8b1287d3",
    "sniffio-1.3.1-py3-none-any.whl":"2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2",
    "tenacity-9.1.2-py3-none-any.whl":"f77bf36710d8b73a50b2dd155c97b870017ad21afe6ab300326b0371b3b05138",
    "typing_extensions-4.13.2-py3-none-any.whl":"a439e7c04b49fec3e5d3e2beaa21755cadbbdc391694e28ccdd36ca4a1408f8c",
    "tzlocal-5.3.1-py3-none-any.whl":"eb1a66c3ef5847adf7a834f1be0800581b683b5608e74f86ecbcef8ab91bb85d",
}
SOURCE_PATHS=(
    "apscheduler/datastores/memory.py",
    "apscheduler/_schedulers/async_.py",
)
SOURCE_GIT_BLOBS=(
    "1c3ecccee81d5ed967eb9d81b8380fcdd450c1cf",
    "b9bd4d02ec3581c218e8a639d7cf3e6fe12441c6",
)
UPSTREAM_REF="4.0.0a6"
IMAGE="python:3.12-alpine"
PUBLIC=[
    {"input":{"case":"memory_single"},"expected":{"safe":True}},
    {"input":{"case":"memory_duplicate"},"expected":{"safe":True}},
    {"input":{"case":"scheduler_tracked"},"expected":{"safe":True}},
    {"input":{"case":"scheduler_removed"},"expected":{"safe":True}},
]
HIDDEN=[
    {"input":{"case":"memory_duplicate","task_id":"p32:held_one",
              "result_retention_s":45},"expected":{"safe":True}},
    {"input":{"case":"memory_duplicate","task_id":"p32:held_two",
              "result_kind":"error"},"expected":{"safe":True}},
    {"input":{"case":"memory_duplicate","task_id":"p32:held_three",
              "result_retention_s":180,"result_kind":"error"},"expected":{"safe":True}},
    {"input":{"case":"memory_single","task_id":"p32:held_four",
              "result_retention_s":30},"expected":{"safe":True}},
    {"input":{"case":"scheduler_removed","task_id":"p32:held_five",
              "fail_job":True},"expected":{"safe":True}},
    {"input":{"case":"scheduler_removed","task_id":"p32:held_six",
              "result_retention_s":45},"expected":{"safe":True}},
    {"input":{"case":"scheduler_tracked","task_id":"p32:held_seven",
              "fail_job":True},"expected":{"safe":True}},
    {"input":{"case":"scheduler_removed","task_id":"p32:held_eight",
              "missing_executor":True},"expected":{"safe":True}},
]
GOAL=(
    "Fix the REAL APScheduler 4.0.0a6 memory lease-duplicate completion "
    "bug #1116. The first release may have removed a job from MemoryDataStore "
    "when its lease is re-acquired and the same job completes twice: a second "
    "release must not throw KeyError, remove another job or decrement "
    "Task.running_jobs again. AsyncScheduler._run_job must not throw "
    "KeyError if the same job was already removed from its _running_jobs "
    "set; normal tracked jobs still finish cleanly. Modify BOTH original "
    "apscheduler/datastores/memory.py and "
    "apscheduler/_schedulers/async_.py. Preserve the original package "
    "imports and API; do not modify the JSON probe or independent gold."
)
# Public, hidden strings and inputs frozen before first model attempt. The
# hidden cases are replayed with separate original fresh objects; this is not
# a broad distribution or maintainer acceptance, explicitly record limitation.

PROBE = r'''
import asyncio
import json
import os
import sys
from pathlib import Path

for wheel in sorted(Path("/app").glob("*.whl")):
    sys.path.insert(0,str(wheel))

from apscheduler import AsyncScheduler
from apscheduler._enums import JobOutcome
from apscheduler._structures import Task,Job,JobResult

def seed(scheduler,request):
    from datetime import timedelta
    data=scheduler.data_store
    task=Task(id=request.get("task_id","p32:real_task"),
              func="p32:real_task",job_executor="async",running_jobs=1)
    job=Job(task_id=task.id,executor="async",
            result_expiration_time=timedelta(
                seconds=request.get("result_retention_s",0)),
            acquired_by=scheduler.identity)
    data._tasks[task.id]=task
    data._jobs_by_id[job.id]=job
    data._jobs_by_task_id[job.task_id].add(job)
    return data,task,job

async def check(data):
    case=data["case"]
    async with AsyncScheduler() as scheduler:
        store,task,job=seed(scheduler,data)
        if case.startswith("memory_"):
            if data.get("result_kind")=="error":
                result=JobResult.from_job(job,JobOutcome.error,
                    exception=ValueError("private-case sentinel"))
            else:
                result=JobResult.from_job(job,JobOutcome.success)
            await store.release_job(scheduler.identity,job,result)
            if case=="memory_duplicate":
                await store.release_job(scheduler.identity,job,result)
            should_retain=data.get("result_retention_s",0)>0
            return {"safe":(
                task.running_jobs==0
                and job.id not in store._jobs_by_id
                and task.id not in store._jobs_by_task_id
                and (job.id in store._job_results)==should_retain)}
        if case.startswith("scheduler_"):
            scheduler._running_jobs.add(job)
            if data.get("missing_executor"):
                scheduler._running_jobs.discard(job)
            async def fn():
                if case=="scheduler_removed":
                    scheduler._running_jobs.discard(job)
                if data.get("fail_job"):
                    raise ValueError("private-case sentinel")
                return 17
            await scheduler._run_job(job,fn,
                "unavailable" if data.get("missing_executor") else "async")
            if data.get("missing_executor"):
                return {"safe":(
                    not scheduler._running_jobs
                    and task.running_jobs==1
                    and job.id in store._jobs_by_id)}
            return {"safe":(
                not scheduler._running_jobs
                and task.running_jobs==0
                and job.id not in store._jobs_by_id)}
        return {"safe":False}

try:
    request=json.load(sys.stdin)
    actual=asyncio.run(check(request))
except BaseException as exc:
    actual={"safe":False,"error":type(exc).__name__}
print(json.dumps(actual,sort_keys=True))
'''
def sha(raw:bytes)->str:return hashlib.sha256(raw).hexdigest()
def git_blob_sha(raw:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
def _manifest()->str:
    payload={"issue":ISSUE,"versions":PACKAGES,"wheels":WHEEL_SHA256,
             "git_blobs":SOURCE_GIT_BLOBS,"goal":GOAL,
             "public":PUBLIC,"hidden":HIDDEN,"probe_sha256":sha(PROBE.encode())}
    return sha(json.dumps(payload,sort_keys=True,separators=(",",":")).encode())

def _wheels(root:Path)->tuple[dict[str,bytes],str,dict[str,bytes]]:
    roots=list(root.glob("*.whl"))
    if len(roots)!=len(WHEEL_SHA256) or {x.name for x in roots}!=set(WHEEL_SHA256):
        raise RuntimeError("Expected exact pinned real dependency wheels")
    wheel_bytes={}
    package_wheel=None
    original={}
    for file in roots:
        data=file.read_bytes()
        if sha(data)!=WHEEL_SHA256[file.name]:
            raise RuntimeError("Published real wheel SHA256 changed")
        if not data or file.name in wheel_bytes:
            raise RuntimeError("Missing real upstream wheel")
        wheel_bytes[file.name]=data
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names=set(z.namelist())
            if set(SOURCE_PATHS).issubset(names):
                if package_wheel is not None:raise RuntimeError("Ambiguous upstream wheel")
                package_wheel=file.name
                original={path:z.read(path) for path in SOURCE_PATHS}
    if not package_wheel:raise RuntimeError("Not the full APScheduler package")
    for path,content,blob in zip(SOURCE_PATHS,original.values(),SOURCE_GIT_BLOBS):
        if git_blob_sha(content)!=blob:
            raise RuntimeError("Original release diverged from pinned upstream "+path)
    return wheel_bytes,package_wheel,original

def _stage(root:Path,wheels:dict[str,bytes])->None:
    for name,raw in wheels.items():
        target=root/name
        target.write_bytes(raw)
        target.chmod(0o644)
    target=root/"probe.py"
    target.write_bytes(PROBE.encode("utf-8"))
    target.chmod(0o644)

def _evaluate(stage:Path,cases:list[dict])->dict:
    cli=shutil.which("docker")
    if not cli:raise RuntimeError("No Docker; no fallback to host")
    command=[cli,"run","--rm","-i","--pull=never","--network=none",
        "--read-only","--cap-drop=ALL","--security-opt=no-new-privileges",
        "--pids-limit=32","--memory=192m","--cpus=0.5","--user=65534:65534",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=8m",
        "--mount",f"type=bind,src={stage},dst=/app,readonly",
        "--workdir=/app","--entrypoint=python",IMAGE,"-B","-S","/app/probe.py"]
    result=[]
    for item in cases:
        payload=json.dumps(item["input"],sort_keys=True).encode()
        run=subprocess.run(command,input=payload,capture_output=True,
                           timeout=16,check=False)
        if run.returncode or not run.stdout or len(run.stdout)>4096:
            raise RuntimeError("Actual full package offline Docker unavailable")
        try: observed=json.loads(run.stdout)
        except ValueError as exc:raise RuntimeError("Invalid original wheel output") from exc
        result.append({"pass":observed==item["expected"],
                       "actual_digest":sha(json.dumps(observed,sort_keys=True).encode())})
    return {"passes":sum(r["pass"] for r in result),
            "total":len(cases),"cases":result}

def baseline()->None:
    root=Path(os.environ.get("P32_WHEELS","")).resolve()
    wheels,upstream,files=_wheels(root)
    with tempfile.TemporaryDirectory(prefix="p32-apscheduler-original-") as folder:
        stage=Path(folder)
        stage.chmod(0o755)
        _stage(stage,wheels)
        results=_evaluate(stage,PUBLIC)
    print("p32_full_original_baseline="+json.dumps({
        "issue":ISSUE,"upstream_version":UPSTREAM_REF,
        "wheel_shas":{name:sha(raw) for name,raw in wheels.items()},
        "original_blobs":dict(zip(SOURCE_PATHS,SOURCE_GIT_BLOBS)),
        "manifest_sha256":_manifest(),
        "public_passes":results["passes"],"public_total":results["total"],
        "case_passes":[x["pass"] for x in results["cases"]],
        "original_broken":results["passes"]==2,
        "whole_upstream_wheel_and_real_dependencies":True,
        "model_called":False,"hidden_evaluated":False,
    },sort_keys=True),flush=True)
    if [x["pass"] for x in results["cases"]] !=[True,False,True,False]:
        raise RuntimeError("Full package original baseline differs from predeclared bug")

def _repack(wheel:bytes,changes:dict[str,bytes])->bytes:
    import copy
    with zipfile.ZipFile(io.BytesIO(wheel)) as old:
        names=old.namelist()
        if not set(changes).issubset(names) or set(changes)!=set(SOURCE_PATHS):
            raise ValueError("Both original modules must change")
        recs=[n for n in names if n.endswith(".dist-info/RECORD")]
        if len(recs)!=1:raise ValueError("No unique original RECORD")
        rec=recs[0]
        rows=list(csv.reader(io.StringIO(old.read(rec).decode())))
        counts={name:0 for name in changes}
        for row in rows:
            if row and row[0] in changes:
                content=changes[row[0]]
                row[1]="sha256="+base64.urlsafe_b64encode(
                    hashlib.sha256(content).digest()).decode().rstrip("=")
                row[2]=str(len(content))
                counts[row[0]]+=1
        if any(v!=1 for v in counts.values()):
            raise ValueError("Modified file not correctly indexed in wheel")
        stream=io.StringIO(newline="")
        writer=csv.writer(stream,lineterminator="\n")
        writer.writerows(rows)
        record=stream.getvalue().encode()
        out=io.BytesIO()
        with zipfile.ZipFile(out,"w") as target:
            for info in old.infolist():
                data=(changes.get(info.filename) if info.filename in changes
                      else record if info.filename==rec
                      else old.read(info.filename))
                target.writestr(copy.copy(info),data)
        with zipfile.ZipFile(io.BytesIO(out.getvalue())) as check:
            for name in names:
                expected=(changes[name] if name in changes else
                          record if name==rec else old.read(name))
                if check.read(name)!=expected:
                    raise RuntimeError("Modified unrelated wheel member")
    return out.getvalue()

def _scope(original:dict[str,bytes],changes:dict[str,bytes])->bool:
    """Only the specified method bodies may change, not their enclosing APIs."""
    import ast
    import copy
    if set(original)!=set(changes):return False
    target={"apscheduler/datastores/memory.py":("MemoryDataStore","release_job"),
            "apscheduler/_schedulers/async_.py":("AsyncScheduler","_run_job")}
    for path in SOURCE_PATHS:
        try:
            old=ast.parse(original[path].decode())
            new=ast.parse(changes[path].decode())
            classname,methodname=target[path]
            old_classes=[n for n in old.body
                         if isinstance(n,ast.ClassDef) and n.name==classname]
            new_classes=[n for n in new.body
                         if isinstance(n,ast.ClassDef) and n.name==classname]
            if len(old_classes)!=1 or len(new_classes)!=1:return False
            old_methods=[n for n in old_classes[0].body
                         if isinstance(n,ast.AsyncFunctionDef) and n.name==methodname]
            new_methods=[n for n in new_classes[0].body
                         if isinstance(n,ast.AsyncFunctionDef) and n.name==methodname]
            if len(old_methods)!=1 or len(new_methods)!=1:return False
            prior,replacement=old_methods[0],new_methods[0]
            if (ast.dump(prior.args)!=ast.dump(replacement.args)
                or (ast.dump(prior.returns) if prior.returns is not None else None)
                   !=(ast.dump(replacement.returns) if replacement.returns is not None else None)
                or [ast.dump(d) for d in prior.decorator_list]
                   !=[ast.dump(d) for d in replacement.decorator_list]
                or prior.type_comment!=replacement.type_comment
                or ast.dump(prior)==ast.dump(replacement)):
                return False
            # Normalize ONLY the replacement method back to original before
            # comparing entire full-module AST. This catches alterations to
            # the class bases, decorators, type hints, other methods or imports.
            adjusted=copy.deepcopy(new)
            adjusted_classes=[n for n in adjusted.body
                              if isinstance(n,ast.ClassDef) and n.name==classname]
            adjusted_class=adjusted_classes[0]
            for index,node in enumerate(adjusted_class.body):
                if isinstance(node,ast.AsyncFunctionDef) and node.name==methodname:
                    adjusted_class.body[index]=copy.deepcopy(prior)
                    break
            if ast.dump(adjusted)!=ast.dump(old):
                return False
        except (SyntaxError,UnicodeError,ValueError,TypeError):
            return False
    return True

def _compact(raw:str,original:dict[str,bytes])->dict[str,bytes]:
    obj=json.loads(raw)
    if not isinstance(obj,dict) or set(obj)!={"edits"} or not isinstance(obj["edits"],list):
        raise ValueError("JSON compact patch schema invalid")
    if not 2<=len(obj["edits"])<=4:raise ValueError("Two original modules must be edited")
    sources={p:content.decode() for p,content in original.items()}
    changed=set()
    for item in obj["edits"]:
        if (not isinstance(item,dict) or set(item)!={"path","find","replace"}
            or item["path"] not in sources
            or not isinstance(item["find"],str) or not isinstance(item["replace"],str)
            or not 1<=len(item["find"])<=1100 or not 1<=len(item["replace"])<=2000
            or item["find"]==item["replace"]):
            raise ValueError("Unapproved compact edit")
        path=item["path"]
        if sources[path].count(item["find"])!=1:
            raise ValueError("FIND_NOT_UNIQUE")
        sources[path]=sources[path].replace(item["find"],item["replace"],1)
        changed.add(path)
    if changed!=set(SOURCE_PATHS):
        raise ValueError("Both original modules must change")
    proposed={p:v.encode() for p,v in sources.items()}
    if not _scope(original,proposed):
        raise ValueError("AST_SCOPE_REJECTED")
    return proposed

def _prompt(files:dict[str,bytes])->str:
    a=files[SOURCE_PATHS[0]].decode()
    b=files[SOURCE_PATHS[1]].decode()
    i=a.index("    async def release_job(")
    j=b.index("    async def _run_job(")
    return (
        "Fix APScheduler 4.0.0a6 real reported issue. Original wheel and real "
        "dependencies will execute in network-isolated Docker. ONE trial. "
        "Return JSON object ONLY with key edits, containing 2 to 4 "
        "objects each with exactly path, find and replace strings. Each "
        "find must be a unique verbatim original-source snippet <=1100 "
        "characters, replacement <=2000 chars; edit ONLY original bodies "
        "of MemoryDataStore.release_job AND AsyncScheduler._run_job, "
        "in both named files. No whole file, no new imports or modules. "
        "Do not fabricate results or rewrite the probe.\nBehavior goal:\n"
        +GOAL+"\nPublic visible examples:\n"
        +json.dumps(PUBLIC,sort_keys=True)+"\n"
        +"Real original datastore release method:\n"+a[i:i+1600]+"\n"
        +"Real original async scheduler run method:\n"+b[j:j+4300]
    )

def real_model()->None:
    from cognition_agent_os import local_model
    if os.environ.get("P32_REAL_7B_OPT_IN")!="1":
        raise RuntimeError("No implicit external model experiment")
    model="qwen2.5-coder:7b"
    wheel_root=Path(os.environ.get("P32_WHEELS","")).resolve()
    wheels,name,original=_wheels(wheel_root)
    tags=local_model._request("GET","/api/tags",None,10)
    if model not in {m.get("name") for m in tags.get("models",[]) if isinstance(m,dict)}:
        raise RuntimeError("Genuine 7B model was not installed")
    start=time.monotonic()
    response=local_model._request("POST","/api/generate",{
        "model":model,"prompt":_prompt(original),"stream":False,
        "format":"json","options":{"temperature":0,"num_predict":1650},
        "keep_alive":"0"
    },180)
    if response.get("done") is not True or not isinstance(response.get("response"),str):
        raise RuntimeError("No completed real local model response")
    report={"stage":"P32_ONE_REAL_LOCAL_7B_FULL_UPSTREAM_TWO_MODULES",
        "model":model,"manifest_sha256":_manifest(),
        "one_shot_generations":1,"inference_completed":True,
        "candidate_frozen":False,"public_passes":None,
        "hidden_evaluated":False,"hidden_passes":None,
        "upstream_writes":False,"owner_host_touched":False,
        "automatic_retries":0,"semantic_repair_verified":False}
    try:
        proposal=_compact(response["response"],original)
        repacked=_repack(wheels[name],proposal)
    except (ValueError,UnicodeError,TypeError,KeyError,RuntimeError) as exc:
        report["reason"]="COMPACT_TWO_MODULE_PROPOSAL_REJECTED"
        report["validator_error_type"]=type(exc).__name__
    else:
        report["candidate_frozen"]=True
        with tempfile.TemporaryDirectory(prefix="p32-real-proposal-") as folder:
            stage=Path(folder)
            stage.chmod(0o755)
            edited={key:(repacked if key==name else value) for key,value in wheels.items()}
            _stage(stage,edited)
            public=_evaluate(stage,PUBLIC)
            report["public_passes"]=public["passes"]
            report["public_total"]=public["total"]
            if public["passes"]==len(PUBLIC):
                hidden=_evaluate(stage,HIDDEN)
                report["hidden_evaluated"]=True
                report["hidden_passes"]=hidden["passes"]
                report["hidden_total"]=hidden["total"]
                report["semantic_repair_verified"]=hidden["passes"]==len(HIDDEN)
    report["elapsed_seconds"]=round(time.monotonic()-start,2)
    print("p32_real_full_upstream_7b_result="+json.dumps(report,sort_keys=True),
          flush=True)

if __name__=="__main__":
    if os.environ.get("P32_REAL_7B_OPT_IN")=="1":
        real_model()
    else:
        baseline()
