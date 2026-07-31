"""Waveform synthesis engine: oscillators, envelopes, drums, instruments and the Track mixer."""

import numpy as np
import wave

SR = 44100


def t_len(beats, bpm):
    return int(beats * (60.0 / bpm) * SR)


# ---------- oscillators ----------
def noise(n, seed=0):
    return np.random.default_rng(seed).uniform(-1, 1, n)


def sine(f, n):
    tt = np.arange(n) / SR
    return np.sin(2 * np.pi * f * tt)


def saw(f, n):
    tt = np.arange(n) / SR
    return 2 * (tt * f % 1) - 1


def square(f, n):
    tt = np.arange(n) / SR
    return np.sign(np.sin(2 * np.pi * f * tt))


def triangle(f, n):
    tt = np.arange(n) / SR
    return 2 * np.abs(2 * (tt * f % 1) - 1) - 1


# ---------- envelopes ----------
def adsr(n, a=0.01, d=0.1, s=0.7, r=0.15):
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    si = max(n - ai - di - ri, 0)
    parts = [
        np.linspace(0, 1, ai) if ai else np.array([]),
        np.linspace(1, s, di) if di else np.array([]),
        np.full(si, s) if si else np.array([]),
        np.linspace(s, 0, ri) if ri else np.array([]),
    ]
    return np.concatenate(parts)[:n]


def exp_env(n, decay=12.0):
    return np.exp(-np.arange(n) / SR * decay)


# ---------- filters ----------
def one_pole_lowpass(sig, alpha):
    out = np.empty_like(sig)
    acc = 0.0
    for i, s in enumerate(sig):
        acc += alpha * (s - acc)
        out[i] = acc
    return out


def one_pole_highpass(sig, alpha):
    out = np.empty_like(sig)
    prev = 0.0
    for i, s in enumerate(sig):
        prev = alpha * (prev + s - (s if i == 0 else sig[i - 1]))
        out[i] = prev
    return out


def diff_filt(sig):
    return np.diff(sig, prepend=0)


# ---------- drums ----------
def kick():
    n = int(0.55 * SR)
    tt = np.arange(n) / SR
    f = 160 * np.exp(-tt * 20) + 44
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-tt * 22)
    click = np.sin(2 * np.pi * 1100 * tt) * np.exp(-tt * 350) * 0.35
    return np.tanh(body * 1.8) * 0.95 + click


def clap():
    out = np.zeros(int(0.3 * SR))
    for k in range(4):
        n = int(0.05 * SR)
        seg = noise(n, 100 + k) * np.exp(-np.arange(n) / SR / 0.007)
        i = int(k * 0.012 * SR)
        out[i:i + n] += seg * (1.0 if k < 3 else 0.6)
    return np.tanh(diff_filt(out) * 2) * 0.6


def snare():
    n = int(0.28 * SR)
    tt = np.arange(n) / SR
    nois = diff_filt(noise(n, 40))
    tone = np.sin(2 * np.pi * 185 * tt) * np.exp(-tt * 28)
    return (nois * 0.65 + tone * 0.35) * np.exp(-tt * 20) * 0.85


def hat(open_=False):
    n = int((0.5 if open_ else 0.09) * SR)
    seg = diff_filt(noise(n, 60))
    decay = 6 if open_ else 50
    return seg * np.exp(-np.arange(n) / SR * decay) * 0.3


def shaker():
    n = int(0.07 * SR)
    seg = diff_filt(noise(n, 80))
    return seg * np.exp(-np.arange(n) / SR / 0.018) * 0.16


def tom(f=180.0):
    n = int(0.35 * SR)
    tt = np.arange(n) / SR
    fv = f * np.exp(-tt * 8) + f * 0.8
    ph = 2 * np.pi * np.cumsum(fv) / SR
    return np.sin(ph) * np.exp(-tt * 14) * 0.8


def cowbell():
    n = int(0.25 * SR)
    tt = np.arange(n) / SR
    sig = np.sin(2 * np.pi * 540 * tt) + 0.7 * np.sin(2 * np.pi * 810 * tt)
    return sig * np.exp(-tt * 18) * 0.4


def crash():
    n = int(1.2 * SR)
    return diff_filt(noise(n, 90)) * np.exp(-np.arange(n) / SR / 0.28) * 0.5


def riser(beats, bpm):
    n = t_len(beats, bpm)
    tt = np.arange(n) / SR
    seg = diff_filt(noise(n, 120))
    filt = one_pole_lowpass(seg, 0.12)
    sweep = filt * (1 - np.exp(-tt * 1.5))
    pump = np.sin(2 * np.pi * (2 + 6 * tt / (beats * (60.0 / bpm))) * tt) ** 2
    return sweep * (0.5 + 0.5 * pump) * (0.3 + 0.7 * tt / (beats * (60.0 / bpm)))


# ---------- instruments ----------
def bass(f, beats, bpm, timbre="modern", gain=0.5):
    n = t_len(beats, bpm)
    tt = np.arange(n) / SR
    sub = np.sin(2 * np.pi * f * tt)
    if timbre == "modern":
        sq = np.sign(np.sin(2 * np.pi * f * tt))
        sawt = saw(f, n)
        body = np.tanh((sawt * 0.6 + sq * 0.4) * 1.4) * 0.55
        return sub * 0.7 + body * gain
    if timbre == "warm":
        return np.tanh(saw(f, n) * 0.8) * 0.4 + sub * 0.6
    return sub * 0.9


