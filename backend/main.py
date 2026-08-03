"""SongForge backend API."""

import os
import tempfile

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import storage, billing, auth
from app.models import (
    PromptRequest,
    LyricsRequest,
    TTSRequest,
    GenerateResponse,
    CheckoutRequest,
    SignupRequest,
    LoginRequest,
)
from app.music import engine
from app.music.generator import generate_from_prompt, generate_from_lyrics, generate_from_recording
from app.music.analysis import analyze_recording
from app.music.provider import get_provider, MusicGenUnavailable
from app.music.director import direct
from app.config import assert_quota, TIERS

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


def _client(authorization: str | None, header_value: str | None):
    return auth.resolve_client(authorization, header_value)


def _render_and_store(client_id, L, R, meta):
    # Write in DATA_DIR so os.replace() stays on the same filesystem (avoids
    # cross-device link errors when /tmp is a separate mount, e.g. on AWS).
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=storage.DATA_DIR, delete=False) as f:
        tmp = f.name
    engine.write_wav(tmp, L, R)
    track_id, final, meta = storage.save_track(client_id, tmp, meta)
    return track_id, final, meta


@app.get("/api/genres")
def genres_endpoint():
    """Genre catalog with icons for the UI picker."""
    from app.music.genres import GENRE_CATALOG, GENRES
    return {"genres": list(GENRE_CATALOG.values()), "supported": list(GENRES.keys())}


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/tiers")
def tiers():
    return TIERS


@app.get("/api/plans")
def plans():
    from app.config import TIERS
    return {"plans": TIERS, "providers": billing.providers_status()}


@app.get("/api/engine")
def engine_status():
    """Which generation engine would be active now (musicgen primary, samples fallback)."""
    from app.music.provider import get_provider, MusicGenUnavailable
    try:
        p = get_provider()
    except MusicGenUnavailable:
        p = None
    return {
        "engine": p.name if p else "None",
        "device": getattr(p, "device", None),
        "model": getattr(p, "model_name", None),
        "capabilities": p.capabilities if p else {},
    }


@app.get("/api/engines")
def engines_list():
    """Available engines for the UI engine switch."""
    from app.music.provider import get_provider, get_engines

    return get_engines()


