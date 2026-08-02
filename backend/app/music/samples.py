"""Real-sample library + groove humanization for the arrangement engine.

Loads royalty-free WAV one-shots from ``assets/samples`` (or
``SONGFORGE_SAMPLES``) and plays them in the sequencer. When a category has no
samples it transparently falls back to the synth engine, so the app keeps
working fully offline with the existing DSP sounds.

Directory layout (see scripts/fetch_samples.sh):

    assets/samples/
      drums/{kick,snare,hihat,openhat,clap,shaker,cowbell,tom,crash}/*.wav
      bass/      (note-named one-shots, e.g. C2.wav, F#2_02.wav)
      keys/      (piano / electric keys one-shots)
      guitars/   (plucked guitar one-shots)
      strings/   (sustained string/bowed notes)
      ir/        (room impulse responses for convolution reverb)
"""

import os
import re
import glob
import random

import numpy as np

from . import engine
from .scales import midi_to_name

SAMPLES_DIR = os.environ.get(
    "SONGFORGE_SAMPLES",
    os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "assets", "samples")),
)

_DRUM_DIRS = {
    "kick": "drums/kick",
    "snare": "drums/snare",
    "clap": "drums/clap",
    "hat": "drums/hihat",
    "openhat": "drums/openhat",
    "shaker": "drums/shaker",
    "cowbell": "drums/cowbell",
    "tom": "drums/tom",
    "crash": "drums/crash",
    "perc": "drums/perc",
}

_PITCHED_DIRS = {
    "bass": "bass",
    "keys": "keys",
    "guitar": "guitars",
    "strings": "strings",
    "pluck": "keys",
}

_cache = {}        # path -> np.float32 mono at engine.SR
_cat_files = {}    # category -> [paths]
_note_map = {}     # category -> {midi: [paths]}
_rr = {}           # category -> next round-robin index
_ir = {}           # path -> np.float32 mono IR


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _all_wavs(subdir):
    base = os.path.join(SAMPLES_DIR, subdir)
    if not os.path.isdir(base):
        return []
    return sorted(glob.glob(os.path.join(base, "**", "*.wav"), recursive=True))


def _load(path):
    if path in _cache:
        return _cache[path]
    try:
        audio = engine.read_wav_mono(path)
    except Exception:
        audio = None
    _cache[path] = audio
    return audio


def category_files(category):
    """All sample paths for a drum category (empty list when none exist)."""
    if category in _cat_files:
        return _cat_files[category]
    sub = _DRUM_DIRS.get(category, category)
    files = _all_wavs(sub)
    _cat_files[category] = files
    return files


def available():
    """Map of category -> number of loaded samples (for meta/debug)."""
    out = {}
    for c in _DRUM_DIRS:
        n = len(category_files(c))
        if n:
            out[c] = n
    for c in _PITCHED_DIRS:
        n = len(_pitched_files(c))
        if n:
            out[c] = n
    return out


def _pitch_re(p):
    return re.match(r"([A-G])([#b]?)(-?\d+)", p, re.IGNORECASE)


def _file_midi(path):
    base = os.path.splitext(os.path.basename(path))[0]
    m = _pitch_re(base)
    if not m:
        return None
    return _name_to_midi((m.group(1) + m.group(2)).upper(), int(m.group(3)))


def _name_to_midi(name, octave=4):
    from .scales import name_to_midi
    return name_to_midi(name + str(octave))


def _pitched_files(category):
    if category in _note_map:
        return _note_map[category]
    sub = _PITCHED_DIRS.get(category, category)
    files = _all_wavs(sub)
    mapping = {}
    for p in files:
        midi = _file_midi(p)
        if midi is not None:
            mapping.setdefault(midi, []).append(p)
    _note_map[category] = mapping
    return mapping


# ---------------------------------------------------------------------------
# One-shot drum hits with round-robin
# ---------------------------------------------------------------------------

def drum(category, velocity=1.0, seed=None):
    """Return a one-shot drum hit as float32 mono, or None to fall back to synth.

    Round-robins across the category's samples and applies a mild velocity
    gain (the caller usually adds its own humanization too).
    """
    files = category_files(category)
    if not files:
        return None
    idx = _rr.get(category, 0)
    _rr[category] = idx + 1
    audio = _load(files[idx % len(files)])
    if audio is None:
        return None
    audio = audio * velocity
    return audio


# ---------------------------------------------------------------------------
# Pitched one-shots (bass / keys / guitars / strings)
# ---------------------------------------------------------------------------

def note_audio(category, midi, duration_s=1.0, velocity=1.0, seed=None):
    """Play a pitched sample for ``midi``, pitch-shifting the nearest available
    note (resample = fast pitch+duration change, right for one-shots). Returns
    float32 mono or None to fall back to synth.
    """
    mapping = _pitched_files(category)
    if not mapping:
        return None
    avail = sorted(mapping.keys())
    nearest = min(avail, key=lambda m: abs(m - midi))
    files = mapping[nearest]
    idx = _rr.get(category, 0)
    _rr[category] = idx + 1
    audio = _load(files[idx % len(files)])
    if audio is None:
        return None
    semis = midi - nearest
    if abs(semis) > 0.01:
        audio = _resample_pitch(audio, semis)
    audio = audio * velocity
    return audio


def _resample_pitch(x, semitones):
    """Shift pitch by resampling (also changes duration) — fast and natural
    for percussive/short one-shots."""
    if abs(semitones) < 0.01:
        return x
    factor = 2.0 ** (semitones / 12.0)
    n_out = max(int(len(x) / factor), 1)
    idx = np.linspace(0, len(x) - 1, n_out)
    return np.interp(idx, np.arange(len(x)), x).astype(np.float32)


# ---------------------------------------------------------------------------
# Convolution reverb with real IRs
# ---------------------------------------------------------------------------

def ir_files():
    return _all_wavs("ir")


def load_ir(path):
    if path in _ir:
        return _ir[path]
    audio = _load(path)
    _ir[path] = audio
    return audio


# ---------------------------------------------------------------------------
# Humanization helpers
# ---------------------------------------------------------------------------

def velocity_jitter(base, rng, amount=0.12):
    """±amount relative velocity jitter, clamped to a usable range."""
    return max(0.55, min(1.2, base * (1 + rng.uniform(-amount, amount))))


def timing_jitter(t_s, rng, max_ms=18.0):
    """Micro-timing humanization in milliseconds (keeps the grid musical)."""
    return t_s + rng.uniform(-max_ms, max_ms) / 1000.0


def swing_time(step_frac, swing=0.0):
    """Swing an 8th/16th note position. swing in [0,1); 0.5 = no swing."""
    if swing <= 0:
        return 0.0
    offset = step_frac % 1.0
    if offset == 0.5:  # the off-8th gets pushed late
        return (swing - 0.5) * (step_frac and 1.0)
    return 0.0
