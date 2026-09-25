"""Unified entry point -- avoids relative import issues in CI and local runs."""

import sys

# Windows GBK consoles cannot encode emoji — degrade gracefully
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    from src.main import main
    main()
