# Borsa

AI tabanlı Türkçe borsa asistanı. Yanıtlar Ollama veya OpenAI uyumlu API üzerinden üretilir.

## Hızlı başlangıç

```bash
bash scripts/install.sh
bash scripts/dev.sh
```

Tarayıcı: http://127.0.0.1:8000

## AI bağlantısı

### Seçenek A — Yerel Ollama
```bash
ollama pull qwen2.5:3b
```

### Seçenek B — OpenAI uyumlu API
```bash
export OPENAI_API_KEY=sk-...
# isteğe bağlı:
# export OPENAI_BASE_URL=https://api.openai.com/v1
# export OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_API_KEY` varsa OpenAI tercih edilir; yoksa Ollama kullanılır.

## Özellikler

- AI-first sohbet (piyasa / hisse / risk / portföy)
- Yerel bellek (ad, risk profili, takip listesi)
- Yatırım tavsiyesi vermez; çerçeve ve eğitim odaklıdır
- Eğitim verisi: `companion/data/training/borsa_dataset.jsonl`

## Test

```bash
source .venv/bin/activate
pytest companion/tests -q
```

## Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Yerel Ollama |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Ollama modeli |
| `OPENAI_API_KEY` | — | Varsa AI sağlayıcı olarak kullanılır |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Uyumlu API kökü |
| `OPENAI_MODEL` | `gpt-4o-mini` | Bulut model |
| `BORSA_DATA` | `companion/data` | Veri klasörü |
