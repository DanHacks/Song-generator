import os
import numpy as np
import wave

SR = 44100
BPM = 112
BEAT = 60.0 / BPM
BAR = BEAT * 4
SIX = BEAT / 4
EIGHTH = BEAT / 2

N_BARS = 40
TOTAL_SEC = N_BARS * BAR
N = int(TOTAL_SEC * SR)

L = np.zeros(N)
R = np.zeros(N)

SEMIS = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
         "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}

def freq(note):
    note = note.upper()
    if len(note) >= 2 and note[1] in "#b":
        letter, octave = note[:2], int(note[2:])
    else:
        letter, octave = note[:1], int(note[1:])
    midi = 60 + SEMIS[letter] + 12 * (octave - 4)
    return 440.0 * 2 ** ((midi - 69) / 12.0)

def add(buf, sig, start_s, gain=1.0):
    i = int(start_s * SR)
    if i >= len(buf):
        return
    end = min(i + len(sig), len(buf))
    buf[i:end] += sig[:end - i] * gain

def st(bufL, bufR, sig, start_s, pan=0.0, gain=1.0):
    i = int(start_s * SR)
    if i >= len(bufL):
        return
    end = min(i + len(sig), len(bufL))
    gl = np.sqrt((1 - pan) / 2) * 2
    gr = np.sqrt((1 + pan) / 2) * 2
    bufL[i:end] += sig[:end - i] * gl * gain
    bufR[i:end] += sig[:end - i] * gr * gain

def noise(n, seed=0):
    return np.random.default_rng(seed).uniform(-1, 1, n)

def lowpass(sig, alpha):
    out = np.empty_like(sig)
    acc = 0.0
    for i, s in enumerate(sig):
        acc += alpha * (s - acc)
        out[i] = acc
    return out

# ---------- DRUMS ----------
def kick():
    n = int(0.55 * SR)
    tt = np.arange(n) / SR
    f = 160 * np.exp(-tt * 20) + 44
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-tt * 22)
    click = np.sin(2 * np.pi * 1100 * tt) * np.exp(-tt * 350) * 0.35
    sat = np.tanh(body * 1.8)
    return (sat + click) * 0.95

def clap():
    out = np.zeros(int(0.3 * SR))
    for k in range(4):
        n = int(0.05 * SR)
        seg = noise(n, 100 + k) * np.exp(-np.arange(n) / SR / 0.007)
        add(out, seg, k * 0.012, 1.0 if k < 3 else 0.6)
    bp = np.diff(out, prepend=0)
    return np.tanh(bp * 2) * 0.6

def snare():
    n = int(0.28 * SR)
    tt = np.arange(n) / SR
    nois = np.diff(noise(n, 40), prepend=0)
    tone = np.sin(2 * np.pi * 185 * tt) * np.exp(-tt * 28)
    return (nois * 0.65 + tone * 0.35) * np.exp(-tt * 20) * 0.85

def hat(open_=False, pan=-0.3):
    n = int((0.5 if open_ else 0.09) * SR)
    seg = np.diff(noise(n, 60), prepend=0)
    decay = 6 if open_ else 50
    return seg * np.exp(-np.arange(n) / SR * decay) * 0.3

def shaker(pan=0.35):
    n = int(0.07 * SR)
    seg = np.diff(noise(n, 80), prepend=0)
    return seg * np.exp(-np.arange(n) / SR / 0.018) * 0.16

def tom(f=180.0):
    n = int(0.35 * SR)
    tt = np.arange(n) / SR
    f = f * np.exp(-tt * 8) + f * 0.8
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-tt * 14) * 0.8

def cowbell():
    n = int(0.25 * SR)
    tt = np.arange(n) / SR
    sig = np.sin(2 * np.pi * 540 * tt) + 0.7 * np.sin(2 * np.pi * 810 * tt)
    return sig * np.exp(-tt * 18) * 0.4

def crash():
    n = int(1.2 * SR)
    seg = noise(n, 90)
    seg = np.diff(seg, prepend=0)
    return seg * np.exp(-np.arange(n) / SR / 0.28) * 0.5

