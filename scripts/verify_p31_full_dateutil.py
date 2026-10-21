"""P31 full, original third-party wheel + real dependency Docker baseline.

No AST method extraction, hand-written fake implementation, host execution,
Docker fallback, model generation, or hidden cases mounted into the container.
Only the original 2024 python-dateutil distribution and original six wheel
are imported by the container. Expected dates come from independent stdlib
calendar arithmetic, not from dateutil or model output.
"""
from __future__ import annotations
import calendar
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ISSUE="https://github.com/dateutil/dateutil/issues/1588"
DATEUTIL_WHEEL="python_dateutil-2.9.0.post0-py2.py3-none-any.whl"
SIX_WHEEL="six-1.17.0-py2.py3-none-any.whl"
WHEEL_SHAS={
    DATEUTIL_WHEEL:"a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427",
    SIX_WHEEL:"4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274",
}
IMAGE="python:3.12-alpine"
DAY={"MO":0,"TU":1,"WE":2,"TH":3,"FR":4,"SA":5,"SU":6}

# Frozen cases. Limits intentionally keep the original incomplete/buggy
# rule from iterating across thousands of years. Two original controls must pass.
PUBLIC_SPECS=[
    (2024,4,"MO,1FR"),
    (2024,2,"TU,-1TH"),
    (2024,4,"MO"),
    (2024,2,"1FR"),
]
HIDDEN_SPECS=[
    (2024,5,"WE,2FR"),
    (2024,6,"TU,-1SU"),
    (2024,7,"MO,1TH"),
    (2024,8,"FR,3TU"),
    (2025,1,"TH,-1MO"),
    (2024,12,"SA,2WE"),
    (2024,7,"-1MO"),
    (2025,1,"FR"),
]
RULE_RE=re.compile(r"(?:(-?[1-5])?)(MO|TU|WE|TH|FR|SA|SU)\Z")

def _independent_dates(year:int,month:int,byday:str)->list[str]:
    """Calendar implementation independently computes an inclusive BYDAY union."""
    tokens=byday.split(",")
    days=calendar.monthrange(year,month)[1]
    actual=set()
    for token in tokens:
        match=RULE_RE.fullmatch(token)
        if match is None:
            raise ValueError("Not a frozen calendar token")
        ordinal,weekday=match.groups()
        hits=[day for day in range(1,days+1)
              if calendar.weekday(year,month,day)==DAY[weekday]]
        if ordinal:
            index=int(ordinal)
            if abs(index)>len(hits):continue
            actual.add(hits[index-1] if index>0 else hits[index])
        else:
            actual.update(hits)
    return [f"{year:04d}-{month:02d}-{day:02d}" for day in sorted(actual)]

def _cases(rows:list[tuple[int,int,str]])->list[dict]:
    cases=[]
    for year,month,byday in rows:
        end=calendar.monthrange(year,month)[1]
        # The RRULE parser, scheduler and weekday expansion come from the
        # actual third-party package in the offline Docker process.
        rule=f"FREQ=MONTHLY;BYDAY={byday};UNTIL={year:04d}{month:02d}{end:02d}T235959"
        cases.append({
            "input":{"rule":rule,"start":f"{year:04d}-{month:02d}-01"},
            "expected":{"dates":_independent_dates(year,month,byday)},
        })
    return cases

PUBLIC=_cases(PUBLIC_SPECS)
HIDDEN=_cases(HIDDEN_SPECS)
GOAL=("For RFC 5545 RRULE monthly recurrence, mixed unqualified and ordinal "
      "BYDAY entries are a UNION. Preserve the original python-dateutil "
      "2.9.0.post0 wheel's parser and related modules, fix real recurrence "
      "expansion only, and preserve ordinary plain and ordinal BYDAY cases. "
      "No independent expected case results or hidden data are supplied "
      "to the model.")

# Trusted adapter; never includes expected values, issue answer or gold.
PROBE=(
    "import json,sys\n"
    f"sys.path.insert(0,'/app/{DATEUTIL_WHEEL}')\n"
    f"sys.path.insert(0,'/app/{SIX_WHEEL}')\n"
    "from datetime import datetime\n"
    "from dateutil.rrule import rrulestr\n"
    "data=json.loads(sys.stdin.read())\n"
    "try:\n"
    "    start=datetime.fromisoformat(data['start'])\n"
    "    days=[d.date().isoformat() for d in rrulestr(data['rule'],dtstart=start)]\n"
    "    print(json.dumps({'dates':days},sort_keys=True))\n"
    "except Exception as exc:\n"
    "    print(json.dumps({'error':type(exc).__name__},sort_keys=True))\n"
)

