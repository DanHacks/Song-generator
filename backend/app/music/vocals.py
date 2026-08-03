"""Real neural vocals and natural text-to-speech via edge-tts (no API key).

Voice synthesis runs through Microsoft's free Edge neural voices, decoded with
ffmpeg into 44.1 kHz mono float32. Singing mode aligns each word to a composed
melody note using autocorrelation pitch detection + a phase-vocoder
time-stretch and pitch-shift, giving an auto-tune style sung vocal.

Requires network access at runtime; every render degrades gracefully to None
so tracks still generate offline.
"""

import asyncio
import hashlib
import os
import subprocess

import numpy as np

from .scales import midi_to_freq

SR = 44100

DEFAULT_VOICE = "en-KE-AsiliaNeural"

VOICES = [
    "en-KE-AsiliaNeural",
    "en-NG-EzinneNeural",
    "en-IN-NeerjaNeural",
    "en-US-JennyNeural",
    "en-US-EmmaNeural",
    "en-GB-SoniaNeural",
    "en-ZA-LeahNeural",
    "en-TZ-ImaniNeural",
]

CACHE_DIR = os.environ.get(
    "SONGFORGE_TTS_CACHE",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "tts_cache"),
)

_MP3_CACHE = {}


def _run_sync(coro):
    """Run an async coroutine from sync code, tolerating an existing loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import threading

    result = {}

    def _t():
        result["r"] = asyncio.run(coro)

    th = threading.Thread(target=_t)
    th.start()
    th.join()
    return result["r"]


def _cache_path(text, voice, rate, pitch):
    key = hashlib.md5(("%s|%s|%s|%s" % (text, voice, rate, pitch)).encode("utf-8")).hexdigest()
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, key + ".mp3")


async def _synth(text, voice, rate, pitch):
    import edge_tts

    com = edge_tts.Communicate(
        text, voice, rate=rate or "+0%", pitch=pitch or "+0Hz", boundary="WordBoundary"
    )
    audio = bytearray()
    words = []
    async for chunk in com.stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            words.append(
                {
                    "word": chunk["text"],
                    "start_s": chunk["offset"] / 1e7,
                    "dur_s": chunk["duration"] / 1e7,
                }
            )
    return bytes(audio), words


def tts_line(text, voice=DEFAULT_VOICE, rate="+0%", pitch="+0Hz"):
    """Synthesize a line. Returns (audio float32 mono SR, word events).

    edge-tts is tried first; if it is unreachable (no network) we fall back to
    the on-device Parler-TTS model so vocals still render offline.
    """
    path = _cache_path(text, voice, rate, pitch)
    mp3 = _MP3_CACHE.get(path)
    words = None
    if mp3 is None:
        if os.path.exists(path):
            with open(path, "rb") as f:
                mp3 = f.read()
        else:
            mp3, words = _run_sync(_synth(text, voice, rate, pitch))
            if mp3:
                with open(path, "wb") as f:
                    f.write(mp3)
                _MP3_CACHE[path] = mp3
    if words is None:
        words = []
    audio = _decode_mp3(mp3) if mp3 else None
    if audio is None:
        audio = _local_tts(text, voice)
    if audio is None:
        return None, []
    return audio, words


_BASE_F0_CACHE = {}


def _local_tts(text, voice):
    """On-device TTS fallback (Parler) when edge-tts has no network."""
    try:
        from . import vocals_local

        audio, _ = vocals_local.synthetic_line(text, voice=voice, sr=SR)
        return audio
    except Exception as exc:
        _local_tts.last_error = exc
        return None


_local_tts.last_error = None


def _voice_base_f0(voice):
    """Estimate the voice's natural fundamental (Hz), cached per voice."""
    if voice in _BASE_F0_CACHE:
        return _BASE_F0_CACHE[voice]
    base = 190.0
    audio, _ = tts_line("Mama Aaaa", voice, "+0%", "+0Hz")
    if audio is not None:
        est = estimate_f0(audio, SR)
        if est is not None:
            base = est
    _BASE_F0_CACHE[voice] = base
    return base


