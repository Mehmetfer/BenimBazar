from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("BORSA_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "borsa.db"

# Starting cash for paper trading (TRY)
STARTING_CASH = float(os.environ.get("BORSA_STARTING_CASH", "100000"))