def pad(freqs, beats, bpm, gain=0.22, attack=0.5, tremolo=0.4):
    n = t_len(beats, bpm)
    tt = np.arange(n) / SR
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        det = f * 0.0025
        w = (np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * (f + det) * tt)
             + 0.3 * np.sin(2 * np.pi * (f - det) * tt))
        out += w * (1 - i * 0.12)
    out /= max(len(freqs), 1)
    amp = adsr(n, attack, 0.1, 0.85, 0.7)
    trem = 1 + 0.1 * np.sin(2 * np.pi * tremolo * tt)
    return out * amp * trem * gain


def pluck(f, beats, bpm, wave="saw", gain=0.28):
    n = t_len(beats, bpm)
    tt = np.arange(n) / SR
    sig = saw(f, n) if wave == "saw" else triangle(f, n)
    amp = adsr(n, 0.002, 0.25, 0.5, 0.1)
    return np.tanh(sig * 1.5) * amp * gain


def lead(f, beats, bpm, octave=1, timbre="warm", gain=0.34):
    n = t_len(beats, bpm)
    tt = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.0 * tt)
    fv = f * octave * vib
    if timbre == "warm":
        sig = np.sin(2 * np.pi * fv * tt) * 0.5 + np.sign(np.sin(2 * np.pi * fv * tt)) * 0.28 + saw(fv, n) * 0.22
    elif timbre == "bright":
        sig = np.sin(2 * np.pi * fv * tt) * 0.3 + saw(fv, n) * 0.7
    else:
        sig = np.sin(2 * np.pi * fv * tt)
    sig = np.tanh(sig * 1.3)
    amp = adsr(n, 0.01, 0.1, 0.78, 0.15)
    return sig * amp * gain


def bell(f, beats, bpm, gain=0.11):
    n = t_len(beats, bpm)
    tt = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 2.01 * tt)
           + 0.15 * np.sin(2 * np.pi * f * 3.99 * tt))
    return sig * np.exp(-tt * 5) * gain


def organ(f, beats, bpm, gain=0.18):
    n = t_len(beats, bpm)
    tt = np.arange(n) / SR
    sig = sine(f, n) + 0.5 * sine(f * 2, n) + 0.25 * sine(f * 3, n) + 0.12 * sine(f * 4, n)
    trem = 1 + 0.3 * np.sin(2 * np.pi * 6 * tt)
    return sig * trem * gain


# ---------- mixer ----------
class Track:
    def __init__(self, duration_s, bpm=112):
        self.n = int(duration_s * SR)
        self.bpm = bpm
        self.L = np.zeros(self.n)
        self.R = np.zeros(self.n)

    def bar(self):
        return 4 * 60.0 / self.bpm

    def place(self, sig, at_s, pan=0.0, gain=1.0):
        i = int(at_s * SR)
        if i >= self.n:
            return
        end = min(i + len(sig), self.n)
        gl = np.sqrt((1 - pan) / 2) * 2
        gr = np.sqrt((1 + pan) / 2) * 2
        self.L[i:end] += sig[:end - i] * gl * gain
        self.R[i:end] += sig[:end - i] * gr * gain

    def place_lr(self, sigL, sigR, at_s, gain=1.0):
        i = int(at_s * SR)
        if i >= self.n:
            return
        end = min(i + len(sigL), self.n)
        self.L[i:end] += sigL[:end - i] * gain
        self.R[i:end] += sigR[:end - i] * gain


def fft_reverb(sig, seed=7, rt=1.2):
    """Return only the wet (reverb tail) signal."""
    n = int(SR * rt)
    ir = noise(n, seed) * np.exp(-np.arange(n) / SR / (rt * 0.3))
    ns = len(sig) + n
    fft_size = 1
    while fft_size < ns:
        fft_size <<= 1  # power-of-two FFTs are dramatically faster
    wet = np.fft.irfft(np.fft.rfft(sig, fft_size) * np.fft.rfft(ir, fft_size), fft_size)[:len(sig)]
    return wet


def sidechain(sig, duck_positions, sr=SR, bpm=112):
    duck = np.ones(len(sig))
    six = (60.0 / bpm) / 4
    for pos in duck_positions:
        i = int(pos * six * sr)
        if i >= len(sig):
            continue
        n = int(0.28 * six * sr)
        e = np.linspace(0, 1, n)
        seg = 0.6 + 0.4 * e
        end = min(i + n, len(sig))
        duck[i:end] = np.minimum(duck[i:end], seg[:end - i])
    return sig * duck


def softclip(audio, drive=0.45):
    return np.tanh(audio * drive)


def normalize(audio, peak=0.92):
    m = np.max(np.abs(audio)) + 1e-9
    return audio / m * peak


def fade_out(audio, seconds=3.0):
    n = int(seconds * SR)
    out = audio.copy()
    out[-n:] *= np.linspace(1, 0, n)
    return out


def write_wav(path, audio_l, audio_r, sr=SR):
    pcm = (np.stack([audio_l, audio_r], axis=0).T * 32767).astype(np.int16)
    with wave.open(path, "w") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def read_wav_mono(path, sr=SR):
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype=np.int16)
        ch = w.getnchannels()
        rate = w.getframerate()
        if ch == 2:
            data = data.reshape(-1, 2).mean(axis=1)
        audio = data.astype(float) / 32767.0
    if rate != sr and len(audio) > 1:
        x_old = np.linspace(0, len(audio), len(audio))
        x_new = np.linspace(0, len(audio), int(len(audio) * sr / rate))
        audio = np.interp(x_new, x_old, audio)
    return audio
