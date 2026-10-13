"""YouTube AI Summarizer - Streamlit UI.   Run:  streamlit run app.py

1. Sends the YouTube URL to the API (Kaggle) which fetches captions + summarizes.
2. If YouTube blocks the server, it automatically fetches the captions on YOUR
   computer and sends the text instead.
"""
import os
import re

import requests
import streamlit as st
from youtube_transcript_api import NoTranscriptFound, YouTubeTranscriptApi

H = {"ngrok-skip-browser-warning": "true"}
st.set_page_config(page_title="YouTube AI Summarizer", page_icon="🎬")


class ApiError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def video_id(url):
    m = (re.search(r"(?:[?&]v=|youtu\.be/|shorts/|embed/|live/)([\w-]{11})", url)
         or re.fullmatch(r"([\w-]{11})", url.strip()))
    if not m:
        raise ValueError("Could not find a video id in that link.")
    return m.group(1)


def local_transcript(vid):
    tl = YouTubeTranscriptApi().list(vid)
    try:
        t = tl.find_transcript(["ar", "en"])
    except NoTranscriptFound:
        t = sorted(tl, key=lambda x: x.is_generated)[0]
    return " ".join(s.text.replace("\n", " ") for s in t.fetch())


def post(api, payload):
    r = requests.post(api.rstrip("/") + "/summarize", json=payload, headers=H, timeout=900)
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.ok:
        return body
    d = body.get("detail", {})
    d = d if isinstance(d, dict) else {"message": str(d)}
    raise ApiError(d.get("code"), d.get("message") or r.text[:200])


with st.sidebar:
    default = os.environ.get("API_URL", "")
    api_url = st.text_input("API URL (ngrok)", default, placeholder="https://xxxx.ngrok-free.dev")
    lang = st.selectbox("Summary language", ["auto", "ar", "en"],
                        format_func={"auto": "Same as video", "ar": "العربية", "en": "English"}.get)

st.title("🎬 YouTube AI Summarizer")
url = st.text_input("YouTube URL", placeholder="https://www.youtube.com/watch?v=...")
with st.expander("Or paste a transcript instead"):
    pasted = st.text_area("Transcript", height=200)

if st.button("Summarize", type="primary", use_container_width=True):
    try:
        if not api_url:
            raise ValueError("Enter the API URL in the sidebar first.")
        if not (url.strip() or pasted.strip()):
            raise ValueError("Enter a YouTube URL or paste a transcript.")
        with st.spinner("Summarizing... long videos can take a few minutes."):
            if pasted.strip():
                res = post(api_url, {"transcript": pasted, "language": lang})
            else:
                try:
                    res = post(api_url, {"url": url, "language": lang})
                except ApiError as e:
                    if e.code != "youtube_blocked":
                        raise
                    text = local_transcript(video_id(url))  # fetched from your computer
                    res = post(api_url, {"transcript": text, "language": lang})
        st.success(f"{res['words']:,} words processed in {res['chunks']} chunk(s).")
        st.markdown(res["summary"])
        st.download_button("⬇️ Download summary", res["summary"], "summary.md")
    except Exception as e:
        st.error(str(e)[:400])
