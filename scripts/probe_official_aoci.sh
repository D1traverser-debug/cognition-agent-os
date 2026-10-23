#!/usr/bin/env bash
# Experimental OFFICIAL AOCI-CODE bootstrap only; this does not author semantics.
# Trust: pinned SHA256 from upstream release. This is not Cosign publisher auth.
set -euo pipefail
: "$GITHUB_WORKSPACE"
: "$RUNNER_TEMP"
TAG="v0.1.0-rc21"
ARCHIVE="aoci_0.1.0-rc21_linux_amd64.tar.gz"
SHA256="4c0d97f48abb096c4cb9d6abe808d910dd0cff39b61bc7b0ea7be4740bb422f5"
SANDBOX="$(mktemp -d "$RUNNER_TEMP/aoci-probe.XXXXXX")"
trap 'rm -rf -- "$SANDBOX"' EXIT
curl --fail --show-error --location --retry 2 --proto '=https' \
  --tlsv1.2 --max-time 90 \
  "https://github.com/aoci-spec/aoci-code/releases/download/$TAG/$ARCHIVE" \
  -o "$SANDBOX/$ARCHIVE"
printf '%s  %s\n' "$SHA256" "$SANDBOX/$ARCHIVE" | sha256sum --check --status
mkdir -p "$SANDBOX/bin"
python3 - "$SANDBOX/$ARCHIVE" "$SANDBOX/bin" <<'PY'
import pathlib,sys,tarfile
archive,dest=pathlib.Path(sys.argv[1]),pathlib.Path(sys.argv[2])
with tarfile.open(archive,'r:gz') as tar:
    members=tar.getmembers()
    if not members or len(members)>80:
        raise SystemExit("AOCI archive has unexpected member count")
    for member in members:
        path=pathlib.PurePosixPath(member.name)
        if (path.is_absolute() or '..' in path.parts or member.issym()
            or member.islnk() or member.isdev() or (member.isfile() and member.size>60_000_000)):
            raise SystemExit("unsafe AOCI release archive member")
    tar.extractall(dest,filter='data')
PY
EXEC_COUNT="$(find "$SANDBOX/bin" -type f -name aoci | wc -l)"
test "$EXEC_COUNT" -eq 1
AOCI="$(find "$SANDBOX/bin" -type f -name aoci -print -quit)"
chmod u+x "$AOCI"
"$AOCI" --version | tee "$SANDBOX/version.txt"
grep -F 'aoci version 0.1.0-rc21 (commit cfa8e93ca9fe546a375f48b41b3d4766ed98b013' "$SANDBOX/version.txt" >/dev/null

# Clone exact checked-out candidate into a disposable Git worktree.
git clone --quiet --no-local "$GITHUB_WORKSPACE" "$SANDBOX/project"
"$AOCI" --repo "$SANDBOX/project" init --locale en-US --agent codex
"$AOCI" --repo "$SANDBOX/project" scan
test -s "$SANDBOX/project/aoci.txt"
test -s "$SANDBOX/project/aoci.meta.txt"
test -f "$SANDBOX/project/aoci.code.txt"
set +e
"$AOCI" --repo "$SANDBOX/project" verify --json > "$SANDBOX/verify.json" 2> "$SANDBOX/verify.err"
VERIFY_RC=$?
"$AOCI" --repo "$SANDBOX/project" check --json > "$SANDBOX/check.json" 2> "$SANDBOX/check.err"
CHECK_RC=$?
set -e
python3 - "$SANDBOX/verify.json" "$SANDBOX/check.json" "$VERIFY_RC" "$CHECK_RC" "$GITHUB_WORKSPACE/aoci-probe-out" "$SANDBOX/project" <<'PY'
import json,pathlib,shutil,subprocess,sys
verify,check=(pathlib.Path(p) for p in sys.argv[1:3])
for path in (verify,check):
    if not path.is_file() or path.stat().st_size>262144:
        raise SystemExit('AOCI check output missing or oversized')
    try:
        result=json.loads(path.read_text(encoding='utf-8'))
    except (ValueError,UnicodeError) as exc:
        raise SystemExit('AOCI emitted non-JSON machine evidence: '+type(exc).__name__)
    if not isinstance(result,(dict,list)):
        raise SystemExit('AOCI machine evidence is not an object or list')
if int(sys.argv[3])==0 or int(sys.argv[4])==0:
    raise SystemExit("Unexpected fully aligned verdict from un-authored AOCI skeleton")
output=pathlib.Path(sys.argv[5])
output.mkdir(parents=True,exist_ok=True)
for name,source in [('verify.json',verify),('check.json',check)]:
    shutil.copyfile(source,output/name)
commit=subprocess.check_output(
    ['git','-C',sys.argv[6],'rev-parse','HEAD'],text=True).strip()
report={
 'probe':'OFFICIAL_AOCI_INIT_SCAN_SMOKE',
 'release':'v0.1.0-rc21',
 'verification_level':'PINNED_BASIC_SHA_ONLY',
 'actual_mcp_host_connected':False,
 'whole_index_authored':False,
 'index_semantics_verified':False,
 'product_readiness':'NOT_READY',
 'verify_exit_code':int(sys.argv[3]),
 'check_exit_code':int(sys.argv[4]),
 'source_commit':commit,
 'next_required_action':'ORIGINAL_MCP_HOST_MODEL_AUTHORED_FRAS_INDEX'
}
(output/'status.json').write_text(json.dumps(report,indent=2,sort_keys=True)+chr(10),encoding='utf-8')
print(json.dumps(report,sort_keys=True))
PY