def _decode_mp3(mp3):
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"],
            input=mp3,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            return None
        data = np.frombuffer(proc.stdout, dtype=np.float32).copy()
        if data.size == 0:
            return None
        return data
    except Exception:
        return None


def _resample(x, m):
    """Linear resample array x to length m (changes pitch, preserves time)."""
    n = len(x)
    if n == 0:
        return x.copy()
    if m == n:
        return x.copy()
    if m < 1:
        return x[:0].copy()
    idx = np.linspace(0, n - 1, int(m))
    return np.interp(idx, np.arange(n), x)


def _phase_vocoder(x, ratio):
    """Time-stretch x by ratio (ratio>1 => longer) without pitch change."""
    if ratio <= 0:
        return x[:0].copy()
    if abs(ratio - 1.0) < 1e-3:
        return x.copy()
    n = len(x)
    if n < 64:
        return x.copy()
    win = 1024
    hop = 256
    syn_hop = max(int(round(hop * ratio)), 1)
    if n <= win:
        x = np.concatenate([x, np.zeros(win - n, dtype=np.float32)])
        n = win
    window = np.hanning(win).astype(np.float32)
    n_out = int(round(n * ratio)) + win
    out = np.zeros(n_out, dtype=np.float32)
    accum = np.zeros(n_out, dtype=np.float32)
    bins = np.arange(win // 2 + 1, dtype=np.float64)
    omega = 2 * np.pi * bins * hop / win
    spec = np.fft.rfft(x[:win] * window)
    mag = np.abs(spec)
    phase = np.angle(spec)
    last_phase = phase.copy()
    synth_phase = phase.copy()
    idx = 0
    syn_idx = 0
    while idx + win < n:
        frame = x[idx:idx + win] * window
        spec = np.fft.rfft(frame)
        mag = np.abs(spec)
        phase = np.angle(spec)
        delta = phase - last_phase
        delta -= omega
        delta -= 2 * np.pi * np.round(delta / (2 * np.pi))
        true_advance = omega + delta
        synth_phase = (synth_phase + true_advance * syn_hop / hop) % (2 * np.pi)
        synth = mag * np.exp(1j * synth_phase)
        frame_out = np.fft.irfft(synth, win).astype(np.float32) * window
        end = min(syn_idx + win, n_out)
        out[syn_idx:end] += frame_out[:end - syn_idx]
        accum[syn_idx:end] += window[:end - syn_idx]
        last_phase = phase
        idx += hop
        syn_idx += syn_hop
    np.divide(out, accum, out=out, where=accum > 1e-8)
    return out.astype(np.float32)


def time_stretch(x, target_len):
    """Time-stretch x to target_len samples preserving pitch."""
    n = len(x)
    if n <= 1:
        return x.copy()
    ratio = target_len / n
    return _phase_vocoder(x, ratio)


def pitch_shift(x, sr, semitones):
    """Shift pitch by semitones preserving duration."""
    if abs(semitones) < 0.05:
        return x.copy()
    factor = 2.0 ** (semitones / 12.0)
    stretched = _phase_vocoder(x, factor)
    return _resample(stretched, len(x))


def estimate_f0(x, sr):
    """YIN-style pitch estimate (cumulative mean normalized square difference)
    on the most energetic window. Returns Hz or None."""
    if x is None or len(x) < 512:
        return None
    x = x.astype(np.float64)
    win = min(2048, len(x))
    step = 1024
    best_e = 0.0
    best_start = 0
    for start in range(0, max(len(x) - win, 1), step):
        seg = x[start:start + win]
        e = np.dot(seg, seg)
        if e > best_e:
            best_e = e
            best_start = start
    seg = x[best_start:best_start + win]
    if best_e < 1e-6:
        return None
    seg = seg.astype(np.float64) - seg.mean()
    n = len(seg)
    p = 1 << (2 * n).bit_length()
    segf = np.zeros(p)
    segf[:n] = seg
    F = np.fft.rfft(segf)
    r = np.fft.irfft(np.abs(F) ** 2, p)[:n]
    r = np.maximum(r, 0.0)
    e = float(np.dot(seg, seg))
    if e <= 1e-9:
        return None
    d = np.maximum(2.0 * (e - r), 0.0)
    tau_min = int(sr / 500)
    tau_max = min(n // 2 - 1, int(sr / 60))
    if tau_max <= tau_min:
        return None
    cum = np.cumsum(d[1:])
    cmnd = np.zeros(n)
    cmnd[1:] = d[1:] * np.arange(1, n) / np.maximum(cum, 1e-12)
    threshold = 0.1
    tau = None
    for t in range(tau_min, tau_max):
        if cmnd[t] < threshold:
            tau = t
            break
    if tau is None:
        tau = tau_min + int(np.argmin(cmnd[tau_min:tau_max]))
    # walk to the bottom of the dip, then parabolic interpolation
    lo, hi = tau - 2, tau + 2
    while lo > tau_min and cmnd[lo - 1] < cmnd[lo]:
        lo -= 1
    while hi + 1 < tau_max and cmnd[hi + 1] < cmnd[hi]:
        hi += 1
    if cmnd[lo] <= 0:
        tau = lo
    else:
        y0, y1, y2 = cmnd[lo], cmnd[(lo + hi) // 2], cmnd[hi]
        if lo < hi:
            tau = lo + (hi - lo) * 0.5
    f0 = sr / tau
    if not 60 <= f0 <= 500:
        return None
    return float(f0)


def _word_targets(words, notes, line_dur_s):
    """Map TTS word events to target (start_s, dur_s, midi_or_None).

    Notes span line_dur_s; a word's target window is proportional to where it
    falls in the speech, and its target note is the melody note whose beat
    window contains the word's midpoint.
    """
    if not words:
        return []
    speech_end = max(w["start_s"] + w["dur_s"] for w in words)
    if speech_end <= 0:
        return []
    note_windows = []
    cum = 0.0
    for note, beats in notes:
        note_windows.append((note, cum, cum + beats * (line_dur_s / max(sum(b for _, b in notes), 1e-9))))
        cum += beats * (line_dur_s / max(sum(b for _, b in notes), 1e-9))
    out = []
    for w in words:
        frac_start = w["start_s"] / speech_end
        frac_dur = w["dur_s"] / speech_end
        t_start = frac_start * line_dur_s
        t_dur = frac_dur * line_dur_s
        mid = t_start + t_dur / 2
        target = None
        for note, ns, ne in note_windows:
            if ns <= mid <= ne:
                target = note
                break
        out.append({"start_s": t_start, "dur_s": t_dur, "note": target, "word": w["word"]})
    return out


def render_singing(lines, voice=DEFAULT_VOICE, bpm=112, seed=None, sr=SR):
    """Render sung vocals for a list of line dicts {text, notes}.

    Each line is synthesized with the neural voice pitched (via edge-tts) to
    the melody's register, then each word is time-stretched to its target beat
    window and fine-tuned to its melody note with a small DSP pitch shift.
    Returns float32 mono or None.
    """
    beat_s = 60.0 / max(bpm, 1)
    base_f0 = _voice_base_f0(voice)
    out = []
    for line in lines:
        text = (line.get("text") or "").strip()
        notes = line.get("notes") or []
        if not text or not notes:
            continue
        total_beats = sum(b for _, b in notes)
        if total_beats <= 0:
            continue
        line_dur_s = total_beats * beat_s
        note_midis = [m for m, _ in notes if m is not None]
        if not note_midis:
            continue
        line_note = float(np.median(note_midis))
        line_freq = midi_to_freq(line_note)
        pitch_hz = int(round(line_freq - base_f0))
        pitch_hz = max(-100, min(100, pitch_hz))
        pitch_str = "%+dHz" % pitch_hz
        audio, word_events = tts_line(text, voice, "+0%", pitch_str)
        if audio is None or len(audio) < 512:
            continue
        if not word_events:
            target_n = int(line_dur_s * sr)
            audio = time_stretch(audio, target_n)
            out.append(audio)
            out.append(np.zeros(int(0.03 * sr), dtype=np.float32))
            continue
        targets = _word_targets(word_events, notes, line_dur_s)
        parts = []
        for t in targets:
            seg = _seg_at(audio, word_events, t)
            if seg is None or len(seg) < 64:
                continue
            src = seg
            if t["note"] is not None:
                semis = 12 * np.log2(midi_to_freq(t["note"]) / line_freq)
                semis = float(np.clip(semis, -5, 5))
                if abs(semis) >= 0.05:
                    src = pitch_shift(src, sr, semis)
            target_n = int(t["dur_s"] * sr)
            if target_n > 0 and abs(target_n - len(src)) > 32:
                src = time_stretch(src, target_n)
            parts.append(src)
            parts.append(np.zeros(int(0.015 * sr), dtype=np.float32))
        if parts:
            line_audio = np.concatenate(parts)
            line_audio = line_audio[: int(line_dur_s * sr) + int(0.3 * sr)]
            out.append(line_audio)
            out.append(np.zeros(int(0.12 * sr), dtype=np.float32))
    if not out:
        return None
    return np.concatenate(out).astype(np.float32)


def _seg_at(audio, word_events, t):
    """Extract the audio segment for a target by matching the closest word event."""
    best = None
    best_d = 1e18
    for w in word_events:
        d = abs(w["start_s"] - t["start_s"])
        if d < best_d:
            best_d = d
            best = w
    if best is None:
        return None
    s0 = int(best["start_s"] * SR)
    s1 = min(int((best["start_s"] + best["dur_s"]) * SR), len(audio))
    s0 = min(s0, s1)
    return audio[s0:s1]


def render_spoken(lines, voice=DEFAULT_VOICE, bpm=112, sr=SR):
    """Render spoken/rap-style vocals: each line stretched to its beat window."""
    beat_s = 60.0 / max(bpm, 1)
    out = []
    for line in lines:
        text = (line.get("text") or "").strip()
        notes = line.get("notes") or []
        if not text or not notes:
            continue
        total_beats = sum(b for _, b in notes)
        line_dur_s = total_beats * beat_s
        audio, _ = tts_line(text, voice)
        if audio is None or len(audio) < 512:
            continue
        target_n = int(line_dur_s * sr)
        audio = time_stretch(audio, target_n)
        out.append(audio)
        out.append(np.zeros(int(0.12 * sr), dtype=np.float32))
    if not out:
        return None
    return np.concatenate(out).astype(np.float32)


def render_tts(text, voice=DEFAULT_VOICE, rate="+0%", pitch="+0Hz", sr=SR):
    """Plain natural text-to-speech: concatenated neural speech, no DSP."""
    audio, _ = tts_line(text, voice, rate, pitch)
    if audio is None:
        return None, 0.0
    return audio, round(len(audio) / sr, 2)


def mix_vocals(L, R, vocal, start_s=0.0, level=0.85, sr=SR):
    """Blend a mono vocal track into a stereo instrumental.

    Duck the instrumental slightly where the vocal is active, add the vocal at
    center, then normalize. Returns new (L, R) float arrays.
    """
    n = len(L)
    if vocal is None or len(vocal) == 0:
        return L, R
    v = np.zeros(n, dtype=np.float32)
    s0 = int(start_s * sr)
    if s0 >= n:
        return L, R
    m = min(len(vocal), n - s0)
    v[s0:s0 + m] = vocal[:m]
    v = np.clip(v, -1.0, 1.0)
    v *= level
    # RMS envelope to gate the ducking
    win = max(int(0.05 * sr), 1)
    nw = n // win
    if nw > 0:
        power = np.add.reduceat(v[:nw * win] ** 2, np.arange(0, nw * win, win)) / win
        rms = np.sqrt(power)
        env = np.interp(np.arange(n), np.arange(0, nw * win, win)[:len(rms)], rms)
        norm = max(float(np.max(rms)), 1e-9)
        duck = 0.35 * np.clip(env / norm, 0.0, 1.0)
        L = L * (1.0 - duck)
        R = R * (1.0 - duck)
    L = L + v
    R = R + v
    peak = max(float(np.max(np.abs(L))), float(np.max(np.abs(R))), 1e-9)
    L = L / peak * 0.9
    R = R / peak * 0.9
    return L, R