def riser(beats=4):
    n = int(beats * BEAT * SR)
    tt = np.arange(n) / SR
    seg = noise(n, 120)
    seg = np.diff(seg, prepend=0)
    filt = lowpass(seg, 0.12)
    sweep = filt * (1 - np.exp(-tt * 1.5))
    t2 = 0.2 * beats * tt
    pump = np.sin(2 * np.pi * (2 + 6 * tt / (beats * BEAT)) * tt) ** 2
    return sweep * (0.5 + 0.5 * pump) * (0.3 + 0.7 * tt / (beats * BEAT))

# ---------- KEYS ----------
def sub_bass(f, beats):
    n = int(beats * BEAT * SR)
    tt = np.arange(n) / SR
    sig = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 3) ** 0.5
    amp = env(n, 0.004, 0.2, 0.9, 0.03)
    return sig * amp * 0.7

def mid_bass(f, beats):
    n = int(beats * BEAT * SR)
    tt = np.arange(n) / SR
    saw = 2 * (tt * f % 1) - 1
    sq = np.sign(np.sin(2 * np.pi * f * tt))
    sig = saw * 0.6 + sq * 0.4
    sig = np.tanh(sig * 1.4)
    amp = env(n, 0.003, 0.08, 0.8, 0.04)
    return sig * amp * 0.32

def env(n, a=0.01, d=0.1, s=0.7, r=0.15):
    ai, di, ri = int(a * SR), int(d * SR), int(r * SR)
    si = max(n - ai - di - ri, 0)
    parts = [
        np.linspace(0, 1, ai) if ai else np.array([]),
        np.linspace(1, s, di) if di else np.array([]),
        np.full(si, s) if si else np.array([]),
        np.linspace(s, 0, ri) if ri else np.array([]),
    ]
    return np.concatenate(parts)[:n]

def pad_chord(freqs, beats):
    n = int(beats * BEAT * SR)
    tt = np.arange(n) / SR
    out = np.zeros(n)
    for i, f in enumerate(freqs):
        det = f * 0.0025
        w = (np.sin(2 * np.pi * f * tt) + 0.5 * np.sin(2 * np.pi * (f + det) * tt)
             + 0.3 * np.sin(2 * np.pi * (f - det) * tt))
        out += w * (1 - i * 0.12)
    out /= len(freqs)
    amp = env(n, 0.5, 0.1, 0.85, 0.7)
    trem = 1 + 0.1 * np.sin(2 * np.pi * 0.4 * tt)
    return out * amp * trem * 0.22

def pluck(f, beats, wave="saw"):
    n = int(beats * BEAT * SR)
    tt = np.arange(n) / SR
    saw = 2 * (tt * f % 1) - 1
    tri = 2 * np.abs(2 * (tt * f % 1) - 1) - 1
    sig = saw if wave == "saw" else tri
    amp = env(n, 0.002, 0.25, 0.5, 0.1)
    return np.tanh(sig * 1.5) * amp * 0.28

def lead(f, beats, octave=1):
    n = int(beats * BEAT * SR)
    tt = np.arange(n) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.0 * tt)
    fv = f * octave * vib
    sine = np.sin(2 * np.pi * fv * tt)
    sq = np.sign(np.sin(2 * np.pi * fv * tt))
    saw = 2 * (tt * fv % 1) - 1
    sig = sine * 0.5 + sq * 0.28 + saw * 0.22
    sig = np.tanh(sig * 1.3)
    amp = env(n, 0.01, 0.1, 0.78, 0.15)
    return sig * amp * 0.34

def bell(f, beats):
    n = int(beats * BEAT * SR)
    tt = np.arange(n) / SR
    sig = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * f * 2.01 * tt)
           + 0.15 * np.sin(2 * np.pi * f * 3.99 * tt))
    return sig * np.exp(-tt * 5) * 0.11

# ---------- EFFECTS ----------
def fft_reverb(sig, seed=7, rt=1.2):
    n = int(SR * rt)
    ir = noise(n, seed) * np.exp(-np.arange(n) / SR / (rt * 0.3))
    ns = len(sig) + n
    return np.fft.irfft(np.fft.rfft(sig, ns) * np.fft.rfft(ir, ns), ns)[:len(sig)]

