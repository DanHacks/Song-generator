"""Track generation: arranges genre patterns + melody into a full stereo mix."""

import numpy as np

from . import engine
from .genres import GENRES, GENRE_ALIASES, TEMPO_WORDS, BASS_PATTERNS, DRUM_PATTERNS
from .scales import name_to_midi, parse_key, scale_degrees, midi_to_freq, midi_to_name
from .melody import lyrics_to_melody, lyrics_to_lines_melody, random_melody, lyrics_mood, _seed_for
from .arrangement import build_sections, vocal_start_bar, section_times, variation_label


def _bass_variant(genre_name, variant):
    """Alternative bass rhythms for anti-repetition (variant 0 = base)."""
    base = BASS_PATTERNS[genre_name]
    if variant == 1:
        off = [(min(p + 1, 7), l) for p, l in base]
        return off or [(0, 2)]
    if variant == 2:
        if len(base) >= 3:
            return [(0, 1), (1, 1), (2, 1)] + base[2:]
        return base
    return base


def _play_drums(track, bar, pattern, energy, density=1.0, width=1.0, style=0, extra=None):
    start = bar * track.bar()
    if energy <= 0 or not pattern:
        return
    g = min(energy, 1.15)
    kick = list(pattern["kick"])
    snare = list(pattern["snare"])
    clap = list(pattern["clap"])
    open_hat = list(pattern["open_hat"])
    shaker = list(pattern["shaker"])
    cowbell = list(pattern["cowbell"])
    hat8 = bool(pattern["hat8"])
    if style == 1:
        hat8 = True
        shaker = shaker + [0, 4, 8, 12] if shaker else [0, 4, 8, 12]
    if style == 2:
        open_hat = (open_hat + [12]) if open_hat else [12]
        cowbell = []
    if density >= 1.2:
        kick = kick + [2, 10]
        shaker = shaker + [2, 6, 10, 14] if shaker else [2, 6, 10, 14]
    if density <= 0.6:
        shaker = shaker[::2]
        hat8 = hat8 and density > 0.5
    if density <= 0.35:
        shaker = []
        open_hat = []

    for pos in kick:
        track.place(engine.kick(), start + pos * track.bar() / 16, 0.0, g)
    for pos in snare:
        track.place(engine.snare(), start + pos * track.bar() / 16, 0.05 * width, g * 0.85)
    for pos in clap:
        track.place(engine.clap(), start + pos * track.bar() / 16, 0.05 * width, g * 0.9)
    if hat8:
        for e in range(8):
            off = (track.bar() / 16) * 0.5
            h = start + e * track.bar() / 8 + off
            track.place(engine.hat(e == 7), h, -0.3 * width, g * (pattern["hat_gain"] if e % 2 else pattern["hat_gain"] * 1.6))
    for pos in open_hat:
        track.place(engine.hat(True), start + pos * track.bar() / 16, -0.3 * width, g)
    for pos in shaker:
        track.place(engine.shaker(), start + pos * track.bar() / 16 + track.bar() / 32, 0.35 * width, g)
    for pos in cowbell:
        track.place(engine.cowbell(), start + pos * track.bar() / 16, 0.25 * width, g * 0.5)
    if extra == "roll":
        _snare_roll(track, bar, g)
    elif extra == "fill":
        _tom_fill(track, bar)


def _snare_roll(track, bar, energy):
    """Building snare roll across the last half of a bar."""
    t0 = (bar + 1) * track.bar() - track.bar() / 2
    for i in range(8):
        t = t0 + i * (track.bar() / 2 / 8)
        gain = 0.15 + 0.85 * (i / 7)
        track.place(engine.snare(), t, 0.0, energy * gain)


def _tom_fill(track, bar):
    """Tom fill on the last beats of a bar (section boundary energy)."""
    start = (bar + 1) * track.bar() - track.bar() / 2
    for k, f in enumerate([220, 165, 125, 95]):
        track.place(engine.tom(f), start + k * 1.5 * track.bar() / 16, 0.0, 0.7)


