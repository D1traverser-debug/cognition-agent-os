"""Explicit Docker-only repository code execution, no host fallback.

Untrusted Python is executed ONLY if a preinstalled Docker image exists.
The candidate gets one JSON input via stdin but NEVER any expected outputs
or hidden gold file. Docker is defense-in-depth, not a security boundary
against a hostile kernel/daemon exploit.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

IMAGE="python:3.12-alpine"
MAX_OUTPUT=4096
MAX_INPUT=2048
_ALLOWED=re.compile(r"[a-z][a-z0-9_]{0,48}\.py\Z")
_HEX=re.compile(r"[0-9a-f]{64}\Z")


class ContainerUnavailable(Exception):
    """Docker runtime/service missing or unavailable; NEVER host fallback."""


class CandidateExecutionFailed(Exception):
    """A real Docker run completed, but the untrusted program failed."""

    def __init__(self, code: str):
        if code not in ("CANDIDATE_NONZERO","CANDIDATE_EMPTY_OR_OVERSIZE_OUTPUT",
                        "CANDIDATE_INVALID_JSON_OUTPUT"):
            raise ValueError("Unapproved candidate failure code")
        self.code=code
        super().__init__(code)


def _json_bytes(value)->bytes:
    return (json.dumps(value,sort_keys=True,separators=(",",":"),
                       ensure_ascii=False)+"\n").encode("utf-8")


def validate_task_spec(spec):
    keys={"kind","files","entrypoint","candidate","visible","holdout",
          "holdout_sha256"}
    if not isinstance(spec,dict) or set(spec)!=keys or spec["kind"]!="repo_container_repair":
        raise ValueError("Unsupported repository experiment contract")
    files=spec["files"]
    if (not isinstance(files,list) or not 2<=len(files)<=6
        or any(not isinstance(p,str) or not _ALLOWED.fullmatch(p) for p in files)
        or len(set(files))!=len(files)):
        raise ValueError("Only 2-6 flat Python source files are allowed")
    if spec["entrypoint"] not in files:return _reject("Entrypoint must be approved")
    for key in ("candidate","visible","holdout"):
        name=spec[key]
        if (not isinstance(name,str) or not 1<=len(name)<=80
            or not re.fullmatch(r"[a-zA-Z0-9_-]+\.json",name)):
            raise ValueError("Input must be a flat named JSON fixture")
    if len({spec["candidate"],spec["visible"],spec["holdout"]})!=3:
        raise ValueError("Proposal, public and gold inputs must be separate")
    pin=spec["holdout_sha256"]
    if not isinstance(pin,str) or not _HEX.fullmatch(pin):
        raise ValueError("Holdout requires independent SHA256 pin")
    return spec


def _reject(reason):
    raise ValueError(reason)


def candidate_changes(raw,allowed_files):
    if len(raw)>65536:raise ValueError("Candidate exceeded 64KB")
    doc=json.loads(raw)
    if not isinstance(doc,dict) or set(doc)!={"changes"} or not isinstance(doc["changes"],list):
        raise ValueError("Candidate format requires only changes")
    edits=doc["changes"]
    if not 1<=len(edits)<=len(allowed_files):
        raise ValueError("Candidate change count invalid")
    changed={}
    for item in edits:
        if not isinstance(item,dict) or set(item)!={"path","content"}:
            raise ValueError("Changed file must contain path and content")
        path,content=item["path"],item["content"]
        if (not isinstance(path,str) or path not in allowed_files or path in changed
            or not isinstance(content,str) or len(content.encode("utf-8"))>16384
            or "\0" in content):
            raise ValueError("Change violates file allowlist or size bounds")
        changed[path]=content.encode("utf-8")
    return changed


def cases_from_bytes(raw):
    if len(raw)>16384:raise ValueError("Test cases too large")
    doc=json.loads(raw)
    if not isinstance(doc,list) or not 1<=len(doc)<=8:
        raise ValueError("Test suite must contain 1-8 cases")
    for case in doc:
        if not isinstance(case,dict) or set(case)!={"input","expected"}:
            raise ValueError("Cases need input and expected")
        if len(_json_bytes(case["input"]))>MAX_INPUT:
            raise ValueError("Test input exceeded bound")
        if len(_json_bytes(case["expected"]))>MAX_OUTPUT:
            raise ValueError("Expected output exceeded bound")
    return doc


def _docker_run(directory:Path,entrypoint:str,case_input)->dict:
    """Execute a single case as an unprivileged, offline, resource-capped process.

    No host Python fallback, no Docker build, no pull, no shell and no
    host fixture/holdout mount. An exit code, timeout or invalid JSON
    cannot be reported as a successful test result.
    """
    cli=shutil.which("docker")
    if not cli:raise ContainerUnavailable("DOCKER_CLI_NOT_INSTALLED")
    # -i is required: subprocess.run(input=...) otherwise sends JSON into
    # Docker CLI stdin while the container receives EOF (not the testcase).
    command=[cli,"run","--rm","-i","--pull=never",
             "--network=none","--read-only","--cap-drop=ALL",
             "--security-opt=no-new-privileges","--pids-limit=32",
             "--memory=128m","--cpus=0.5","--user=65534:65534",
             "--tmpfs=/tmp:rw,noexec,nosuid,size=8m",
             "--mount",f"type=bind,src={directory},dst=/app,readonly",
             "--workdir=/app","--entrypoint=python",
             IMAGE,"-B","-S",f"/app/{entrypoint}"]
    try:
        child=subprocess.run(command,input=_json_bytes(case_input),
                             capture_output=True,timeout=8,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ContainerUnavailable("CONTAINER_LAUNCH_OR_TIMEOUT") from exc
    if child.returncode in (125,126,127):
        # Docker CLI/runtime failures, not evidence about candidate logic.
        raise ContainerUnavailable("DOCKER_PROCESS_UNAVAILABLE")
    if child.returncode!=0:
        raise CandidateExecutionFailed("CANDIDATE_NONZERO")
    if not child.stdout or len(child.stdout)>MAX_OUTPUT:
        raise CandidateExecutionFailed("CANDIDATE_EMPTY_OR_OVERSIZE_OUTPUT")
    try:
        return json.loads(child.stdout)
    except (ValueError,UnicodeError) as exc:
        raise CandidateExecutionFailed("CANDIDATE_INVALID_JSON_OUTPUT") from exc


def run_suite(base_sources:dict[str,bytes],changes:dict[str,bytes],
              entrypoint:str, cases:list[dict])->dict:
    """Run candidate in disposable directory; comparison remains in HOST.

    Expected values NEVER enter files, Docker mounts, stdin, CLI arguments
    or environment passed to the candidate. Test inputs alone are visible.
    """
    if set(changes)-set(base_sources) or entrypoint not in base_sources:
        raise ValueError("Executable files outside approved input manifest")
    with tempfile.TemporaryDirectory(prefix="cognition-repo-docker-") as temp:
        root=Path(temp)
        os.chmod(root,0o755)
        for name,original in base_sources.items():
            if not _ALLOWED.fullmatch(name) or len(original)>16384:
                raise ValueError("Unsafe code snapshot")
            file=root/name
            file.write_bytes(changes.get(name,original))
            os.chmod(file,0o644)
        passes=0
        observed=[]
        for case in cases:
            try:
                result=_docker_run(root,entrypoint,case["input"])
            except CandidateExecutionFailed as exc:
                # A broken candidate is a public-test failure, NOT proof
                # Docker is missing. Safe enum can be fed back to a model;
                # no traceback/host paths/hidden expected values disclosed.
                observed.append({
                    "output_sha256":hashlib.sha256(exc.code.encode()).hexdigest(),
                    "pass":False,"execution_error":exc.code})
                continue
            expected=_json_bytes(case["expected"])
            observed_bytes=_json_bytes(result)
            accepted=observed_bytes==expected
            passes+=int(accepted)
            observed.append({"output_sha256":hashlib.sha256(observed_bytes).hexdigest(),
                             "pass":accepted})
    return {"passes":passes,"total":len(cases),"observed":observed}
