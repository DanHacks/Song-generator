"""SongDirector — prompt expansion service (Phase 2).

Turns a simple user prompt ("kenyan love song, slow and romantic") into a full
production brief: genre, BPM, key, mood, structure, instrumentation, vocal
style, lyrical theme and a viral hook. Also builds a MusicGen-optimized text
prompt so the generative engine gets a rich, consistent condition.

Rule + template based (offline, no LLM API needed). Future: swap the heuristic
``_expand`` for an LLM call via the same ``direct()`` interface.
"""

import re

from .genres import GENRES, GENRE_ALIASES, TEMPO_WORDS, MOOD_WORDS
from .melody import lyrics_mood


# ---------------------------------------------------------------------------
# Recognition
# ---------------------------------------------------------------------------

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
    m = re.search(r"\bkey of ([a-g](?:#|b)?)(?: (major|minor|min|m))?\b", text.lower())
    if m:
        return m.group(1), ("major" if m.group(2) in (None, "major") else "minor")
    m2 = re.search(r"\b([a-g](?:#|b)?)[ -]?(m|min|minor|maj|major)\b", text.lower())
    if m2:
        return m2.group(1), ("minor" if m2.group(2) in ("m", "min", "minor") else "major")
    return None, None


def _find_bpm(text, genre_name):
    t = text.lower()
    m = re.search(r"(\d{2,3})\s*(?:bpm|beats per minute)", t)
    if m:
        return int(m.group(1))
    base = GENRES[genre_name]["bpm"]
    factor = 1.0
    for word, f in TEMPO_WORDS.items():
        if word in t:
            factor *= f
    return int(round(base * factor))


def _mood(text):
    mood = lyrics_mood(text)
    if mood:
        return mood
    t = text.lower()
    if any(w in t for w in ("happy", "joy", "party", "dance", "celebration")):
        return "energetic"
    if any(w in t for w in ("sad", "heartbreak", "breakup", "tears", "lonely")):
        return "sad"
    if any(w in t for w in ("love", "romance", "baby", "crush")):
        return "love"
    return "neutral"


def _theme(text):
    t = text.lower()
    themes = {
        "love": ["love", "romance", "baby", "crush", "kiss", "heart"],
        "party": ["party", "club", "dance", "celebration", "weekend"],
        "faith": ["god", "worship", "praise", "faith", "prayer", "church"],
        "hustle": ["hustle", "grind", "money", "success", "city", "street"],
        "home": ["home", "kenya", "africa", "country", "roots", "family"],
        "night": ["night", "moon", "stars", "city lights", "midnight"],
    }
    best, score = None, 0
    for theme, words in themes.items():
        s = sum(t.count(w) for w in words)
        if s > score:
            best, score = theme, s
    return best or "love"


HOOKS = {
    "love": "I need your love tonight",
    "party": "dance all night with me",
    "faith": "lift your hands and praise",
    "hustle": "we hustle for the dream",
    "home": "back to my homeland",
    "night": "under the city lights",
    "energetic": "we don't stop until sunrise",
    "sad": "why did you leave me here",
    "neutral": "feel the rhythm take control",
}

_ENERGY_ADJS = {
    "energetic": "high-energy, danceable",
    "sad": "emotional, melancholic",
    "love": "romantic, warm",
    "faith": "uplifting, anthemic",
    "neutral": "groovy, atmospheric",
}


def _instrumentation(genre_name, mood):
    instr = GENRES[genre_name].get("instruments", [])
    if mood == "sad":
        instr = [i for i in instr if "808" not in i][:2] + ["soft piano", "ambient pads"]
    return instr or ["drums", "bass", "keys"]


# ---------------------------------------------------------------------------
# Lyric/theme generation (rule-based seed)
# ---------------------------------------------------------------------------

def sample_lyrics(theme, mood, genre_name, lines=4):
    """Generate a short starter lyric block from the theme + mood."""
    bank = {
        "love": [
            "You and me under the moonlit sky",
            "Hold my hand, never say goodbye",
            "Every beat of my heart calls your name",
            "Together we rise, together we stay",
        ],
        "party": [
            "The speakers pumping, the crowd goes wild",
            "Hands up high, dance floor alive",
            "We move to the rhythm all night long",
            "No stopping now, this is our time",
        ],
        "faith": [
            "We lift our voices to the sky",
            "In every season, you are my guide",
            "Praise in the morning, thanks at night",
            "Your love surrounds me, I am alive",
        ],
        "hustle": [
            "City streets calling, gotta keep the pace",
            "Turn my dreams to gold, no time to waste",
            "Every step forward, leaving trails behind",
            "One day they'll remember my name",
        ],
        "home": [
            "Miles away but my heart stays here",
            "The soil remembers every tear",
            "Calling me back to the place I belong",
            "Home is the melody, sweet and strong",
        ],
        "night": [
            "City lights flicker like falling stars",
            "Neon dreams under the boulevard",
            "Midnight secrets whispered in the dark",
            "Dancing shadows leave their mark",
        ],
    }
    pool = bank.get(theme, bank["love"])
    out = []
    for i in range(lines):
        out.append(pool[i % len(pool)])
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Auto lyrics (Phase 3)
# ---------------------------------------------------------------------------

