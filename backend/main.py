"""SongForge backend API."""

import os
import tempfile

from fastapi import FastAPI, UploadFile, File, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import storage, billing
from app.models import PromptRequest, LyricsRequest, GenerateResponse, CheckoutRequest
from app.music import engine
from app.music.generator import generate_from_prompt, generate_from_lyrics, generate_from_recording
from app.music.analysis import analyze_recording
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
    return TIERS


@app.get("/api/plans")
def plans():
    from app.config import TIERS
    return {"plans": TIERS, "providers": billing.providers_status()}


@app.get("/api/billing/status")
def billing_status(x_client_id: str | None = Header(default=None)):
    cid = _client(x_client_id)
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
def checkout(req: CheckoutRequest, x_client_id: str | None = Header(default=None)):
    cid = _client(x_client_id)
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
def mock_confirm(body: dict, x_client_id: str | None = Header(default=None)):
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
