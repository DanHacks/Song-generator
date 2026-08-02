"""Track storage: saves WAV + metadata per client, scoped for future user accounts."""

import datetime
import json
import os
import re
import uuid

DATA_DIR = os.environ.get("SONGFORGE_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))


def _safe_name(text, max_len=40):
    text = re.sub(r"[^a-zA-Z0-9 _-]", "", text).strip()
    text = re.sub(r"\s+", "_", text)
    return (text or "track")[:max_len]


def _client_dir(client_id):
    d = os.path.join(DATA_DIR, client_id)
    os.makedirs(d, exist_ok=True)
    return d


def save_track(client_id, wav_path, meta):
    """Move a rendered WAV into the client's storage and record its metadata."""
    cdir = _client_dir(client_id)
    track_id = uuid.uuid4().hex[:12]
    name = _safe_name(meta.get("prompt") or meta.get("recording_name") or meta.get("genre", "track"))
    filename = "%s_%s.wav" % (name, track_id)
    final = os.path.join(cdir, filename)
    os.replace(wav_path, final)
    meta["id"] = track_id
    meta["filename"] = filename
    meta["path"] = final
    meta["audio_url"] = "/data/%s/%s" % (client_id, filename)
    meta["created_at"] = datetime.datetime.utcnow().isoformat()
    with open(os.path.join(cdir, track_id + ".json"), "w") as f:
        json.dump(meta, f, indent=2, default=str)
    return track_id, final, meta


def list_tracks(client_id):
    cdir = _client_dir(client_id)
    out = []
    if not os.path.isdir(cdir):
        return out
    for fn in sorted(os.listdir(cdir), reverse=True):
        if fn.endswith(".json"):
            with open(os.path.join(cdir, fn)) as f:
                meta = json.load(f)
            out.append(meta)
    return out


def get_track_path(client_id, track_id):
    cdir = _client_dir(client_id)
    meta_path = os.path.join(cdir, track_id + ".json")
    if not os.path.exists(meta_path):
        return None, None
    with open(meta_path) as f:
        meta = json.load(f)
    return meta.get("path"), meta


def delete_track(client_id, track_id):
    path, meta = get_track_path(client_id, track_id)
    if not path:
        return False
    if os.path.exists(path):
        os.remove(path)
    os.remove(os.path.join(_client_dir(client_id), track_id + ".json"))
    return True


def save_tts(client_id, wav_path, meta):
    """Store a standalone TTS clip (not a track) under {client}/tts/."""
    cdir = _client_dir(client_id)
    tts_dir = os.path.join(cdir, "tts")
    os.makedirs(tts_dir, exist_ok=True)
    tts_id = uuid.uuid4().hex[:12]
    filename = "speech_%s.wav" % tts_id
    final = os.path.join(tts_dir, filename)
    os.replace(wav_path, final)
    meta["id"] = tts_id
    meta["filename"] = filename
    meta["audio_url"] = "/data/%s/tts/%s" % (client_id, filename)
    meta["created_at"] = datetime.datetime.utcnow().isoformat()
    return meta