def _auto_lyrics(theme, mood, hook):
    from .lyricsgen import generate, to_text
    song = generate(theme=theme, mood=mood, hook=hook)
    return to_text(song)


# ---------------------------------------------------------------------------
# MusicGen prompt builder
# ---------------------------------------------------------------------------

def _mg_prompt(genre_name, bpm, key_name, scale, mood, theme, vibe, hook):
    gname = GENRES[genre_name]["name"]
    parts = [gname.lower()]
    if scale and key_name:
        parts.append("in %s %s" % (key_name, scale))
    if bpm:
        parts.append("at %d bpm" % bpm)
    if mood != "neutral":
        parts.append(_ENERGY_ADJS.get(mood, mood))
    if vibe:
        parts.append(vibe)
    if theme and theme not in ("love", "neutral"):
        parts.append(theme)
    # instrument texture helps MusicGen's output quality a lot
    instr = GENRES[genre_name].get("instruments", [])[:4]
    if instr:
        parts.append("with " + ", ".join(instr))
    parts.append("clean studio recording, radio quality")
    return ", ".join(parts) + (". hook: %s." % hook if hook else "")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def direct(prompt, duration_s=40.0, overrides=None):
    """Expand a user prompt into a full SongDirector brief.

    Returns: {spec, prompt_mg, lyrics, hook, meta} where spec is the HYDAN
    structure JSON and prompt_mg is the MusicGen text condition.
    """
    overrides = overrides or {}
    genre_name = overrides.get("genre") or _find_genre(prompt)
    key_name, scale = overrides.get("key") or _find_key(prompt)[0], _find_key(prompt)[1]
    if overrides.get("key") and overrides.get("scale"):
        key_name, scale = overrides["key"], overrides["scale"]
    if key_name:
        key_name = key_name[0].upper() + key_name[1:]
    bpm = int(overrides.get("bpm") or _find_bpm(prompt, genre_name))
    mood = _mood(prompt)
    theme = _theme(prompt)
    vibe = overrides.get("vibe")
    hook = overrides.get("hook") or HOOKS.get(mood) or HOOKS["neutral"]
    gname = GENRES[genre_name]["name"]

    sections = _structure(duration_s, bpm, genre_name)
    lyrics_structured = _auto_lyrics(theme, mood, hook)
    spec = {
        "title": _title(prompt),
        "genre": genre_name,
        "genre_name": gname,
        "bpm": bpm,
        "key": key_name or _default_key(genre_name),
        "scale": scale or GENRES[genre_name]["scale"],
        "mood": mood,
        "theme": theme,
        "vibe": vibe,
        "hook": hook,
        "structure": sections,
        "instruments": _instrumentation(genre_name, mood),
        "vocal_style": _vocal_style(genre_name, mood),
        "lyrics": lyrics_structured,
        "mix_notes": GENRES[genre_name].get("mix", []),
        "mastering_notes": GENRES[genre_name].get("master", []),
    }
    prompt_mg = _mg_prompt(genre_name, bpm, spec["key"], spec["scale"], mood, theme, vibe, hook)
    return {
        "spec": spec,
        "prompt_mg": prompt_mg,
        "lyrics": spec["lyrics"],
        "hook": hook,
        "meta": {"engine": "songdirector", "genre": genre_name, "bpm": bpm, "mood": mood},
    }


def _title(prompt):
    words = [w for w in prompt.split() if len(w) > 2][:5]
    return " ".join(words).title() if words else "Untitled"


def _default_key(genre_name):
    keys = ["C", "G", "D", "A", "E", "F", "B", "F#", "C#"]
    i = list(GENRES.keys()).index(genre_name) % len(keys) if genre_name in GENRES else 0
    return keys[i]


def _vocal_style(genre_name, mood):
    if mood == "faith":
        return "choir + lead"
    if mood == "sad":
        return "emotional lead"
    if genre_name in ("hiphop", "dancehall"):
        return "rap/chant lead"
    if genre_name == "gospel":
        return "choir + lead"
    return "lead + backing"


def _structure(duration_s, bpm, genre_name):
    from .arrangement import build_sections, section_times, variation_label
    n_bars = max(16, int(round(duration_s / (4 * 60.0 / bpm))))
    sections = build_sections(n_bars, bpm, genre_name)
    out = []
    for sec in sections:
        out.append({
            "name": sec["name"],
            "bars": "%d-%d" % (sec["start_bar"] + 1, sec["end_bar"]),
            "variation": variation_label(sec["variation"]),
            "vocal_style": sec["vocal_style"],
            "energy": sec["energy"],
        })
    return out