def sidechain(sig, pattern_16th):
    duck = np.ones(len(sig))
    for pos in pattern_16th:
        i = int(pos * SIX * SR)
        if i >= len(sig):
            continue
        n = int(0.28 * BEAT * SR)
        e = np.linspace(0, 1, n)
        seg = 0.65 + 0.35 * e
        end = min(i + n, len(sig))
        duck[i:end] = np.minimum(duck[i:end], seg[:end - i])
    return sig * duck

# ---------- ARRANGEMENT ----------
prog = ["G", "Em", "C", "D"]
bass_roots = {"G": "G1", "Em": "E2", "C": "C2", "D": "D2"}
voicings = {
    "G": ["G3", "B3", "D4", "G4"],
    "Em": ["E3", "G3", "B3", "D4"],
    "C": ["C3", "E3", "G3", "C4"],
    "D": ["D3", "F#3", "A3", "D4"],
}

melodyA = [
    ("D5", 0.5), ("D5", 0.5), ("E5", 1), ("F#5", 1), ("E5", 1),
    ("D5", 1), ("C5", 1), ("B4", 1), ("A4", 1),
]
melodyB = [
    ("B4", 0.5), ("C5", 0.5), ("B4", 1), ("A4", 1), ("G4", 1),
    ("A4", 1), ("B4", 1), ("A4", 1), ("G4", 1),
]
mel_phrases = [melodyA, melodyB]

def play_melody(bar_start, n_bars, octave=1, harmony=None, gain=1.0, pan=0.0):
    for b in range(n_bars):
        bar = bar_start + b
        ph = mel_phrases[b % 2]
        t = bar * BAR
        for note, beats in ph:
            f = freq(note)
            s = lead(f, beats, octave)
            st(L, R, s, t, pan, gain)
            if harmony:
                hs = lead(f * harmony, beats, octave)
                st(L, R, hs, t, pan * 0.5, gain * 0.6)
            t += beats * BEAT

def drums(bar, intensity=1.0):
    start = bar * BAR
    g = intensity
    st(L, R, kick(), start, 0.0, g)
    st(L, R, clap(), start + 1 * BEAT, 0.05, g * 0.9)
    st(L, R, clap(), start + 3 * BEAT, 0.05, g * 0.9)
    for e in range(8):
        h = start + e * 0.5 * BEAT
        if e == 7:
            st(L, R, hat(True), h, -0.3, g)
        else:
            off = SIX * 0.5
            st(L, R, hat(False), h + off, -0.3, g * (0.5 if e % 2 else 0.85))
    for p in [1, 5, 9, 13]:
        st(L, R, shaker(), start + p * SIX + SIX * 0.6, 0.35, g)
    st(L, R, cowbell(), start + 2.5 * BEAT, 0.25, g * 0.5)

def bassline(bar, pattern=None):
    c = prog[bar % 4]
    root = freq(bass_roots[c])
    start = bar * BAR
    if pattern is None:
        pattern = [(0, 1.5), (3, 0.5), (5, 1.0), (7, 0.5)]
    for epos, beats in pattern:
        st(L, R, sub_bass(root, beats), start + epos * EIGHTH, 0.0, 0.9)
        st(L, R, mid_bass(root * 2, beats), start + epos * EIGHTH, 0.0, 0.55)

def stabs(bar, gate=0.8):
    c = prog[bar % 4]
    start = bar * BAR
    notes = voicings[c]
    for k in range(4):
        epos = k * 2
        t = start + epos * EIGHTH
        for j, n in enumerate(notes[:3]):
            st(L, R, pluck(freq(n), 1.4), t, (j - 1) * 0.15, 0.5)
    st(L, R, pluck(freq(notes[0]) * 2, 0.8), start + 6 * EIGHTH, 0.1, 0.3)

def pads(bar, gain=1.0):
    c = prog[bar % 4]
    st(L, R, pad_chord([freq(x) for x in voicings[c]], 4), bar * BAR, 0.0, gain)

