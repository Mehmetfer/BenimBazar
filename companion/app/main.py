from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .brain import Intent, process_deterministic
from .config import TRAINING_PATH
from .memory import MemoryStore, extract_memories, memory_context
from .ollama import OllamaClient, append_training_example

STATIC_DIR = Path(__file__).resolve().parents[1] / "static"

app = FastAPI(title="Borsa", version="0.1.0")
store = MemoryStore()
ollama = OllamaClient()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatResponse(BaseModel):
    reply: str
    intent: str
    source: str
    ollama: bool


class HealthResponse(BaseModel):
    status: str
    ollama: bool
    model: str


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    ready = await ollama.available()
    return HealthResponse(status="ok", ollama=ready, model=ollama.model)


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
    brain = process_deterministic(message, memories=memories)

    if brain.intent == Intent.MEMORY_TEACH and brain.reply:
        reply = brain.reply
        # If we extracted something concrete, acknowledge it.
        learned = extract_memories(message)
        if learned:
            key, value, _ = learned[0]
            labels = {
                "user_name": "adın",
                "preferred_name": "hitap",
                "cat_name": "kedinin adı",
                "city": "şehir",
            }
            label = labels.get(key, key)
            reply = f"Tamam — {label} olarak '{value}' kaydettim."
        source = brain.source
        used_ollama = False
    elif brain.reply is not None and not brain.use_llm:
        reply = brain.reply
        source = brain.source
        used_ollama = False
    else:
        used_ollama = await ollama.available()
        if used_ollama:
            history = [
                {"role": m.role, "content": m.content}
                for m in store.recent_messages(12)
                if m.role in {"user", "assistant"}
            ]
            try:
                reply = await ollama.chat(
                    message,
                    history=history,
                    memory_block=memory_context(store.list_all()),
                )
                source = "ollama"
            except Exception:
                reply = (
                    "Model şu an yanıt veremedi. Kısa tutayım: sorununu bir cümleyle tekrar eder misin?"
                )
                source = "fallback"
                used_ollama = False
        else:
            reply = (
                "Ollama bağlı değil; şimdilik yerel beynimle yanıtlıyorum. "
                "Kısa soru sor veya bana bir şey öğret (ör. 'Benim adım Mehmet')."
            )
            source = "offline"
            used_ollama = False

    store.add_message("user", message)
    store.add_message("assistant", reply)
    append_training_example(TRAINING_PATH, message, reply)

    return ChatResponse(
        reply=reply,
        intent=brain.intent.value,
        source=source,
        ollama=used_ollama,
    )


@app.post("/api/reset")
async def reset_chat() -> dict:
    store.clear_messages()
    return {"ok": True}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