def digest(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def git_blob_sha(data:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def manifest()->str:
    return digest(json.dumps({
        "issue":ISSUE,"wheel_shas":WHEEL_SHAS,"goal":GOAL,
        "public":PUBLIC,"hidden":HIDDEN,"probe_sha256":digest(PROBE.encode()),
    },sort_keys=True,separators=(",",":")).encode())

def verify_wheels(wheel_root:Path)->dict[str,bytes]:
    import zipfile
    wheels={}
    for filename,expected in WHEEL_SHAS.items():
        raw=(wheel_root/filename).read_bytes()
        if digest(raw)!=expected:
            raise ValueError("Pinned published dependency wheel SHA256 mismatch")
        wheels[filename]=raw
    with zipfile.ZipFile(wheel_root/DATEUTIL_WHEEL) as archive:
        source=archive.read("dateutil/rrule.py")
        if len(source)<50000 or len(source)>90000:
            raise ValueError("Unexpected full upstream recurrence module")
    return wheels

def _docker_case(stage:Path,data:dict)->dict:
    docker=shutil.which("docker")
    if not docker:raise RuntimeError("Docker missing; host execution prohibited")
    command=[docker,"run","--rm","-i","--pull=never","--network=none",
        "--read-only","--cap-drop=ALL","--security-opt=no-new-privileges",
        "--pids-limit=32","--memory=192m","--cpus=0.5",
        "--user=65534:65534","--tmpfs=/tmp:rw,noexec,nosuid,size=8m",
        "--mount",f"type=bind,src={stage},dst=/app,readonly",
        "--workdir=/app","--entrypoint=python",IMAGE,
        "-B","-S","/app/probe.py"]
    raw=json.dumps(data,sort_keys=True,separators=(",",":")).encode()
    result=subprocess.run(command,input=raw,capture_output=True,timeout=12)
    if result.returncode:
        raise RuntimeError("Original upstream full-wheel execution unavailable")
    if not result.stdout or len(result.stdout)>4096:
        raise RuntimeError("Original upstream Docker response missing or oversized")
    return json.loads(result.stdout)

def _run_cases(stage:Path,cases:list[dict])->dict:
    passes=0
    # Expected values remain only with independent host-side reviewer.
    # The original package receives only each case's "input" dictionary.
    observed=[]
    for case in cases:
        actual=_docker_case(stage,case["input"])
        ok=actual==case["expected"]
        passes+=int(ok)
        observed.append({"pass":ok,"output_sha256":digest(json.dumps(
            actual,sort_keys=True).encode())})
    return {"passes":passes,"total":len(cases),"observed":observed}

def main()->None:
    wheel_root=Path(os.environ.get("P31_WHEELS","")).resolve()
    if not wheel_root.is_dir():
        raise RuntimeError("P31_WHEELS must point to independently downloaded wheels")
    wheels=verify_wheels(wheel_root)
    with tempfile.TemporaryDirectory(prefix="cognition-p31-dateutil-full-") as tmp:
        stage=Path(tmp)
        os.chmod(stage,0o755)
        for name,raw in wheels.items():
            dest=stage/name
            dest.write_bytes(raw)
            os.chmod(dest,0o644)
        (stage/"probe.py").write_text(PROBE,encoding="utf-8")
        (stage/"probe.py").chmod(0o644)
        report=_run_cases(stage,PUBLIC)
        print("p31_full_upstream_original_baseline="+json.dumps({
            "issue":ISSUE,"original_version":"2.9.0.post0",
            "dependency_version":"1.17.0","wheel_hashes":WHEEL_SHAS,
            "manifest_sha256":manifest(),"public_passes":report["passes"],
            "public_total":report["total"],
            "original_broken":0<report["passes"]<report["total"],
            "full_package_imported_in_real_offline_docker":True,
            "actual_model_called":False,
            "hidden_tested":False,
        },sort_keys=True))
        if not 0<report["passes"]<report["total"]:
            raise RuntimeError("Original release must exhibit both failures and controls")


def _public_prompt(source:str)->str:
    """Scope reads to the actual constructor, filter and ordinal mask; no gold."""
    constructor=source.index("        # byweekday / bynweekday")
    cond=source.index("            for i in dayset[start:end]:")
    mask=source.index("                self.nwdaymask = [0]*self.yearlen")
    slices=(
        ("weekday representation",source[constructor:constructor+1900]),
        ("recurrence iteration filter",source[cond:cond+1500]),
        ("ordinal weekday mask construction",source[mask:mask+750]),
    )
    return (
        "You are fixing a REAL bug in python-dateutil 2.9.0.post0, whose "
        "complete original package and actual six dependency are evaluated "
        "offline. The target is only dateutil/rrule.py; change only the "
        "existing rrule._iter method body. Preserve ordinary weekday, ordinal "
        "weekday and unrelated recurrence semantics. This is a one-shot "
        "unfamiliar-project experiment: NO gold cases or model feedback. "
        "Return only a JSON object with an edits list of 1 to 3 entries. "
        "Each entry must have EXACTLY string fields find and replace, where "
        "find is a short UNIQUE LITERAL substring of the original source "
        "(at most 1000 characters) and replace is the corresponding changed "
        "code (at most 1800 characters). No new imports/files, no Markdown. "
        "Do not copy or rewrite the whole 66KB source file.\n"
        "Independent issue goal:\n"+GOAL+"\n"
        "Public visible tests only:\n"
        +json.dumps(PUBLIC,sort_keys=True)+"\n"
        +"\n".join("\n"+label+":\n"+part for label,part in slices)
    )

def _scope_ok(base:str,patched:str)->bool:
    """Allow only the original rrule._iter function AST to change."""
    import ast
    try:
        old=ast.parse(base)
        new=ast.parse(patched)
        if len(old.body)!=len(new.body):return False
        changed=False
        for prev,next_ in zip(old.body,new.body):
            if isinstance(prev,ast.ClassDef) and prev.name=="rrule":
                if not isinstance(next_,ast.ClassDef) or next_.name!="rrule":
                    return False
                if len(prev.body)!=len(next_.body):return False
                if (prev.bases!=next_.bases or len(prev.decorator_list)!=len(next_.decorator_list)):
                    return False
                for prev_method,next_method in zip(prev.body,next_.body):
                    if (isinstance(prev_method,(ast.FunctionDef,ast.AsyncFunctionDef))
                        and prev_method.name=="_iter"):
                        if not isinstance(next_method,ast.FunctionDef) or next_method.name!="_iter":
                            return False
                        if ast.dump(prev_method.args)!=ast.dump(next_method.args):
                            return False
                        changed=changed or ast.dump(prev_method)!=ast.dump(next_method)
                    elif ast.dump(prev_method)!=ast.dump(next_method):
                        return False
            elif ast.dump(prev)!=ast.dump(next_):
                return False
        return changed
    except (SyntaxError,ValueError,TypeError,UnicodeError):
        return False

def _expand_one_compact(raw_response:str,source:str)->str:
    response=json.loads(raw_response)
    if (not isinstance(response,dict) or set(response)!={"edits"}
        or not isinstance(response["edits"],list)
        or not 1<=len(response["edits"])<=3):
        raise ValueError("INVALID_COMPACT_CANDIDATE")
    result=source
    for edit in response["edits"]:
        if (not isinstance(edit,dict) or set(edit)!={"find","replace"}
            or not isinstance(edit["find"],str)
            or not isinstance(edit["replace"],str)
            or not 1<=len(edit["find"])<=1000
            or not 1<=len(edit["replace"])<=1800
            or edit["find"]==edit["replace"]):
            raise ValueError("INVALID_EDIT_SHAPE")
        if result.count(edit["find"])!=1:
            raise ValueError("FIND_NOT_UNIQUE")
        result=result.replace(edit["find"],edit["replace"],1)
    if result==source or not _scope_ok(source,result):
        raise ValueError("UNAPPROVED_METHOD_CHANGE")
    return result

def _repack_only_rrule(wheel:bytes,new_rrule:bytes)->bytes:
    import io
    import zipfile
    target="dateutil/rrule.py"
    original=io.BytesIO(wheel)
    dest=io.BytesIO()
    with zipfile.ZipFile(original) as incoming,zipfile.ZipFile(dest,"w") as outgoing:
        names=incoming.namelist()
        if names.count(target)!=1:
            raise ValueError("Expected a single original rrule source")
        for info in incoming.infolist():
            data=new_rrule if info.filename==target else incoming.read(info)
            outgoing.writestr(info,data)
    repacked=dest.getvalue()
    with zipfile.ZipFile(io.BytesIO(repacked)) as check:
        if check.read(target)!=new_rrule:
            raise RuntimeError("Patched module was not frozen")
        for name in names:
            if name!=target:
                with zipfile.ZipFile(io.BytesIO(wheel)) as origin:
                    if check.read(name)!=origin.read(name):
                        raise RuntimeError("Unrelated upstream package source changed")
    return repacked

def run_one_real_model()->None:
    """Exactly ONE 7B generation with verified full-wheel independent cases."""
    import io
    import time
    import zipfile
    from cognition_agent_os import local_model
    if os.environ.get("P31_REAL_7B_OPT_IN")!="1":
        raise RuntimeError("P31 real model requires distinct explicit opt-in")
    model="qwen2.5-coder:7b"
    tags=local_model._request("GET","/api/tags",None,10)
    names={x.get("name") for x in tags.get("models",[]) if isinstance(x,dict)}
    if model not in names:raise RuntimeError("7B must be installed on disposable runner")
    wheel_root=Path(os.environ.get("P31_WHEELS","")).resolve()
    wheels=verify_wheels(wheel_root)
    with zipfile.ZipFile(io.BytesIO(wheels[DATEUTIL_WHEEL])) as incoming:
        original=incoming.read("dateutil/rrule.py").decode("utf-8")
    start=time.monotonic()
    reply=local_model._request("POST","/api/generate",{
        "model":model,"prompt":_public_prompt(original),
        "stream":False,"format":"json",
        "options":{"temperature":0,"num_predict":1800},
        "keep_alive":"0",
    },180)
    if reply.get("done") is not True or not isinstance(reply.get("response"),str):
        raise RuntimeError("No genuine completed Ollama inference")
    record={
        "status":"GENUINE_LOCAL_7B_REPAIR_ATTEMPT",
        "model":model,"manifest_sha256":manifest(),
        "source_wheel_sha256":WHEEL_SHAS[DATEUTIL_WHEEL],
        "inference_completed":True,"model_called":True,
        "one_shot_generations":1,"feedback_retries":0,
        "candidate_frozen":False,"public_passes":None,
        "hidden_passes":None,"hidden_evaluated":False,
        "original_upstream_modified":False,
        "source_files_changed_in_package":[],
        "external_maintainer_accepted":False,
        "full_upstream_package_execution":False,
    }
    with tempfile.TemporaryDirectory(prefix="p31-full-wheel-candidate-") as tmp:
        stage=Path(tmp)
        os.chmod(stage,0o755)
        try:
            edited=_expand_one_compact(reply["response"],original)
            new_wheel=_repack_only_rrule(wheels[DATEUTIL_WHEEL],edited.encode())
        except (ValueError,TypeError,UnicodeError,KeyError) as exc:
            # A true completed inference with invalid code is still a
            # measured negative result, never a fabricated refuted patch.
            record["reason"]="COMPACT_CANDIDATE_REJECTED"
            record["validation_error_type"]=type(exc).__name__
        else:
            record["candidate_frozen"]=True
            record["source_files_changed_in_package"]=["dateutil/rrule.py"]
            for name,data in wheels.items():
                output=stage/name
                output.write_bytes(new_wheel if name==DATEUTIL_WHEEL else data)
                output.chmod(0o644)
            probe=stage/"probe.py"
            probe.write_text(PROBE,encoding="utf-8")
            probe.chmod(0o644)
            actual=_run_cases(stage,PUBLIC)
            record["public_passes"]=actual["passes"]
            record["public_total"]=actual["total"]
            record["full_upstream_package_execution"]=True
            if actual["passes"]==len(PUBLIC):
                independent=_run_cases(stage,HIDDEN)
                record["hidden_evaluated"]=True
                record["hidden_passes"]=independent["passes"]
                record["hidden_total"]=independent["total"]
                record["isolated_repair_verified"]=(independent["passes"]==len(HIDDEN))
            else:
                record["isolated_repair_verified"]=False
        record["elapsed_seconds"]=round(time.monotonic()-start,2)
    # Never emit generated code, hidden expected values or model answers.
    print("p31_real_full_upstream_7b_result="+json.dumps(record,sort_keys=True),
          flush=True)

if __name__=="__main__":
    if os.environ.get("P31_REAL_7B_OPT_IN")=="1":
        run_one_real_model()
    else:
        main()
