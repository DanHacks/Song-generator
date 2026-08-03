"""Local on-device TTS fallback (Parler-TTS) used when edge-tts has no network.

Kept optional: the heavy model is loaded lazily once and only when edge-tts
fails, so machines with internet never pay the cost. Run once (online) to fetch:

    pip install -q "parler-tts"

then generation falls back to on-device speech automatically when Microsoft's
edge-tts is unreachable.
"""

import os

import numpy as np

from .scales import midi_to_freq  # noqa: F401  (kept for parity with vocals)

# Parler speaker descriptions, keyed by the same voice ids used for edge-tts.
_DESCRIPTIONS = {
    "en-KE-AsiliaNeural": "A Kenyan woman speaks clearly with a friendly, warm tone and a subtle East African accent.",
    "en-NG-EzinneNeural": "A Nigerian woman speaks with bright energy and a gentle West African accent.",
    "en-IN-NeerjaNeural": "An Indian woman speaks in a calm, warm manner with a soft South Asian accent.",
    "en-TZ-ImaniNeural": "A Tanzanian woman speaks softly with a light East African accent.",
    "en-ZA-LeahNeural": "A South African woman speaks with a steady, pleasant tone.",
    "en-US-JennyNeural": "An American woman reads clearly in a neutral, natural tone.",
    "en-US-EmmaNeural": "An American woman speaks enthusiastically in a bright, clear voice.",
    "en-GB-SoniaNeural": "A British woman speaks in a poised, crisp Received Pronunciation.",
    "_default": "A woman speaks clearly and naturally in a calm, friendly tone.",
}

_pipe = None
_ready = False


def _load():
    """Load the Parler TTS pipeline once (slow on first call)."""
    global _pipe, _ready
    if _ready:
        return _pipe is not None
    model_id = os.environ.get("SONGFORGE_TTS_MODEL", "parler-tts/parler-tts-mini-v1")
    try:
        import torch
        from parler_tts import ParlerTTSForConditionalGeneration
        from transformers import AutoTokenizer
    except Exception as exc:  # deps missing
        print("[vocals_local] Parler-TTS unavailable (missing deps): %s" % exc)
        _ready = True
        return False
    try:
        pipe = ParlerTTSForConditionalGeneration.from_pretrained(model_id).to("cpu")
        tok = AutoTokenizer.from_pretrained(model_id)
    except Exception as exc:  # e.g. no network to download the model
        print("[vocals_local] failed to load %s: %s" % (model_id, exc))
        _ready = True
        return False
    pipe.eval()
    pipe.grammar = None
    _pipe = (pipe, tok)
    _ready = True
    return True


def synth_line(text, voice="default", sr=44100.0):
    """Synthesize ``text`` on-device. Returns (float32 mono @ sr, None) or (None, None)."""
    if not _load():
        return None, None
    pipe, tok = _pipe
    if voice not in _DESCRIPTIONS:
        voice = "default"
    description = _DESCRIPTIONS[voice]
    import torch

    with torch.no_grad():
        input_ids = tok(text, return_tensors="pt").input_ids
        prompt_ids = tok(description, return_tensors="pt").input_ids
        out = pipe.generate(input_ids=input_ids, prompt_input_ids=prompt_ids, max_new_tokens=200)
    audio = out[0].cpu().numpy().astype(np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=0)
    model_sr = 16000.0
    if sr != model_sr:
        audio = _resample(audio, model_sr, sr)
    return audio, sr


def _resample(x, src, dst):
    n = int(round(len(x) * dst / src))
    idx = np.linspace(0, len(x) - 1, n)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)