def _play_log(track, bar, energy, density=1.0, width=1.0):
    """Afrobeat/amapiano log drum accents."""
    start = bar * track.bar()
    if energy <= 0:
        return
    positions = [2, 6, 10, 14] if density >= 1.0 else [2, 10]
    for i, pos in enumerate(positions):
        f = 130 + (i % 3) * 30
        track.place(engine.tom(f), start + pos * track.bar() / 16, (0.3 - 0.1 * i) * width, 0.5 * energy)


def _play_bass(track, bar, root_midi, pattern, timbre="modern"):
    start = bar * track.bar()
    step = track.bar() / 8
    for epos, length in pattern:
        f = midi_to_freq(root_midi)
        track.place(engine.bass(f, length * 0.5, track.bpm, timbre=timbre), start + epos * step, 0.0, 1.0)


def _play_chords(track, bar, root_midi, scale_name, chord_deg, energy, genre, on, inversion=0, register=0, width=1.0):
    start = bar * track.bar()
    from .scales import chord
    voicing = chord(root_midi + register, scale_name, chord_deg, n_notes=3)
    voicing = sorted(voicing)
    if inversion:
        voicing = voicing[inversion:] + [m + 12 for m in voicing[:inversion]]
    freqs = [midi_to_freq(m) for m in voicing]
    if on.get("pad") and energy > 0:
        track.place(engine.pad(freqs, 4, track.bpm), start, 0.0, genre.get("pad_level", 0.22))
    if on.get("stab") and energy >= 0.7:
        for k in range(4):
            t = start + k * track.bar() / 4
            for j, f in enumerate(freqs):
                track.place(engine.pluck(f, 1.4, track.bpm), t, (j - 1) * 0.15 * width, 0.4)
    if on.get("arp") and energy >= 0.5:
        from .scales import scale_degrees
        pool = scale_degrees(root_midi, scale_name, 0, 1)
        seq = [0, 1, 2, 1, 3, 2, 1, 2, 0, 3, 2, 1, 3, 2, 0, 1]
        for k, idx in enumerate(seq):
            m = pool[min(idx, len(pool) - 1)]
            track.place(engine.bell(midi_to_freq(m), 0.5, track.bpm), start + k * track.bar() / 16, ((k % 2) * 0.4 - 0.2) * width, 0.8)
    if on.get("bell") and bar % 2 == 0:
        for k in range(4):
            f = midi_to_freq(freqs[k % len(freqs)])
            track.place(engine.bell(f * 2, 1, track.bpm), start + k * track.bar() / 4, 0.3 * width, 0.8)


def _play_melody(track, melody, start_bar, bars, genre, harmony_interval=None, gain=1.0, octave=1, phase=None):
    if not melody:
        return
    t = start_bar * track.bar()
    end_t = (start_bar + bars) * track.bar()
    idx = phase["idx"] if phase else 0
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
    if phase:
        phase["idx"] = idx


def _play_transitions(track, sections, bpm):
    """Risers, reverse sweeps, crashes and boundary fills between sections."""
    for sec in sections:
        t = sec["transition"]
        if t == "riser":
            bar = sec["start_bar"] - 1
            if bar >= 0:
                track.place(engine.riser(4, bpm), bar * track.bar(), 0.0, 0.5)
        elif t == "reverse":
            bar = sec["start_bar"] - 1
            if bar >= 0:
                r = engine.riser(2, bpm)[::-1]
                track.place(r, bar * track.bar() + track.bar() - len(r) / engine.SR, 0.0, 0.35)
        elif t == "crash":
            track.place(engine.crash(), sec["start_bar"] * track.bar(), 0.0, 0.6)
        elif t == "fill":
            bar = sec["start_bar"] - 1
            if bar >= 0:
                _tom_fill(track, bar)


def song_sections(duration_s, bpm, genre_name, seed=None):
    """Sections for a given duration/tempo (shared by arrangement + vocals)."""
    n_bars = max(16, int(round(duration_s / (4 * 60.0 / bpm))))
    return build_sections(n_bars, bpm, genre_name, seed=seed)


