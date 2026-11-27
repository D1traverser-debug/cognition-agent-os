"""One offline engineering receipt; never a model/owner-outcome certification.

Reuses existing acceptance probes. No downloads, account edits or model calls.
Use an output directory outside the checkout; full logs stay out of context.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def source_identity():
    def git(*args):
        return subprocess.check_output(["git", "-C", str(ROOT), *args])
    names = set(git("ls-files", "-z", "--cached", "--others", "--exclude-standard").split(b"\0")) - {b""}
    digest = hashlib.sha256()
    for name in sorted(names):
        path = ROOT / os.fsdecode(name)
        digest.update(name + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest() if path.is_file() else b"MISSING")
    return {"head": git("rev-parse", "HEAD").decode().strip(),
            "content_sha256": digest.hexdigest(),
            "dirty": bool(git("status", "--porcelain", "--untracked-files=all"))}


def run_check(name, command, output, environment, *, cwd=ROOT):
    log = output / (name + ".log")
    start = time.monotonic()
    with log.open("w", encoding="utf-8") as stream:
        try:
            result = subprocess.run(command, cwd=cwd, env=environment, timeout=600,
                                    stdout=stream, stderr=subprocess.STDOUT)
            code = result.returncode
        except subprocess.TimeoutExpired:
            stream.write("CHECK_TIMEOUT: no passing receipt may be inferred\n")
            code = 124
        except OSError as exc:
            stream.write(str(exc))
            code = 127
    row = {"name": name, "status": "PASS" if code == 0 else "FAIL",
           "exit_code": code, "seconds": round(time.monotonic() - start, 2),
           "log": str(log), "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()}
    print(json.dumps(row), flush=True)
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--profile", choices=("core", "transport", "full"), default="full")
    parser.add_argument("--build-python", default=sys.executable,
                        help="Existing Python with pip and setuptools; no dependency download")
    parser.add_argument("--mcp-python", default=sys.executable,
                        help="Existing Python with the MCP extra installed")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents or output.exists():
        parser.error("output must be a NEW directory outside the checkout")
    output.mkdir(parents=True)
    before = source_identity()
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONUTF8="1",
               PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    installed_env = dict(env)
    installed_env.pop("PYTHONPATH", None)
    rows = []

    def check(name, command, *, source_context=True, **kwargs):
        row = run_check(name, command, output, env if source_context else installed_env, **kwargs)
        rows.append(row)
        return row["status"] == "PASS"

    if args.profile in ("core", "full"):
        check("regression", [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])
        for name in ("assurance_registry", "effect_boundaries"):
            check(name, [sys.executable, "scripts/verify_" + name + ".py"])
        # Build a copy so setuptools cannot leave stale build output in source.
        with tempfile.TemporaryDirectory(prefix="caos-wheel-") as temporary:
            stage = Path(temporary)
            shutil.copytree(ROOT / "src", stage / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
            shutil.copy2(ROOT / "pyproject.toml", stage / "pyproject.toml")
            wheel_dir = output / "wheel"
            if check("wheel_build", [args.build_python, "-m", "pip", "wheel", "--no-deps",
                    "--no-build-isolation", str(stage), "-w", str(wheel_dir)], cwd=stage, source_context=False):
                wheels = list(wheel_dir.glob("*.whl"))
                if len(wheels) != 1:
                    raise RuntimeError("EXPECTED_ONE_WHEEL")
                venv = stage / "installed"
                if check("isolated_environment", [sys.executable, "-m", "venv", str(venv)], source_context=False):
                    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
                    if check("wheel_install", [str(python), "-m", "pip", "install", "--no-deps", str(wheels[0])], cwd=stage, source_context=False):
                        check("installed_cli", [str(python), str(ROOT / "scripts/verify_installed_cli.py")], cwd=stage, source_context=False)
    if args.profile in ("transport", "full"):
        for name in ("native_mcp_transport", "managed_cognition_transport"):
            check(name, [args.mcp_python, "scripts/verify_" + name + ".py"])
    after = source_identity()
    passed = bool(rows) and all(row["status"] == "PASS" for row in rows) and before == after
    report = {"schema": "caos-engineering-receipt-v1", "profile": args.profile,
              "status": "PASS" if passed else "FAIL", "source_before": before,
              "source_after": after, "checks": rows, "product_ready": False,
              "model_semantics": "NOT_TESTED", "native_account_connection": "NOT_TESTED",
              "scope": "existing deterministic local engineering probes only"}
    (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "receipt": str(output / "receipt.json"), "product_ready": False}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
