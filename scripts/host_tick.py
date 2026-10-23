"""Run the local package without installing or downloading dependencies."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cognition_agent_os.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
