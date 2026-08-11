# Koca Kafa

Yerel AI sohbet arkadaşı. Windows WinForms kodu (`Services/`, `Application/`) arşiv olarak duruyor; yeni çalışan uygulama `companion/` altında.

## Hızlı başlangıç

```bash
bash scripts/install.sh
bash scripts/dev.sh
```

Tarayıcı: http://127.0.0.1:8000

## Özellikler

- Türkçe sohbet arayüzü
- Yerel bellek (SQLite) — ad, kedi adı vb. hatırlar
- Selamlaşma, empati ve basit matematik için deterministik yanıtlar
- Ollama bağlıysa LLM cevapları (`OLLAMA_MODEL`, varsayılan `qwen2.5:3b`)
- Her sohbet çifti eğitim verisine yazılır: `companion/data/training/koca_kafa_dataset.jsonl`

## Ollama (isteğe bağlı)

```bash
ollama pull qwen2.5:3b
```

Ollama yoksa uygulama **yerel modda** çalışmaya devam eder.

## Test

```bash
source .venv/bin/activate
pytest companion/tests -q
```

## Ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|----------|------------|----------|
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama API |
| `OLLAMA_MODEL` | `qwen2.5:3b` | Model adı |
| `KOCA_KAFA_DATA` | `companion/data` | Veri klasörü |
