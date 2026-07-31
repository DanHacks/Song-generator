"""Analysis of uploaded recordings: tempo (BPM) and key detection using numpy only."""

import numpy as np

from .scales import midi_to_name


def _frames(audio, sr, frame=1024, hop=512):
    n = (len(audio) - frame) // hop
    if n < 1:
        n = 1
    return np.lib.stride_tricks.sliding_window_view(audio, frame)[::hop][:n]


def _onset_envelope(audio, sr):
    frame, hop = 1024, 512
    frames = _frames(audio, sr, frame, hop)
    win = np.hanning(frame)
    spec = np.abs(np.fft.rfft(frames * win, axis=1))
    # full-spectrum energy flux, with low band de-emphasized
    freq_weights = np.ones(spec.shape[1])
    freqs = np.fft.rfftfreq(frame, 1.0 / sr)
    freq_weights[freqs < 100] = 0.5
    spec = spec * freq_weights
    flux = np.diff(np.sum(spec, axis=1), prepend=0)
    flux[flux < 0] = 0
    flux -= flux.mean()
    denom = flux.std() + 1e-9
    flux /= denom
    # mild smoothing so a single click yields one broad peak
    kernel = np.ones(3) / 3
    flux = np.convolve(flux, kernel, mode="same")
    return flux


def detect_tempo(audio, sr, lo=60, hi=200):
    """Detect tempo via autocorrelation of the onset envelope with harmonic refinement."""
    flux = _onset_envelope(audio, sr)
    hop = 512
    hop_s = hop / sr
    x = flux - flux.mean()
    ac = np.correlate(x, x, mode="full")[len(x) - 1:]
    if ac[0] < 1e-9:
        return 112
    ac /= ac[0]
    lag_min = max(int(60.0 / hi / hop_s), 1)
    lag_max = int(60.0 / lo / hop_s)
    lag_max = min(lag_max, len(ac) - 1)
    if lag_max <= lag_min:
        return 112

    def score_at_lag(lag):
        # local prominence over a neighborhood, avoids broad DC drift
        lo_n = max(lag - 3, lag_min)
        hi_n = min(lag + 3, lag_max)
        neigh = max(np.max(ac[lo_n:hi_n + 1]), 1e-6)
        return ac[lag] / neigh if ac[lag] > 0 else 0.0

    lags = list(range(lag_min, lag_max + 1))
    scores = [score_at_lag(l) for l in lags]
    best_lag = lags[int(np.argmax(scores))]
    bpm = 60.0 / (best_lag * hop_s)

    # harmonic refinement: if a fraction of the best lag scores higher, use it
    for ratio in (0.5, 2.0):
        cand = bpm * ratio
        if lo <= cand <= hi:
            lag2 = int(round(60.0 / cand / hop_s))
            if lag_min <= lag2 <= lag_max and score_at_lag(lag2) > score_at_lag(best_lag) * 1.05:
                bpm = cand
    return int(round(bpm))


KRUMHANSL_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
KRUMHANSL_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def _chroma(audio, sr):
    frame, hop = 4096, 2048
    frames = _frames(audio, sr, frame, hop)
    win = np.hanning(frame)
    spec = np.abs(np.fft.rfft(frames * win, axis=1)) ** 2
    freqs = np.fft.rfftfreq(frame, 1.0 / sr)
    chroma = np.zeros((len(frames), 12))
    for pc in range(12):
        # include harmonics up to 8x for robustness
        mask = np.zeros(len(freqs), dtype=bool)
        for h in range(1, 9):
            f = (pc * 8.175799 + 0) * h
            band = (freqs > f * 0.97) & (freqs < f * 1.03)
            mask |= band
        chroma[:, pc] = spec[:, mask].sum(axis=1)
    return chroma.sum(axis=0)


def detect_key(audio, sr):
    """Return (key_name, 'major'|'minor') via chroma correlation with Krumhansl profiles."""
    chroma = _chroma(audio, sr)
    if chroma.sum() < 1e-6:
        return "C", "major"
    chroma = chroma / (chroma.sum() + 1e-9)
    best = None
    best_score = -1e9
    for pc in range(12):
        for profile, mode in ((KRUMHANSL_MAJOR, "major"), (KRUMHANSL_MINOR, "minor")):
            rotated = np.roll(chroma, -pc)
            score = float(np.dot(rotated, profile))
            if score > best_score:
                best_score = score
                best = (pc, mode)
    pc, mode = best
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    key = names[pc]
    return key, mode


def analyze_recording(path, sr=44100):
    from .engine import read_wav_mono
    audio = read_wav_mono(path, sr)
    duration = len(audio) / sr
    tempo = detect_tempo(audio, sr)
    key, mode = detect_key(audio, sr)
    return {
        "bpm": tempo,
        "key": key,
        "mode": mode,
        "duration_s": round(duration, 1),
        "recording_name": path.split("/")[-1],
    }
