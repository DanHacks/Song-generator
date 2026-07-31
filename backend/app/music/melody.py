"""Melody generation: from lyrics (syllable-driven) or procedural random-walk."""

import re
import hashlib
import numpy as np

from .scales import scale_degrees, scale_pc, SCALES


def _seed_for(text):
    return int(hashlib.md5(text.encode("utf-8")).hexdigest()[:8], 16)


def _syllables(word):
    """Rough syllable count for English/Swahili words via vowel groups."""
    word = re.sub(r"[^a-z0-9]", "", word.lower())
    if not word:
        return 1
    vowels = "aeiouy"
    groups = re.findall(r"[%s]+" % vowels, word)
    count = len(groups)
    if word.endswith("e") and len(word) > 2 and word[-2] not in vowels:
        count = max(count - 1, 1)
    if count == 0:
        return 1
    return count


def split_lines(lyrics):
    lines = [l.strip() for l in lyrics.splitlines()]
    lines = [l for l in lines if l]
    if not lines:
        lines = ["la la la"]
    return lines


def _rhythm_from_words(words, beats_per_line):
    """Distribute syllable durations across a line. Returns list of (beats, is_stress)."""
    syls = [_syllables(w) for w in words]
    total = sum(syls)
    if total == 0:
        return [(1.0, False)] * int(beats_per_line)
    step = beats_per_line / total
    out = []
    for w, s in zip(words, syls):
        for k in range(s):
            out.append((step, k == 0))
    # snap short steps to musical values
    snapped = []
    for beats, stress in out:
        b = min(max(round(beats * 4) / 4.0, 0.25), 2.0)
        snapped.append((b, stress))
    return snapped


def lyrics_to_melody(lyrics, root_midi, scale_name, seed=None):
    """Convert lyrics into (note, beats) list. note is midi or None (rest)."""
    rng = np.random.default_rng(seed if seed is not None else _seed_for(lyrics))
    lines = split_lines(lyrics)
    scale = SCALES[scale_name]
    result = []
    phrase = 0
    for line in lines:
        words = re.findall(r"[\w']+|[.,!?;:]", line)
        words = [w for w in words if re.match(r"[\w']+", w)]
        if not words:
            result.append((None, 2.0))
            continue
        beats = 4.0 if phrase % 2 == 0 else 6.0
        rhythm = _rhythm_from_words(words, beats)
        start_degree = [5, 0, 3, 2, 4, 1][phrase % 6]
        degree = start_degree
        for b, stress in rhythm:
            if rng.random() < 0.06:
                result.append((None, b))
                continue
            degree = max(0, degree + int(rng.choice([-2, -1, 0, 1, 1, 2])))
            degree = min(degree, 5)
            midi = root_midi + scale[degree % len(scale)]
            if degree >= len(scale):
                midi += 12
            if stress and rng.random() < 0.5:
                midi += 12
            if midi > root_midi + 19:
                midi -= 12
            if midi < root_midi + 7:
                midi += 12
            result.append((midi, b))
        # end of line resolution
        resolution = root_midi if phrase % 2 == 0 else root_midi + scale[4] - scale[0]
        result.append((resolution, 1.0))
        result.append((None, 1.0))
        phrase += 1
    return result


def random_melody(root_midi, scale_name, bars, bpm, seed=None, density=0.8, register_lo=7, register_hi=19):
    """Procedural pentatonic-ish random walk melody. Returns (note, beats) list."""
    rng = np.random.default_rng(seed)
    pool = scale_degrees(root_midi, scale_name, 0, 2)
    pool = [m for m in pool if register_lo <= m - root_midi <= register_hi]
    total_beats = bars * 4
    out = []
    pos = 0
    current = pool[len(pool) // 2]
    phrase_dir = 1
    while pos < total_beats:
        beats = rng.choice([0.5, 0.5, 1.0, 1.0, 1.5, 2.0])
        if pos + beats > total_beats:
            beats = total_beats - pos
        if rng.random() < 0.12:
            out.append((None, beats))
            pos += beats
            continue
        step = int(rng.choice([-3, -2, -1, -1, 0, 1, 1, 2, 3]))
        idx = pool.index(current) if current in pool else len(pool) // 2
        idx = min(max(idx + step, 0), len(pool) - 1)
        current = pool[idx]
        if rng.random() < density:
            out.append((current, beats))
        else:
            out.append((None, beats))
        pos += beats
        if pos % (8) == 0:
            phrase_dir = -phrase_dir
            current = pool[min(max(idx + phrase_dir * 2, 0), len(pool) - 1)]
    return out


def lyrics_mood(lyrics):
    """Simple keyword mood detection -> one of the genre mood lists or None."""
    text = lyrics.lower()
    scores = {}
    from .genres import MOOD_WORDS
    for mood, words in MOOD_WORDS.items():
        scores[mood] = sum(text.count(w) for w in words)
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return None
    return best


def lyric_line_count(lyrics):
    return len(split_lines(lyrics))