@app.post("/api/auth/signup")
def auth_signup(req: SignupRequest):
    try:
        user = auth.signup(req.username, req.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {
        "username": user["username"],
        "client_id": user["client_id"],
        "token": auth.encode_token(user["username"]),
    }


@app.post("/api/auth/login")
def auth_login(req: LoginRequest):
    user = auth.verify(req.username, req.password)
    if not user:
        raise HTTPException(401, "Invalid username or password.")
    return {
        "username": user["username"],
        "client_id": user["client_id"],
        "token": auth.encode_token(user["username"]),
    }


@app.get("/api/auth/me")
def auth_me(authorization: str | None = Header(default=None)):
    user = auth.user_from_token(authorization[7:].strip()) if authorization and authorization.lower().startswith("bearer ") else None
    if not user:
        raise HTTPException(401, "Not logged in.")
    return {"username": user["username"], "client_id": user["client_id"]}


@app.get("/api/billing/status")
def billing_status(authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    cid = _client(authorization, x_client_id)
    sub = billing.get_subscription(cid)
    tier = TIERS[billing.active_tier_name(cid)]
    return {
        "tier": billing.active_tier_name(cid),
        "label": tier["label"],
        "expires_at": sub.get("expires_at"),
        "max_duration_s": tier["max_duration_s"],
        "stems": tier["stems"],
        "usage": billing.usage(cid),
        "payments": sub.get("payments", []),
    }


@app.post("/api/billing/checkout")
def checkout(req: CheckoutRequest, authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    cid = _client(authorization, x_client_id)
    try:
        if req.provider == "mock":
            record = billing.mock_checkout(cid, req.plan)
            return {"provider": "mock", "checkout_id": record["id"], "status": record["status"],
                    "amount_kes": record["amount"], "plan": req.plan}
        if req.provider == "mpesa":
            if not req.phone:
                raise HTTPException(400, "Phone number is required for M-Pesa.")
            result = billing.initiate_mpesa(cid, req.plan, req.phone)
            record = {
                "provider": "mpesa",
                "merchant_request_id": result.get("MerchantRequestID"),
                "checkout_request_id": result.get("CheckoutRequestID"),
                "response_code": result.get("ResponseCode"),
                "response_desc": result.get("ResponseDescription"),
                "plan": req.plan,
                "status": "pending",
                "amount_kes": TIERS[req.plan]["price_kes"],
            }
            billing._ensure_dirs()
            import json
            with open(os.path.join(billing.CHECKOUT_DIR, record["merchant_request_id"] + ".json"), "w") as f:
                json.dump({**record, "client_id": cid}, f)
            return record
        if req.provider == "stripe":
            session = billing.create_stripe_checkout(cid, req.plan)
            return {"provider": "stripe", "session_id": session["id"], "url": session["url"], "plan": req.plan}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "Payment initiation failed: %s" % exc)
    raise HTTPException(400, "Unsupported provider.")


@app.post("/api/billing/mock/confirm")
def mock_confirm(body: dict, authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    checkout_id = body.get("checkout_id")
    if not checkout_id:
        raise HTTPException(400, "checkout_id is required.")
    record = billing.mock_confirm(checkout_id)
    if not record:
        raise HTTPException(404, "Checkout not found.")
    return {"status": record["status"], "tier": record["plan"], "expires_at": billing.get_subscription(record["client_id"])["expires_at"]}


@app.post("/api/billing/mpesa/callback")
async def mpesa_callback(request: Request):
    payload = await request.json()
    return billing.handle_mpesa_callback(payload)


@app.post("/api/billing/stripe/webhook")
async def stripe_webhook(request: Request):
    raw = await request.body()
    sig = request.headers.get("stripe-signature")
    result = billing.handle_stripe_webhook(raw, sig)
    if result is None:
        raise HTTPException(400, "Invalid signature.")
    return result


@app.get("/api/tracks", response_model=list)
def tracks(authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    return storage.list_tracks(_client(authorization, x_client_id))


@app.delete("/api/tracks/{track_id}")
def delete(track_id: str, authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    ok = storage.delete_track(_client(authorization, x_client_id), track_id)
    if not ok:
        raise HTTPException(404, "Track not found")
    return {"deleted": True}


def _generate_with_fallback(fn, prompt, req, settings=None):
    """Run the engine the client asked for, falling back to the fast engine.

    req.engine:
      - "fast"   -> always the hybrid sample+synth engine (<1s, offline).
      - "musicgen" -> MusicGen only; falls back to samples if unavailable.
      - "auto"   -> MusicGen primary (if available), samples fallback.
    """
    from app.music.provider import get_provider, MusicGenUnavailable

    settings = settings or {}
    choice = getattr(req, "engine", "auto") or "auto"
    try:
        if choice == "fast":
            provider = get_provider("fast")
            L, R, meta = provider.generate(prompt, {
                "duration_s": req.duration_s,
                "mode": settings.get("mode", "prompt"),
                **settings,
            })
            return L, R, meta
        provider = get_provider("musicgen")
        # expand the prompt through SongDirector for a rich condition
        expanded = direct(prompt, duration_s=req.duration_s,
                          overrides={"genre": settings.get("genre")})
        mg_prompt = expanded["prompt_mg"]
        meta = {
            "mode": settings.get("mode", "prompt"),
            "director": expanded["spec"],
        }
        L, R, meta = provider.generate(mg_prompt, {
            "duration_s": req.duration_s,
            "mode": settings.get("mode", "prompt"),
            "_meta": meta,
            **settings,
        })
        return L, R, meta
    except (MusicGenUnavailable, Exception) as exc:
        if choice == "musicgen":
            print("[warn] MusicGen unavailable, falling back to fast engine: %s" % exc)
        elif not isinstance(exc, MusicGenUnavailable):
            print("[warn] %s generation failed, falling back: %s" % (choice, exc))
    return fn(req)


@app.post("/api/direct")
def direct_endpoint(req: PromptRequest):
    """Expand a prompt into a full SongDirector production brief (no audio)."""
    return direct(req.prompt, duration_s=req.duration_s)


@app.post("/api/generate/prompt", response_model=GenerateResponse)
def gen_prompt(req: PromptRequest, authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    cid = _client(authorization, x_client_id)
    assert_quota(cid)
    L, R, meta = _generate_with_fallback(
        lambda r: generate_from_prompt(r.prompt, duration_s=r.duration_s),
        req.prompt, req, settings={"mode": "prompt", "genre": req.genre},
    )
    track_id, _, meta = _render_and_store(cid, L, R, meta)
    return GenerateResponse(id=track_id, audio_url="/data/%s/%s" % (cid, meta["filename"]), meta=meta)


@app.post("/api/generate/lyrics", response_model=GenerateResponse)
def gen_lyrics(req: LyricsRequest, authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    cid = _client(authorization, x_client_id)
    assert_quota(cid)
    if req.vocal_style in ("singing", "spoken"):
        # vocals pipeline lives in the hybrid engine
        L, R, meta = generate_from_lyrics(
            req.lyrics, duration_s=req.duration_s, genre_name=req.genre,
            vocal_style=req.vocal_style or "none", voice=req.voice,
        )
    else:
        L, R, meta = _generate_with_fallback(
            lambda r: generate_from_lyrics(r.lyrics, duration_s=r.duration_s, genre_name=r.genre),
            req.lyrics, req, settings={"mode": "lyrics"},
        )
    track_id, _, meta = _render_and_store(cid, L, R, meta)
    return GenerateResponse(id=track_id, audio_url="/data/%s/%s" % (cid, meta["filename"]), meta=meta)


@app.post("/api/tts")
def gen_tts(req: TTSRequest, authorization: str | None = Header(default=None), x_client_id: str | None = Header(default=None)):
    cid = _client(authorization, x_client_id)
    from app.music import vocals

    voice = req.voice or vocals.DEFAULT_VOICE
    audio, dur = vocals.render_tts(req.text, voice=voice, rate=req.rate, pitch=req.pitch)
    if audio is None:
        raise HTTPException(502, "Voice synthesis unavailable. Check your internet connection.")
    import wave

    import numpy as np
    # Write in DATA_DIR so storage.save_tts()'s os.replace() stays on the same
    # filesystem (avoids cross-device link errors on AWS/tmpfs).
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=storage.DATA_DIR, delete=False) as f:
        tmp = f.name
    try:
        with wave.open(tmp, "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(vocals.SR)
            p = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
            f.writeframes(p.tobytes())
        meta = {
            "mode": "tts",
            "text": req.text[:500],
            "voice": voice,
            "rate": req.rate or "+0%",
            "pitch": req.pitch or "+0Hz",
            "duration_s": dur,
        }
        meta = storage.save_tts(cid, tmp, meta)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return {"id": meta["id"], "audio_url": meta["audio_url"], "meta": meta}


@app.post("/api/generate/recording")
async def gen_recording(
    file: UploadFile = File(...),
    genre: str | None = File(default=None),
    authorization: str | None = Header(default=None),
    x_client_id: str | None = Header(default=None),
):
    cid = _client(authorization, x_client_id)
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


# Serve the built React frontend (must be mounted last so /api and /data win).
_FRONTEND_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")
if os.path.isdir(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
