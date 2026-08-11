from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .brain import Intent, process
from .config import TRAINING_PATH
from .memory import MemoryStore, extract_memories, memory_context
from .ollama import AiClient, append_training_example

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(title="Borsa", version="0.2.0", description="AI tabanlı borsa asistanı")
store = MemoryStore()
ai = AiClient()

_LABELS = {
    "user_name": "adın",
    "preferred_name": "hitap",
    "risk_profile": "risk profili",
    "watchlist": "takip listesi",
    "city": "şehir",
}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    intent: str
    source: str
    ai: bool
    provider: str


class HealthResponse(BaseModel):
    status: str
    ai: bool
    provider: str
    model: str


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    status = await ai.status()
    return HealthResponse(
        status="ok",
        ai=status.available,
        provider=status.provider,
        model=status.model,
    )


@app.get("/api/memories")
async def list_memories() -> dict:
    items = store.list_all()
    return {
        "memories": [
            {
                "key": m.key,
                "value": m.value,
                "importance": m.importance,
                "updated_at": m.updated_at,
            }
            for m in items
        ]
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Mesaj boş olamaz.")

    for key, value, importance in extract_memories(message):
        store.upsert(key, value, importance)

    memories = {m.key: m.value for m in store.list_all()}
    brain = process(message, memories=memories, prefer_llm=True)
    ai_status = await ai.status()

    reply: str
    source: str
    used_ai = False
    provider = "none"

    # Memory teach stays local so facts are confirmed instantly.
    if brain.intent == Intent.MEMORY_TEACH:
        learned = extract_memories(message)
        if learned:
            key, value, _ = learned[0]
            reply = f"Tamam — {_LABELS.get(key, key)} olarak '{value}' kaydettim."
        else:
            reply = brain.reply or "Tamam, aklımda tuttum."
        source = brain.source
    elif brain.reply is not None and not brain.use_llm:
        reply = brain.reply
        source = brain.source
    elif ai_status.available and brain.use_llm:
        history = [
            {"role": m.role, "content": m.content}
            for m in store.recent_messages(12)
            if m.role in {"user", "assistant"}
        ]
        try:
            reply, provider = await ai.chat(
                message,
                history=history,
                memory_block=memory_context(store.list_all()),
                intent=brain.intent.value,
            )
            source = f"ai:{provider}"
            used_ai = True
        except Exception:
            reply = brain.reply or (
                "AI model yanıt veremedi. Sorunu bir cümleyle tekrar eder misin?"
            )
            source = "fallback"
            provider = "none"
    else:
        if brain.reply:
            reply = brain.reply
            source = brain.source
        else:
            reply = (
                "AI şu an bağlı değil. Ollama çalıştır veya OPENAI_API_KEY ekle. "
                "Şimdilik risk profilini / takip listeni kaydedebilirim "
                "(ör. 'Risk tercihim orta', 'Takip ettiğim hisseler: THYAO, ASELS')."
            )
            source = "offline"

    store.add_message("user", message)
    store.add_message("assistant", reply)
    append_training_example(TRAINING_PATH, message, reply)

    return ChatResponse(
        reply=reply,
        intent=brain.intent.value,
        source=source,
        ai=used_ai,
        provider=provider,
    )


@app.post("/api/reset")
async def reset_chat() -> dict:
    store.clear_messages()
    return {"ok": True}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