def generate_track(genre_name, bpm, root_midi, scale_name, duration_s, melody=None, seed=None, mode="song"):
    """Build the full track using the section-based arrangement. Returns (L, R)."""
    genre = GENRES[genre_name]
    if bpm is None:
        bpm = genre["bpm"]
    bpm = int(round(bpm))

    n_bars = max(16, int(round(duration_s / (4 * 60.0 / bpm))))
    total_s = n_bars * 4 * 60.0 / bpm + 0.5
    track = engine.Track(total_s, bpm)

    sections = build_sections(n_bars, bpm, genre_name, seed=seed)
    chord_prog = genre["chords"]
    if melody is None:
        melody = random_melody(root_midi, scale_name, 16, bpm, seed=seed)

    melody_phase = {"idx": 0}
    for sec in sections:
        v = sec["variation"]
        for bar in range(sec["start_bar"], sec["end_bar"]):
            energy = sec["energy"]
            chord_deg = chord_prog[bar % len(chord_prog)]
            _play_chords(track, bar, root_midi, scale_name, chord_deg, energy, genre,
                         on=v["layering"], inversion=v["chord_inversion"],
                         register=v["register"], width=v["width"])
            if v["bass"] is not None and energy > 0:
                _play_bass(track, bar, root_midi - 12, _bass_variant(genre_name, v["bass"]),
                           timbre=genre["bass_timbre"])
            if v["bass"] is not None and energy > 0.2:
                _play_drums(track, bar, DRUM_PATTERNS[genre_name], energy,
                            density=v["density"], width=v["width"], style=v["drum_style"], extra=v["extra"])
            if genre.get("log") and energy >= 0.6:
                _play_log(track, bar, energy * 0.8, density=v["density"], width=v["width"])
            if v["layering"].get("lead") and melody and energy > 0.2:
                _play_melody(track, melody, bar, 1, genre,
                             harmony_interval=(-3 if genre["scale"] == "minor" else 3) if energy >= 0.95 else None,
                             gain=1.0 if energy < 1.0 else 1.05,
                             octave=v["melody_octave"], phase=melody_phase)

    _play_transitions(track, sections, bpm)
    return _mix(track, bpm, genre_name, root_midi, scale_name, seed, sections)


def _mix(track, bpm, genre_name, root_midi, scale_name, seed, sections=None):
    L, R = track.L.copy(), track.R.copy()

    # stereo delay on the lead region only (keep from bar 8 onward)
    lead_start = int(8 * 4 * 60.0 / bpm * engine.SR)
    leadL = np.zeros(track.n); leadR = np.zeros(track.n)
    leadL[lead_start:] = L[lead_start:]
    leadR[lead_start:] = R[lead_start:]
    delL = np.zeros(track.n); delR = np.zeros(track.n)
    dn = int(0.29 * engine.SR)
    delL[dn:] += leadL[:-dn] * 0.35
    delL[2 * dn:] += leadL[:-2 * dn] * 0.15
    delR[dn:] += leadR[:-dn] * 0.35
    delR[2 * dn:] += leadR[:-2 * dn] * 0.15
    L = L + delL
    R = R + delR

    # section-scaled reverb (quieter/underexposed sections get dryer, builds wetter)
    for sec in sections or []:
        s = int(sec["start_bar"] * 4 * 60.0 / bpm * engine.SR)
        e = int(sec["end_bar"] * 4 * 60.0 / bpm * engine.SR)
        e = min(e, track.n)
        if e <= s:
            continue
        wetL = engine.fft_reverb(L[s:e], 7)
        wetR = engine.fft_reverb(R[s:e], 9)
        blend = 0.18 + 0.22 * sec["energy"]
        L[s:e] = L[s:e] + wetL * blend
        R[s:e] = R[s:e] + wetR * blend

    # sidechain on kick beats from bar 8 onward
    duck_pos = []
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
    meta["spec"] = _spec(prompt, genre_name, bpm, root_midi, scale_name, duration_s, seed)
    return L, R, meta


