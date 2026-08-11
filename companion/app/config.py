from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("KOCA_KAFA_DATA", ROOT / "data"))
DB_PATH = DATA_DIR / "koca_kafa.db"
TRAINING_PATH = DATA_DIR / "training" / "koca_kafa_dataset.jsonl"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

SYSTEM_PERSONA = (
    "Sen Koca Kafa'sın — sıcak, samimi ve net konuşan bir Türkçe sohbet arkadaşı. "
    "Kısa cevap ver. Uydurma. Kullanıcının anlattığı kişisel bilgileri hatırla. "
    "Klinik teşhis koyma. Gerektiğinde tek net soru sor."
)
