"""CLI convenience wrapper forwarding to ``orekit_nrlmsis21.acquire``."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "python"))

from orekit_nrlmsis21.acquire import main

if __name__ == "__main__":
    sys.exit(main())
