"""Read-only registration precondition; never create a write authority.

Run by the opt-in Windows Task Scheduler registration script. A regular
file's mere existence is NOT evidence it is an initialized task ledger.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from cognition_agent_os.host import HostNotConfigured,_admit_existing_ledger


def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True,type=Path)
    args=p.parse_args()
    try:
        _admit_existing_ledger(args.db)
    except HostNotConfigured as exc:
        print(json.dumps({"status":"REGISTRATION_BLOCKED",
                          "reason":str(exc),
                          "new_authority_created":False},sort_keys=True))
        return 4
    print(json.dumps({"status":"INITIALIZED_LEDGER_OBSERVED",
                      "new_authority_created":False,
                      "production_permission_granted":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
