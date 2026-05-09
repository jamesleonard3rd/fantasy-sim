"""Convenience launcher for the background simulation runner.

Equivalent to ``python -m rts_world.sim.runner`` but works from a fresh shell
without setting PYTHONPATH, mirroring how ``init_db.py`` and ``demo_generate.py``
add the backend src dir to sys.path before importing.

Usage:

    python backend/scripts/sim.py once    --region-id 1
    python backend/scripts/sim.py forever
    python backend/scripts/sim.py status
    python backend/scripts/sim.py seed-regions --regions 3
"""
from __future__ import annotations

import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from rts_world.sim.runner import main  # noqa: E402


if __name__ == "__main__":
    sys.exit(main())
