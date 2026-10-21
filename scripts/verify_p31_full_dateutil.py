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

if __name__=="__main__":
    main()