def generate_from_lyrics(lyrics, duration_s=40.0, genre_name=None, seed=None, vocal_style="none", voice=None):
    mood = lyrics_mood(lyrics)
    if genre_name is None:
        genre_name = _find_genre(lyrics)
    root_midi = 60 + 4  # E by default for a singable register
    scale_name = GENRES[genre_name]["scale"]
    melody = lyrics_to_melody(lyrics, root_midi, scale_name, seed=seed)
    lines = lyrics_to_lines_melody(lyrics, root_midi, scale_name, seed=seed)
    bpm = GENRES[genre_name]["bpm"]
    L, R = generate_track(genre_name, bpm, root_midi, scale_name, duration_s, melody=melody, seed=seed)
    meta = _meta(genre_name, bpm, root_midi, scale_name, duration_s, seed, "lyrics")
    meta["lyrics"] = lyrics[:500]
    meta["detected_mood"] = mood
    meta["vocal_style"] = vocal_style or "none"
    meta["vocals"] = False
    meta["spec"] = _spec(lyrics, genre_name, bpm, root_midi, scale_name, duration_s, seed)
    if vocal_style in ("singing", "spoken"):
        from . import vocals

        voice = voice or vocals.DEFAULT_VOICE
        meta["voice"] = voice
        sections = song_sections(duration_s, bpm, genre_name, seed=seed)
        vocal_bar = vocal_start_bar(sections)
        try:
            if vocal_style == "singing":
                vocal = vocals.render_singing(lines, voice, bpm=bpm, seed=seed)
            else:
                vocal = vocals.render_spoken(lines, voice, bpm=bpm)
            if vocal is not None:
                start_s = vocal_bar * (4 * 60.0 / bpm)
                L, R = vocals.mix_vocals(L, R, vocal, start_s=start_s)
                meta["vocals"] = True
            else:
                meta["vocals_error"] = "Voice synthesis unavailable (network required)."
        except Exception as exc:  # never let vocals break generation
            meta["vocals_error"] = str(exc)
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
    meta["spec"] = _spec("recording", genre_name, bpm, root_midi, scale_name, duration_s, seed)
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


def _spec(source, genre_name, bpm, root_midi, scale_name, duration_s, seed):
    """HYDAN-style structured spec: sections timeline, instrumentation, mix/master notes."""
    genre = GENRES[genre_name]
    sections = build_sections(max(16, int(round(duration_s / (4 * 60.0 / bpm)))), bpm, genre_name, seed=seed)
    out = []
    for sec in sections:
        times = section_times(sections, bpm)
        label = variation_label(sec["variation"])
        out.append({
            "name": sec["name"],
            "duration": f"{sec['start_bar'] * 4 * 60.0 / bpm:.1f}-{sec['end_bar'] * 4 * 60.0 / bpm:.1f}s",
            "bars": f"{sec['start_bar'] + 1}-{sec['end_bar']}",
            "instruments": genre.get("instruments", [])[:2] + (["drums"] if sec["energy"] >= 0.6 else []),
            "variation": label,
            "vocal_style": sec["vocal_style"],
            "energy": round(sec["energy"], 2),
        })
    return {
        "title": source.strip()[:80].splitlines()[0] if source else "Untitled",
        "genre": genre_name,
        "genre_name": genre["name"],
        "bpm": bpm,
        "key": midi_to_name(root_midi, octave=False),
        "scale": scale_name,
        "mood": (lyrics_mood(source) or "neutral") if source else "neutral",
        "sections": out,
        "lyrics": source[:500] if source else "",
        "mix_notes": genre.get("mix", []),
        "mastering_notes": genre.get("master", []),
        "vocal_guidance": {
            "lead": "Lead vocal melody follows the composed melody phrase (phase-continuous).",
            "backing": "Backing harmonies double the lead a minor/perfect third higher in choruses.",
            "ad_libs": "Ad-libs sit on the last 2 bars of each Chorus and Final Chorus.",
        },
    }
