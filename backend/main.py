"""SongForge backend API."""

import os
import tempfile

from fastapi import FastAPI, UploadFile, File, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import storage
from app.models import PromptRequest, LyricsRequest, GenerateResponse
from app.music import engine
from app.music.generator import generate_from_prompt, generate_from_lyrics, generate_from_recording
from app.music.analysis import analyze_recording
from app.config import assert_quota

app = FastAPI(title="SongForge", version="0.1.0")


@app.exception_handler(PermissionError)
async def permission_handler(request, exc):
    return JSONResponse(status_code=403, content={"detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/data", StaticFiles(directory=storage.DATA_DIR), name="data")


def _client(header_value):
    return header_value if header_value else "anonymous"


def _render_and_store(client_id, L, R, meta):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp = f.name
    engine.write_wav(tmp, L, R)
    track_id, final, meta = storage.save_track(client_id, tmp, meta)
    return track_id, final, meta


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/tiers")
def tiers():
    from app.config import TIERS
    return TIERS


@app.get("/api/tracks", response_model=list)
def tracks(x_client_id: str | None = Header(default=None)):
    return storage.list_tracks(x_client_id or "anonymous")


@app.delete("/api/tracks/{track_id}")
def delete(track_id: str, x_client_id: str | None = Header(default=None)):
    ok = storage.delete_track(x_client_id or "anonymous", track_id)
    if not ok:
        raise HTTPException(404, "Track not found")
    return {"deleted": True}


@app.post("/api/generate/prompt", response_model=GenerateResponse)
def gen_prompt(req: PromptRequest, x_client_id: str | None = Header(default=None)):
    cid = _client(x_client_id)
    assert_quota(cid)
    L, R, meta = generate_from_prompt(req.prompt, duration_s=req.duration_s)
    track_id, _, meta = _render_and_store(cid, L, R, meta)
    return GenerateResponse(id=track_id, audio_url="/data/%s/%s" % (cid, meta["filename"]), meta=meta)


@app.post("/api/generate/lyrics", response_model=GenerateResponse)
def gen_lyrics(req: LyricsRequest, x_client_id: str | None = Header(default=None)):
    cid = _client(x_client_id)
    assert_quota(cid)
    L, R, meta = generate_from_lyrics(req.lyrics, duration_s=req.duration_s, genre_name=req.genre)
    track_id, _, meta = _render_and_store(cid, L, R, meta)
    return GenerateResponse(id=track_id, audio_url="/data/%s/%s" % (cid, meta["filename"]), meta=meta)


@app.post("/api/generate/recording")
async def gen_recording(
    file: UploadFile = File(...),
    genre: str | None = File(default=None),
    x_client_id: str | None = Header(default=None),
):
    cid = _client(x_client_id)
    assert_quota(cid)
    suffix = os.path.splitext(file.filename or "rec.wav")[1] or ".wav"
    if suffix.lower() != ".wav":
        raise HTTPException(400, "Only WAV recordings are supported. Record in the browser to convert automatically.")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(await file.read())
        tmp = f.name
    try:
        try:
            analysis = analyze_recording(tmp)
        except Exception as exc:
            raise HTTPException(400, "Could not analyze the recording: %s" % exc)
    finally:
        os.remove(tmp)
    L, R, meta = generate_from_recording(analysis, genre_name=genre)
    meta["recording_name"] = file.filename
    track_id, _, meta = _render_and_store(cid, L, R, meta)
    return GenerateResponse(id=track_id, audio_url="/data/%s/%s" % (cid, meta["filename"]), meta=meta)