def arp(bar, n16=16):
    c = prog[bar % 4]
    start = bar * BAR
    notes = voicings[c]
    seq = [0, 1, 2, 3, 2, 1, 0, 1, 2, 3, 2, 3, 1, 2, 0, 3]
    for k, idx in enumerate(seq):
        st(L, R, bell(freq(notes[idx % 4]) * 2, 0.5), start + k * SIX, (k % 2) * 0.4 - 0.2, 0.8)

# Build track
for bar in range(N_BARS):
    b4 = bar % 4
    if bar < 4:
        pads(bar, 0.8)
        if bar >= 2:
            arp(bar)
        if bar == 3:
            st(L, R, riser(4), bar * BAR, 0.0, 0.5)

    elif bar < 8:
        pads(bar, 0.6)
        bassline(bar)
        drums(bar, 0.8)
        if bar == 7:
            st(L, R, riser(4), bar * BAR, 0.0, 0.6)

    elif bar < 16:
        pads(bar, 0.55)
        bassline(bar)
        drums(bar, 1.0)
        play_melody(bar, 1, gain=1.0)
        if bar == 15:
            st(L, R, riser(4), bar * BAR, 0.0, 0.7)

    elif bar < 24:
        pads(bar, 0.7)
        bassline(bar)
        drums(bar, 1.0)
        stabs(bar)
        play_melody(bar, 1, octave=1, harmony=2 ** (-3 / 12), gain=1.05)
        if bar == 23:
            st(L, R, riser(4), bar * BAR, 0.0, 0.8)

    elif bar < 28:
        if b4 < 2:
            pads(bar, 0.5)
            arp(bar)
        else:
            st(L, R, riser(2), bar * BAR, 0.0, 0.5)
        if bar == 27:
            st(L, R, crash(), bar * BAR, 0.0, 0.5)

    elif bar < 36:
        pads(bar, 0.65)
        bassline(bar, pattern=[(0, 1.5), (3, 0.5), (5, 1.0), (6.5, 0.5), (7, 0.5)])
        drums(bar, 1.0)
        stabs(bar)
        play_melody(bar, 1, octave=2, harmony=2 ** (-7 / 12), gain=1.1)
        if bar == 35:
            st(L, R, crash(), bar * BAR, 0.0, 0.4)

    else:
        pads(bar, 0.5)
        bassline(bar, pattern=[(0, 1.5), (5, 1.0)])
        drums(bar, 0.7)
        play_melody(bar, 1, gain=0.8)

# ---- MIX ----
lead_region_start = 8 * BAR
leadL = np.zeros(N); leadR = np.zeros(N)
leadL[8 * SR:] = L[8 * SR:]; leadR[8 * SR:] = R[8 * SR:]
delL = np.zeros(N); delR = np.zeros(N)
for i in range(len(delL)):
    di = i - int(0.29 * SR)
    if di >= 0:
        delL[i] = leadL[di] * 0.35
        delR[i] = leadR[di] * 0.35
        di2 = i - int(0.29 * SR) * 2
        if di2 >= 0:
            delL[i] += leadL[di2] * 0.15
            delR[i] += leadR[di2] * 0.15
L = L + delL; R = R + delR
st(L, R, leadL * 0, 0)

wetL = fft_reverb(L, 7) * 0.3
wetR = fft_reverb(R, 9) * 0.3
L = L + wetL; R = R + wetR

kicks = []
for bar in range(4, N_BARS):
    if not (28 <= bar < 32):
        kicks += [bar * 4 * SIX / SIX]
duck_pos = []
for bar in range(4, N_BARS):
    for kp in [0, 6]:
        duck_pos.append(bar * 16 + kp)
L = sidechain(L, duck_pos)
R = sidechain(R, duck_pos)

mix = np.stack([L, R], axis=0)
mix = np.tanh(mix * 0.25)
mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.92

fade_n = int(3.5 * SR)
fade = np.ones(N)
fade[-fade_n:] = np.linspace(1, 0, fade_n)
mix *= fade

pcm = (mix.T * 32767).astype(np.int16)
out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kanisa_itachengwa_na_akina_nani_modern.wav")
with wave.open(out_path, "w") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())

print("WAV written:", round(TOTAL_SEC, 1), "seconds, stereo", out_path)
