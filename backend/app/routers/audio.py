import io
import re
import logging
import tempfile
from pathlib import Path
from datetime import datetime

import httpx
import yt_dlp
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..config import settings
from ..auth import require_api_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/audio", tags=["audio"], dependencies=[Depends(require_api_key)])

SUPPORTED_AUDIO = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".webm", ".mp4"}
YOUTUBE_RE = re.compile(r"(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w\-]+")


class TTSRequest(BaseModel):
    text: str
    voice: str = ""
    model: str = ""


class YoutubeRequest(BaseModel):
    url: str
    save_to_vault: bool = True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _transcribe_bytes(audio_bytes: bytes, filename: str) -> str:
    files = {"file": (filename, audio_bytes, "audio/mpeg")}
    data = {"model": settings.whisper_model, "response_format": "text"}
    with httpx.Client(timeout=900) as client:
        resp = client.post(f"{settings.speaches_url}/v1/audio/transcriptions", files=files, data=data)
        resp.raise_for_status()
    return resp.text.strip()


def _save_youtube_note(url: str, title: str, transcript: str) -> bool:
    vault = Path(settings.obsidian_vault_path)
    yt_dir = vault / "knowledge" / "youtube"
    yt_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w\-]", "-", title[:50].lower())
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = yt_dir / f"{date_str}-{slug}.md"

    content = f"""---
tags: [youtube, transcripcion]
fecha: {date_str}
url: {url}
---

# {title}

{transcript}
"""
    filepath.write_text(content, encoding="utf-8")

    try:
        import subprocess
        repo = Path(settings.git_repo_path)
        rel = f"obsidian-vault/knowledge/youtube/{filepath.name}"
        subprocess.run(["git", "add", rel], cwd=repo, check=True, capture_output=True)
        r = subprocess.run(
            ["git", "commit", "-m", f"youtube: {filepath.name}"],
            cwd=repo, capture_output=True,
        )
        if r.returncode == 0:
            subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
        return True
    except Exception as e:
        logger.warning(f"Git push failed: {e}")
        return False


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    suffix = Path(file.filename or "audio.mp3").suffix.lower()
    if suffix not in SUPPORTED_AUDIO:
        raise HTTPException(400, f"Unsupported format: {suffix}")
    audio_bytes = await file.read()
    try:
        text = _transcribe_bytes(audio_bytes, file.filename or "audio.mp3")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Speaches error: {e}")
    return {"text": text}


@router.post("/tts")
async def text_to_speech(req: TTSRequest):
    voice = req.voice or settings.tts_voice
    model = req.model or settings.tts_model
    payload = {"input": req.text, "voice": voice, "model": model, "response_format": "mp3"}
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(f"{settings.speaches_url}/v1/audio/speech", json=payload)
            resp.raise_for_status()
        audio_bytes = resp.content
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Speaches TTS error: {e}")
    return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")


@router.post("/youtube")
async def transcribe_youtube(req: YoutubeRequest):
    if not YOUTUBE_RE.search(req.url):
        raise HTTPException(400, "URL de YouTube no válida")

    with tempfile.TemporaryDirectory() as tmp:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{tmp}/audio.%(ext)s",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "96",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(req.url, download=True)
                title = info.get("title", "youtube-video")
        except Exception as e:
            raise HTTPException(502, f"yt-dlp error: {e}")

        audio_path = Path(tmp) / "audio.mp3"
        if not audio_path.exists():
            raise HTTPException(500, "Audio download failed")

        audio_bytes = audio_path.read_bytes()

    try:
        transcript = _transcribe_bytes(audio_bytes, "audio.mp3")
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Transcription error: {e}")

    saved = False
    if req.save_to_vault:
        saved = _save_youtube_note(req.url, title, transcript)

    return {
        "title": title,
        "url": req.url,
        "transcript": transcript,
        "saved_to_vault": saved,
    }
