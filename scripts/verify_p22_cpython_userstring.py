"""P22: prospectively frozen real CPython UserString issue, function-family scope.

Only a pre-issue immutable upstream commit may supply source. This is a
controlled experiment on a copied class, not a CPython patch or maintainer review.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cognition_agent_os import local_model
from cognition_agent_os.container_lab import cases_from_bytes, run_suite
from scripts.verify_actual_local_model import ENTRY, MODEL, evaluate_one

UPSTREAM_REPOSITORY = "python/cpython"
UPSTREAM_COMMIT = "d220409a13b77de7a6c30abe16ea90db01528edc"
UPSTREAM_PATH = "Lib/collections/__init__.py"
UPSTREAM_GIT_BLOB = "5dbcac19e7a92726fb9594f406177870db1c08bd"
ISSUE_URL = "https://github.com/python/cpython/issues/159868"
ISSUE_CREATED = "2026-10-20T10:13:31Z"
START_MARKER = "\nclass UserString(_collections_abc.Sequence):"
MAX_ORIGINAL_BYTES = 65000
PREFIX = "import sys as _sys\nimport collections.abc as _collections_abc\n\n"
ADAPTER = (
    "\n\ndef calculate(data):\n"
    "    text = UserString(data['text'])\n"
    "    mode = data['type']\n"
    "    affix = UserString(data['affix']) if mode == 'UserString' else (\n"
    "        data['affix'] if mode == 'str' else 17)\n"
    "    try:\n"
    "        result = getattr(text, data['method'])(\n"
    "            affix, data.get('start', 0), data.get('end', _sys.maxsize))\n"
    "    except (TypeError, ValueError) as exc:\n"
    "        return {'error': type(exc).__name__}\n"
    "    return {'match': bool(result)}\n"
)
# Reporter-owned direct expectations plus ordinary str controls. All heldout
# rows are Agent-derived semantic probes, not private maintainer-owned gold.
PUBLIC = [
    {"input":{"text":"hello world","method":"startswith","type":"UserString","affix":"hello"},"expected":{"match":True}},
    {"input":{"text":"hello world","method":"endswith","type":"UserString","affix":"world"},"expected":{"match":True}},
    {"input":{"text":"hello world","method":"startswith","type":"str","affix":"hello"},"expected":{"match":True}},
    {"input":{"text":"hello world","method":"endswith","type":"str","affix":"wrong"},"expected":{"match":False}},
]
HIDDEN = [
    {"input":{"text":"hello","method":"startswith","type":"UserString","affix":"ell","start":1},"expected":{"match":True}},
    {"input":{"text":"hello","method":"endswith","type":"UserString","affix":"ell","end":4},"expected":{"match":True}},
    {"input":{"text":"hello","method":"startswith","type":"UserString","affix":"xyz"},"expected":{"match":False}},
    {"input":{"text":"hello","method":"endswith","type":"UserString","affix":"hello"},"expected":{"match":True}},
    {"input":{"text":"hello","method":"startswith","type":"int","affix":"ignored"},"expected":{"error":"TypeError"}},
    {"input":{"text":"hello","method":"endswith","type":"int","affix":"ignored"},"expected":{"error":"TypeError"}},
    {"input":{"text":"hello","method":"startswith","type":"str","affix":"he","start":2},"expected":{"match":False}},
    {"input":{"text":"hello","method":"endswith","type":"str","affix":"lo"},"expected":{"match":True}},
]
GOAL_STATEMENT = (
    "Repair the externally reported CPython collections.UserString "
    "startswith/endswith inconsistency (issue #159868): direct UserString "
    "prefix and suffix arguments must be accepted, as for its related "
    "string-like methods. Preserve genuine matching and nonmatching results, "
    "start/end slicing, ordinary str arguments, and TypeError for unsupported "
    "argument types. Change only the two affected methods in the original "
    "upstream class; do not alter the JSON adapter or its input conversion."
)

def git_blob_sha1(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()

def source_url() -> str:
    return (f"https://raw.githubusercontent.com/{UPSTREAM_REPOSITORY}/"
            f"{UPSTREAM_COMMIT}/{UPSTREAM_PATH}")

def fetch_pinned_source() -> bytes:
    with urlopen(source_url(), timeout=25) as response:
        raw = response.read(MAX_ORIGINAL_BYTES + 1)
    if len(raw) > MAX_ORIGINAL_BYTES or git_blob_sha1(raw) != UPSTREAM_GIT_BLOB:
        raise ValueError("P22 upstream source is not the frozen Git blob")
    return raw

def extract_unmodified_class(raw: bytes) -> str:
    if git_blob_sha1(raw) != UPSTREAM_GIT_BLOB:
        raise ValueError("P22 original Git blob changed")
    body = raw.decode("utf-8")
    if body.count(START_MARKER) != 1:
        raise ValueError("Cannot isolate upstream UserString class")
    klass = body[body.index(START_MARKER)+1:].rstrip() + "\n"
    if (len(klass.encode()) > 13000
            or not klass.startswith("class UserString(_collections_abc.Sequence):")
            or "def startswith(" not in klass or "def endswith(" not in klass
            or "def removeprefix(" not in klass):
        raise ValueError("Unexpected original UserString scope")
    return klass

def prepare_case(raw: bytes) -> dict:
    case = {
        "name": "external_cpython_159868_userstring_affixes",
        "source": PREFIX + extract_unmodified_class(raw) + ADAPTER,
        "goal_statement": GOAL_STATEMENT,
        # P22b representation intervention, NOT a changed external goal/gold.
        # A short exact-replacement proposal is expanded mechanically and
        # still judged by the original full-file SQLite/Docker acceptance.
        "candidate_format": "exact_replace",
        "public": PUBLIC,
        "hidden": HIDDEN,
    }
    if len(case["source"].encode()) > 16384:
        raise ValueError("P22 adapted original class exceeds lab bounds")
    return case

def _class_nodes(source: str):
    tree = ast.parse(source)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.ClassDef):
        return None
    klass = tree.body[0]
    if klass.name != "UserString":
        return None
    return klass.body

def candidate_preserves_scope(candidate: bytes, original_class: str) -> bool:
    try:
        body = candidate.decode("utf-8")
    except UnicodeError:
        return False
    if not body.startswith(PREFIX) or not body.endswith(ADAPTER):
        return False
    changed = body[len(PREFIX):-len(ADAPTER)]
    if changed == original_class:
        return False
    try:
        before, after = _class_nodes(original_class), _class_nodes(changed)
        if before is None or after is None or len(before) != len(after):
            return False
        modified = set()
        for old, new in zip(before, after):
            oldname = old.name if isinstance(old, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
            newname = new.name if isinstance(new, (ast.FunctionDef, ast.AsyncFunctionDef)) else None
            if oldname != newname:
                return False
            if ast.dump(old, include_attributes=False) != ast.dump(new, include_attributes=False):
                if oldname not in {"startswith", "endswith"}:
                    return False
                modified.add(oldname)
        return modified == {"startswith", "endswith"}
    except (SyntaxError, TypeError, ValueError):
        return False

def check_independent_scope(root: Path, case: dict, raw: bytes) -> dict:
    original = extract_unmodified_class(raw)
    staged = root / case["name"] / "workspace" / "repo_lab"
    if staged.is_symlink() or not staged.is_dir():
        return {"scope_verified":False, "reason":"NO_STAGED_CANDIDATE"}
    dirs = [x for x in staged.iterdir() if x.is_dir() and not x.is_symlink()]
    if len(dirs) != 1:
        return {"scope_verified":False, "reason":"AMBIGUOUS_STAGING"}
    target = dirs[0] / "calculator.py"
    if target.is_symlink() or not target.is_file() or (dirs[0] / "main.py").exists():
        return {"scope_verified":False, "reason":"ENTRYPOINT_CHANGED_OR_NO_PATCH"}
    okay = candidate_preserves_scope(target.read_bytes(), original)
    return {"scope_verified":okay,
            "reason":"TWO_AFFIX_METHODS_ONLY" if okay else "OTHER_OR_ADAPTER_EDIT"}

def main():
    # Inexpensive independent original-source Docker reproduction MUST pass
    # before installing or claiming any real 7B model competence.
    baseline_only = os.getenv("P22_BASELINE_ONLY") == "1"
    if not baseline_only and (MODEL != "qwen2.5-coder:7b" or
                              os.getenv("P22_ISSUE_OPT_IN") != "1"):
        raise RuntimeError("P22 real local inference needs explicit one-time opt-in")
    raw = fetch_pinned_source()
    case = prepare_case(raw)
    manifest = hashlib.sha256(json.dumps(case,sort_keys=True).encode()).hexdigest()
    baseline = run_suite(
        {"main.py": ENTRY.encode(), "calculator.py": case["source"].encode()},
        {}, "main.py", cases_from_bytes(json.dumps(PUBLIC).encode()))
    if baseline["passes"] != 2 or baseline["total"] != 4:
        raise RuntimeError("P22 real original defect was not reproduced")
    print(json.dumps({"test":"p22_external_baseline", "issue":ISSUE_URL,
          "upstream_commit":UPSTREAM_COMMIT,"git_blob_sha1":UPSTREAM_GIT_BLOB,
          "case_manifest_sha256":manifest,"baseline_public_passes":2,
          "baseline_public_total":4,"acceptance":"REPORTER_PLUS_AGENT_DERIVED_NOT_PRIVATE_MAINTAINER",
          "scope":"EXACT_UPSTREAM_CLASS_COPY_ONLY",
          "stage":"BASELINE_ONLY" if baseline_only else "BEFORE_REAL_7B"},
          sort_keys=True),flush=True)
    if baseline_only:
        return
    installed = local_model._request("GET", "/api/tags", None, 10)
    if MODEL not in {x.get("name") for x in installed.get("models",[]) if isinstance(x,dict)}:
        raise RuntimeError("Installed local model missing; no implicit pull")
    probe = local_model._request("POST","/api/generate",{
        "model":MODEL,"prompt":'Return the JSON object {"probe":true}.',
        "stream":False,"format":"json",
        "options":{"temperature":0,"num_predict":50},"keep_alive":"0"},90)
    if probe.get("done") is not True or not isinstance(probe.get("response"),str):
        raise RuntimeError("No observed authentic local model tokens")
    with tempfile.TemporaryDirectory(prefix="cognition-p22-cpython-") as temp:
        root = Path(temp)
        result = evaluate_one(root,case,goal_statement=GOAL_STATEMENT)
        scope = (check_independent_scope(root,case,raw)
                 if result["holdout_pass"] else
                 {"scope_verified":False,"reason":"HOLDOUT_NOT_ACCEPTED"})
    print(json.dumps({"test":"p22_real_cpython_result",
        "issue":ISSUE_URL,"case_manifest_sha256":manifest,
        "model_completion_genuine":True,"frozen_candidate":result["candidate_frozen"],
        "public_pass":result["public_pass"],"heldout_pass":result["holdout_pass"],
        "scope_pass":result["holdout_pass"] and scope["scope_verified"],
        "scope":scope,"revision_attempts":result["revision_attempts"],
        "original_source_unchanged":result["source_unchanged"],
        "upstream_repo_modified":False,"maintainer_approved":False,
        "training_leakage_not_ruled_out":True,
        "no_paid_cloud_inference":True,"result":result},sort_keys=True),flush=True)

if __name__ == "__main__":
    main()
