"""Track generation: arranges genre patterns + melody into a full stereo mix."""

import numpy as np

from . import engine
from .genres import GENRES, GENRE_ALIASES, TEMPO_WORDS, BASS_PATTERNS, DRUM_PATTERNS
from .scales import name_to_midi, parse_key, scale_degrees, midi_to_freq
from .melody import lyrics_to_melody, random_melody, lyrics_mood, _seed_for


def _intensity_for(bar, n_bars, intro_end, build_end, breakdown):
    if bar < intro_end:
        return 0.0
    if bar < build_end:
        return 0.6
    if breakdown and breakdown[0] <= bar < breakdown[1]:
        return 0.0
    return 1.0


def _play_drums(track, bar, pattern, intensity):
    start = bar * track.bar()
    if intensity <= 0:
        return
    g = intensity
    for pos in pattern["kick"]:
        track.place(engine.kick(), start + pos * track.bar() / 16, 0.0, g)
    for pos in pattern["snare"]:
        track.place(engine.snare(), start + pos * track.bar() / 16, 0.05, g * 0.85)
    for pos in pattern["clap"]:
        track.place(engine.clap(), start + pos * track.bar() / 16, 0.05, g * 0.9)
    if pattern["hat8"]:
        for e in range(8):
            off = (track.bar() / 16) * 0.5
            h = start + e * track.bar() / 8 + off
            track.place(engine.hat(e == 7), h, -0.3, g * (pattern["hat_gain"] if e % 2 else pattern["hat_gain"] * 1.6))
    for pos in pattern["open_hat"]:
        track.place(engine.hat(True), start + pos * track.bar() / 16, -0.3, g)
    for pos in pattern["shaker"]:
        track.place(engine.shaker(), start + pos * track.bar() / 16 + track.bar() / 32, 0.35, g)
    for pos in pattern["cowbell"]:
        track.place(engine.cowbell(), start + pos * track.bar() / 16, 0.25, g * 0.5)


def _play_bass(track, bar, root_midi, pattern):
    start = bar * track.bar()
    step = track.bar() / 8
    for epos, length in pattern:
        f = midi_to_freq(root_midi)
        track.place(engine.bass(f, length * 0.5, track.bpm), start + epos * step, 0.0, 1.0)


def _play_chords(track, bar, root_midi, scale_name, chord_deg, intensity, genre):
    start = bar * track.bar()
    from .scales import chord
    voicing = chord(root_midi, scale_name, chord_deg, n_notes=3)
    freqs = [midi_to_freq(m) for m in voicing]
    if genre["pad"] and intensity > 0:
        track.place(engine.pad(freqs, 4, track.bpm), start, 0.0, genre.get("pad_level", 0.22))
    if genre["stab"] and intensity >= 0.8:
        for k in range(4):
            t = start + k * track.bar() / 4
            for j, f in enumerate(freqs):
                track.place(engine.pluck(f, 1.4, track.bpm), t, (j - 1) * 0.15, 0.4)
    if genre["arp"] and intensity >= 0.6:
        from .scales import scale_degrees
        pool = scale_degrees(root_midi, scale_name, 0, 1)
        seq = [0, 1, 2, 1, 3, 2, 1, 2, 0, 3, 2, 1, 3, 2, 0, 1]
        for k, idx in enumerate(seq):
            m = pool[min(idx, len(pool) - 1)]
            track.place(engine.bell(midi_to_freq(m), 0.5, track.bpm), start + k * track.bar() / 16, (k % 2) * 0.4 - 0.2, 0.8)
    if genre["bell"] and intensity == 0.0 and bar % 2 == 0:
        for k in range(4):
            f = midi_to_freq(freqs[k % len(freqs)])
            track.place(engine.bell(f * 2, 1, track.bpm), start + k * track.bar() / 4, 0.3, 0.8)


def _play_melody(track, melody, start_bar, bars, genre, harmony_interval=None, gain=1.0, octave=1):
    if not melody:
        return
    t = start_bar * track.bar()
    end_t = (start_bar + bars) * track.bar()
    total = sum(b for _, b in melody)
    idx = 0
    while t < end_t and melody:
        note, beats = melody[idx % len(melody)]
        if note is not None:
            f = midi_to_freq(note)
            track.place(engine.lead(f, beats, track.bpm, octave=octave, timbre=genre["lead_timbre"]), t, 0.0, gain)
            if harmony_interval:
                hf = midi_to_freq(note + harmony_interval)
                track.place(engine.lead(hf, beats, track.bpm, octave=octave, timbre=genre["lead_timbre"]), t, 0.2, gain * 0.55)
        t += beats * (60.0 / track.bpm)
        idx += 1


