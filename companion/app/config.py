from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("BORSA_DATA", os.environ.get("KOCA_KAFA_DATA", ROOT / "data")))
DB_PATH = DATA_DIR / "borsa.db"
TRAINING_PATH = DATA_DIR / "training" / "borsa_dataset.jsonl"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")

# OpenAI-compatible API (optional). When set, preferred over local Ollama.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

SYSTEM_PERSONA = (
    "Sen Borsa'sın — AI tabanlı Türkçe borsa ve yatırım asistanı. "
    "Hisse, endeks, risk, portföy ve temel analiz konularında net ve sakin konuş. "
    "Yatırım tavsiyesi verme; eğitim ve çerçeve sun. Rakam uydurma. "
    "Bilmediğin canlı fiyatı tahmin etme; veri yoksa bunu söyle. "
    "Kısa cevap ver. Gerektiğinde tek net soru sor. "
    "Kullanıcının risk tercihi ve takip ettiği hisseleri hatırla."
)
