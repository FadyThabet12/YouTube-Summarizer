"""YouTube AI Summarizer API (same code as the notebook cells).

Run: GROQ_API_KEY=... python api.py   (then expose with ngrok if needed)
Optional env: LLM_URL, LLM_MODEL, LLM_API_KEY, PROXY_URL
"""

import os, re, time, requests
from youtube_transcript_api import (YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled,
                                    VideoUnavailable, RequestBlocked, IpBlocked)
from youtube_transcript_api.proxies import GenericProxyConfig

def extract_video_id(url):
    m = (re.search(r"(?:[?&]v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", url)
         or re.fullmatch(r"([\w-]{11})", url.strip()))
    if not m:
        raise ValueError(f"No video id found in: {url}")
    return m.group(1)

def fetch_transcript(video_id):
    proxy = os.environ.get("PROXY_URL")  # optional, helps if YouTube blocks the server
    cfg = GenericProxyConfig(http_url=proxy, https_url=proxy) if proxy else None
    tl = YouTubeTranscriptApi(proxy_config=cfg).list(video_id)
    try:
        t = tl.find_transcript(["ar", "en"])
    except NoTranscriptFound:  # fall back to any available captions
        t = sorted(tl, key=lambda x: x.is_generated)[0]
    f = t.fetch()
    return " ".join(s.text.replace("\n", " ") for s in f), f.language_code

LLM_URL = os.environ.get("LLM_URL", "https://api.groq.com/openai/v1/chat/completions")
PREFER = ["openai/gpt-oss-20b", "openai/gpt-oss-120b", "qwen/qwen3.6-27b", "llama-3.1-8b-instant"]
MODEL = os.environ.get("LLM_MODEL")  # leave unset: auto-pick a model your key can use

def auth():
    key = os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("Missing GROQ_API_KEY")
    return {"Authorization": f"Bearer {key}"}

def pick_model():
    global MODEL
    if not MODEL:
        r = requests.get(LLM_URL.replace("/chat/completions", "/models"), headers=auth(), timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Cannot list models: {r.status_code} {r.text[:150]}")
        ids = [m["id"] for m in r.json().get("data", [])]
        MODEL = next((m for m in PREFER if m in ids), None)
        if not MODEL:
            raise RuntimeError(f"No supported model found. Available: {ids}")
    return MODEL

def llm(prompt, max_tokens=800):
    body = {"model": pick_model(), "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]}
    if "gpt-oss" in body["model"]:
        body["reasoning_effort"] = "low"  # reasoning model: keep its thinking short
    for _ in range(4):  # retry on rate limits / temporary errors
        r = requests.post(LLM_URL, headers=auth(), timeout=120, json={**body, "max_tokens": max_tokens})
        if r.status_code == 200:
            text = (r.json()["choices"][0]["message"].get("content") or "").strip()
            if text:
                return text
            max_tokens *= 2  # thinking used the whole budget: retry with more room
            continue
        if r.status_code not in (429, 500, 502, 503):
            break
        time.sleep(min(float(r.headers.get("retry-after", 20)), 60) + 1)
    raise RuntimeError(f"LLM error {r.status_code}: {r.text[:200]}")

def lang_rule(lang):
    return {"ar": "Write in Arabic.", "en": "Write in English."}.get(lang, "Write in the same language as the text.")

def chunks_of(text, n=600):
    w = text.split()
    return [" ".join(w[i:i + n]) for i in range(0, len(w), n)]

def partial(text, lang):
    return llm(f"Summarize this part of a YouTube transcript in a few concise sentences. {lang_rule(lang)}\n\n{text}", 800)

FINAL = ("Summarize this YouTube video with these sections: ## Short summary, "
         "## Main points (bullets), ## Important information (bullets). ")

def summarize(text, lang="auto"):
    parts = chunks_of(text)
    if not parts:
        raise ValueError("Transcript is empty.")
    if len(parts) > 1:  # map: summarize each chunk, then reduce
        text = "\n\n".join(partial(p, lang) for p in parts)
        while len(text.split()) > 1200:  # very long video: reduce again
            text = "\n\n".join(partial(c, lang) for c in chunks_of(text, 800))
    return llm(f"{FINAL}{lang_rule(lang)}\n\n{text}", 1200), len(parts)

from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="YouTube AI Summarizer")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Req(BaseModel):
    url: Optional[str] = None
    transcript: Optional[str] = None
    language: str = "auto"

ERRORS = {ValueError: (400, "invalid_url"), RequestBlocked: (502, "youtube_blocked"),
          IpBlocked: (502, "youtube_blocked"), TranscriptsDisabled: (404, "transcripts_disabled"),
          NoTranscriptFound: (404, "no_transcript"), VideoUnavailable: (404, "video_unavailable")}

def fail(status, code, msg):
    raise HTTPException(status, {"code": code, "message": msg})

@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL or "auto",
            "key_set": bool(os.environ.get("LLM_API_KEY") or os.environ.get("GROQ_API_KEY"))}

@app.post("/summarize")
def api_summarize(r: Req):
    text, lang, vid = (r.transcript or "").strip(), None, None
    if not text:
        if not r.url:
            fail(400, "missing_input", "Send 'url' or 'transcript'.")
        try:
            vid = extract_video_id(r.url)
            text, lang = fetch_transcript(vid)
        except Exception as e:
            status, code = next((v for k, v in ERRORS.items() if isinstance(e, k)), (500, "transcript_error"))
            fail(status, code, str(e)[:300])
    try:
        summary, n = summarize(text, r.language)
    except Exception as e:
        fail(502, "llm_error", str(e))
    return {"video_id": vid, "language": lang, "words": len(text.split()), "chunks": n, "summary": summary}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