def generate_track(genre_name, bpm, root_midi, scale_name, duration_s, melody=None, seed=None, mode="song"):
    """Build the full track. Returns (L, R, meta)."""
    genre = GENRES[genre_name]
    if bpm is None:
        bpm = genre["bpm"]
    bpm = int(round(bpm))

    n_bars = max(16, int(round(duration_s / (4 * 60.0 / bpm))))
    total_s = n_bars * 4 * 60.0 / bpm + 0.5
    track = engine.Track(total_s, bpm)

    intro_end = min(4, n_bars // 6)
    build_end = intro_end + min(4, n_bars // 6)
    breakdown = None
    if n_bars >= 24:
        bd_start = int(n_bars * 0.62)
        breakdown = (bd_start, min(bd_start + 4, n_bars - 4))
    main_end = breakdown[0] if breakdown else n_bars - 2
    outro_start = n_bars - 2

    chord_prog = genre["chords"]
    bass_pattern = BASS_PATTERNS[genre_name]

    if melody is None:
        melody = random_melody(root_midi, scale_name, 16, bpm, seed=seed)

    for bar in range(n_bars):
        chord_deg = chord_prog[bar % len(chord_prog)]
        intensity = _intensity_for(bar, n_bars, intro_end, build_end, breakdown)
        if bar >= outro_start:
            intensity = min(intensity, 0.5)

        _play_chords(track, bar, root_midi, scale_name, chord_deg, intensity, genre)

        if intensity > 0:
            _play_bass(track, bar, root_midi - 12, bass_pattern)
            _play_drums(track, bar, DRUM_PATTERNS[genre_name], intensity)

        # tom fill before drop
        if breakdown and bar == breakdown[0] - 1:
            start = bar * track.bar()
            for k, f in enumerate([220, 165, 125, 95]):
                track.place(engine.tom(f), start + (12 + k * 1.5) * track.bar() / 16, 0.0, 0.8)

        if bar < intro_end:
            pass

        # melody in main + drop sections
        if build_end <= bar < main_end and (not breakdown or not (breakdown[0] <= bar < breakdown[1])):
            _play_melody(track, melody, bar, 1, genre,
                         harmony_interval=(-3 if genre["scale"] == "minor" else 3) if intensity >= 0.9 else None,
                         gain=1.0 if intensity < 1.0 else 1.05)

    # risers into build/drop
    for bar in (build_end - 1, breakdown[0] - 1 if breakdown else -1):
        if 0 <= bar < n_bars:
            track.place(engine.riser(4, bpm), bar * track.bar(), 0.0, 0.5)

    return _mix(track, bpm, genre_name, root_midi, scale_name, seed)


def _mix(track, bpm, genre_name, root_midi, scale_name, seed):
    L, R = track.L.copy(), track.R.copy()

    # stereo delay on the lead region only (keep from bar 8 onward)
    lead_start = int(8 * 4 * 60.0 / bpm * engine.SR)
    leadL = np.zeros(track.n); leadR = np.zeros(track.n)
    leadL[lead_start:] = L[lead_start:]
    leadR[lead_start:] = R[lead_start:]
    delL = np.zeros(track.n); delR = np.zeros(track.n)
    dn = int(0.29 * engine.SR)
    for ch_src, ch_dst in ((leadL, delL), (leadR, delR)):
        ch_dst[dn:] += ch_src[:-dn] * 0.35
        ch_dst[2 * dn:] += ch_src[:-2 * dn] * 0.15
    L = L + delL
    R = R + delR

    wetL = engine.fft_reverb(L) * 1.0
    wetR = engine.fft_reverb(R, seed=9) * 1.0
    L = L + wetL * 0.3
    R = R + wetR * 0.3

    duck_pos = []
    for bar in range(8, track.n // int(4 * 60.0 / bpm * engine.SR) + 1):
        pass
    # sidechain on kick beats from bar 8 onward
    bar_len = int(4 * 60.0 / bpm * engine.SR)
    for i in range(8 * bar_len, track.n, bar_len):
        for kp in [0, 6]:
            duck_pos.append((i + kp * bar_len / 16) / engine.SR / ((60.0 / bpm) / 4))
    L = engine.sidechain(L, duck_pos, bpm=bpm)
    R = engine.sidechain(R, duck_pos, bpm=bpm)

    L = engine.softclip(L, 0.4)
    R = engine.softclip(R, 0.4)
    peak = max(np.max(np.abs(L)), np.max(np.abs(R)), 1e-9)
    L = L / peak * 0.9
    R = R / peak * 0.9
    L = engine.fade_out(L, 3.0)
    R = engine.fade_out(R, 3.0)
    return L, R


# ---------- prompt / lyrics / recording entry points ----------
def _find_genre(text):
    t = text.lower()
    for alias, g in GENRE_ALIASES.items():
        if alias in t:
            return g
    mood = lyrics_mood(text)
    if mood == "sad":
        return "ballad"
    if mood == "worship":
        return "gospel"
    if mood == "love":
        return "ballad"
    return "afrobeats"


def _find_key(text):
    import re
    m = re.search(r"\bkey of ([a-g](?:#|b)?)(?: (major|minor|min|m))?\b", text.lower())
    if m:
        return m.group(1) + "4", "major" if m.group(2) in (None, "major") else "minor"
    m2 = re.search(r"\b([a-g](?:#|b)?)[ -]?(m|min|minor|maj|major)\b", text.lower())
    if m2:
        root = m2.group(1)
        mode = "minor" if m2.group(2) in ("m", "min", "minor") else "major"
        return root + "4", mode
    return None, None


def _adjust_bpm(text, bpm):
    t = text.lower()
    factor = 1.0
    for word, f in TEMPO_WORDS.items():
        if word in t:
            factor *= f
    import re
    m = re.search(r"(\d{2,3})\s*(?:bpm|beats per minute)", t)
    if m:
        return int(m.group(1))
    return int(round(bpm * factor))


def generate_from_prompt(prompt, duration_s=40.0, seed=None):
    genre_name = _find_genre(prompt)
    key_name, mode = _find_key(prompt)
    if key_name:
        root_midi = name_to_midi(key_name)
        scale_name = mode
    else:
        rng = np.random.default_rng(seed if seed is not None else _seed_for(prompt))
        root_midi = 60 + int(rng.integers(0, 12))
        scale_name = GENRES[genre_name]["scale"]
    bpm = _adjust_bpm(prompt, GENRES[genre_name]["bpm"])
    melody = random_melody(root_midi, scale_name, 16, bpm, seed=seed)
    L, R = generate_track(genre_name, bpm, root_midi, scale_name, duration_s, melody=melody, seed=seed)
    meta = _meta(genre_name, bpm, root_midi, scale_name, duration_s, seed, "prompt")
    meta["prompt"] = prompt
    return L, R, meta


def generate_from_lyrics(lyrics, duration_s=40.0, genre_name=None, seed=None):
    mood = lyrics_mood(lyrics)
    if genre_name is None:
        genre_name = _find_genre(lyrics)
    root_midi = 60 + 4  # E by default for a singable register
    scale_name = GENRES[genre_name]["scale"]
    melody = lyrics_to_melody(lyrics, root_midi, scale_name, seed=seed)
    bpm = GENRES[genre_name]["bpm"]
    L, R = generate_track(genre_name, bpm, root_midi, scale_name, duration_s, melody=melody, seed=seed)
    meta = _meta(genre_name, bpm, root_midi, scale_name, duration_s, seed, "lyrics")
    meta["lyrics"] = lyrics[:500]
    meta["detected_mood"] = mood
    return L, R, meta


def generate_from_recording(analysis, duration_s=40.0, genre_name=None, seed=None):
    if genre_name is None:
        genre_name = "afrobeats"
    bpm = analysis["bpm"]
    root_midi = name_to_midi(analysis["key"] + "4")
    scale_name = "minor" if analysis["mode"] == "minor" else "major"
    melody = random_melody(root_midi, scale_name, 16, bpm, seed=seed)
    L, R = generate_track(genre_name, bpm, root_midi, scale_name, duration_s, melody=melody, seed=seed)
    meta = _meta(genre_name, bpm, root_midi, scale_name, duration_s, seed, "recording")
    meta["recording_analysis"] = analysis
    return L, R, meta


def _meta(genre_name, bpm, root_midi, scale_name, duration_s, seed, mode):
    from .scales import midi_to_name
    return {
        "mode": mode,
        "genre": genre_name,
        "genre_name": GENRES[genre_name]["name"],
        "bpm": bpm,
        "key": midi_to_name(root_midi, octave=False),
        "scale": scale_name,
        "duration_s": duration_s,
        "seed": seed,
    }
