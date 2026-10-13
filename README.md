# 🎬 YouTube Summarizer

Paste a YouTube link and get a clean AI summary of the video, in **Arabic or English**.

The app downloads the video's captions, splits long transcripts into chunks, summarizes each chunk with a free LLM, and merges everything into one structured summary (short summary, main points, important information).

---

## Features

- Works with Arabic and English captions (falls back to any available caption track)
- Handles long videos with chunked "map-reduce" summarization
- Summary language: same as the video, Arabic, or English
- Free to run: Kaggle notebook + Groq free tier + ngrok
- Automatic fallback when YouTube blocks cloud servers: captions are fetched on your own computer instead
- Automatic model selection, so a retired model won't break the project
- Paste-a-transcript mode for videos you can't fetch
- Download the summary as a `.md` file

## How it works

```
┌────────────────────┐   YouTube URL    ┌──────────────────────────────┐   prompt   ┌───────────┐
│  Streamlit app     │ ───────────────► │  FastAPI + ngrok (Kaggle)    │ ─────────► │ Groq LLM  │
│  (your computer)   │ ◄─────────────── │  captions → chunks → merge   │ ◄───────── │           │
└────────────────────┘     summary      └──────────────────────────────┘  summaries └───────────┘
          │
          └─ If YouTube blocks Kaggle's IP: the app fetches the captions locally
             and sends the transcript text to the API instead.
```

## Tech stack

| Part | Tool |
|---|---|
| Captions | `youtube-transcript-api` |
| LLM | Groq API (OpenAI-compatible), model auto-selected (currently `openai/gpt-oss-20b`) |
| Backend | FastAPI + Uvicorn |
| Public URL | ngrok (via `pyngrok`) |
| Frontend | Streamlit |
| Hosting for the backend | Kaggle Notebook |

## Project structure

```
Youtube_summarizer/
├── youtube-summarizer.ipynb   # Kaggle notebook: runs the API + ngrok tunnel
├── api.py                     # Same backend as the notebook, for running outside Kaggle
├── app.py                     # Streamlit user interface
├── requirements.txt           # Python packages
└── README.md
```

---

## Setup

### 1. Get the free keys

| Key | Where |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys |
| `NGROK_AUTH_TOKEN` | https://dashboard.ngrok.com/get-started/your-authtoken |

### 2. Start the backend on Kaggle

1. Create a new Kaggle notebook and upload `youtube-summarizer.ipynb`.
2. In **Add-ons → Secrets**, add `GROQ_API_KEY` and `NGROK_AUTH_TOKEN`, and **attach both** to the notebook.
3. In the notebook settings, turn **Internet ON**.
4. Run all cells from top to bottom.
5. Copy the **API URL** printed by the server cell, for example `https://xxxx.ngrok-free.dev`.

> Keep the notebook running while you use the app. ngrok free URLs change on every run.

### 3. Start the Streamlit app on your computer

Open Command Prompt or PowerShell in the project folder:

```bash
cd C:\Users\user\Downloads\Youtube_summarizer
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Then:

1. Paste the **API URL** into the sidebar.
2. Choose the summary language.
3. Paste a YouTube link and press **Summarize**.

> Use `python -m pip` and `python -m streamlit` (or `py -m ...`) so packages are installed for the same Python that runs Streamlit.

### Optional: run the API on your own computer instead of Kaggle

```powershell
python -m pip install -r requirements.txt
$env:GROQ_API_KEY = "your_key_here"      # PowerShell
python api.py                            # serves on http://localhost:8000
```

Then use `http://localhost:8000` as the API URL in the app. No ngrok needed. Your home IP is also less likely to be blocked by YouTube.

---

## API reference

Interactive docs are available at `<API URL>/docs`.

### `GET /health`

```json
{ "status": "ok", "model": "openai/gpt-oss-20b", "key_set": true }
```

### `POST /summarize`

Send **either** a YouTube `url` **or** a `transcript`.

```bash
curl -X POST "<API URL>/summarize" \
  -H "Content-Type: application/json" \
  -H "ngrok-skip-browser-warning: true" \
  -d '{"url": "https://youtu.be/0CmtDk-joT4", "language": "en"}'
```

| Field | Type | Description |
|---|---|---|
| `url` | string | YouTube link; the server fetches the captions |
| `transcript` | string | Transcript text (used when YouTube blocks the server) |
| `language` | `auto` / `ar` / `en` | Summary language (`auto` = same as the video) |

Response:

```json
{
  "video_id": "0CmtDk-joT4",
  "language": "en",
  "words": 515,
  "chunks": 1,
  "summary": "## Short summary\n..."
}
```

Errors return `{"detail": {"code": "...", "message": "..."}}` with codes such as `invalid_url`, `youtube_blocked`, `transcripts_disabled`, `no_transcript`, `video_unavailable`, `llm_error`.

---

## Configuration

Environment variables (all optional except the keys):

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Groq key (required) |
| `NGROK_AUTH_TOKEN` | ngrok token (required on Kaggle) |
| `LLM_MODEL` | Force a specific model instead of auto-selecting |
| `LLM_URL` | Use another OpenAI-compatible provider (chat completions URL) |
| `LLM_API_KEY` | Key for that provider (overrides `GROQ_API_KEY`) |
| `PROXY_URL` | Proxy for YouTube requests, e.g. `http://user:pass@host:port` |
| `API_URL` | Default API URL shown in the Streamlit sidebar |

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `RequestBlocked` / `youtube_blocked` | YouTube blocks cloud IPs such as Kaggle | The app falls back to fetching captions on your computer automatically. Or use the paste-transcript box, a proxy (`PROXY_URL`), or run the API locally |
| `402 Payment Required` | Hugging Face account has no credits | This project uses Groq instead, so this should not appear |
| `404 model_not_found` | The model was retired by the provider | The code auto-selects an available model. Update the notebook/`api.py` to the latest version |
| `Cannot list models: 401` | Wrong or missing Groq key | Check `GROQ_API_KEY` in Kaggle Secrets (and that it is attached) |
| `429` / slow summaries | Free-tier rate limits | The code waits and retries automatically; long videos can take a few minutes |
| `ModuleNotFoundError: youtube_transcript_api` | Packages not installed for this Python | Run `python -m pip install -r requirements.txt` |
| Streamlit can't reach the API | Notebook stopped or ngrok URL changed | Re-run the server cell and paste the new URL |
| `Transcripts are disabled` / no captions | The video has no captions | Try another video; this project has no speech-to-text |

## Limitations

- Only videos **with captions** (manual or auto-generated) can be summarized.
- Free-tier limits apply: heavy use may hit daily token caps.
- The ngrok URL changes each session, so update it in the sidebar.
- Summary quality depends on the caption quality.

## Security

- Never write API keys inside notebook cells or commit them to GitHub. Use Kaggle Secrets or environment variables.
- If a key was ever shared or pasted publicly, revoke it and create a new one.

## About the model

The project originally targeted `meta-llama/Llama-3.1-8B-Instruct` through Hugging Face. That route needs paid credits, and Groq retired its free Llama 3.1 8B model on 2026-08-16. The project now auto-selects a currently available Groq model. To use Llama again, point `LLM_URL`, `LLM_MODEL` and `LLM_API_KEY` at a provider that still hosts it.
