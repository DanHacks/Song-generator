"""Section-based song arrangement (HYDAN AI STUDIO structure).

A song is broken into the commercial-release macro-structure:

    Intro -> Verse 1 -> Pre-Chorus -> Chorus -> Verse 2 -> Bridge
          -> Final Chorus -> Outro

Every section carries a variation vector so no two consecutive sections share
the same arrangement (anti-repetition rule: each new section changes at least
three of chord inversion, drum pattern, bass rhythm, melody register,
instrument layering, stereo width, reverb amount, percussion density and
transition effects).
"""

# ---------------------------------------------------------------------------
# Section macro-structure
# ---------------------------------------------------------------------------

SECTION_TEMPLATES = [
    {
        "name": "Intro",
        "energy": 0.15, "weight": 0.08, "transition": "none",
        "vocal_style": "none",
        "variation": {
            "chord_inversion": 2, "register": -12, "density": 0.3, "drum_style": 0, "extra": None,
            "bass": None, "melody_octave": 1.0, "width": 0.7, "reverb": 1.3,
            "layering": {"pad": True, "stab": False, "arp": False, "bell": True, "lead": False, "harmony": False},
        },
    },
    {
        "name": "Verse 1",
        "energy": 0.55, "weight": 0.14, "transition": "fill",
        "vocal_style": "lead",
        "variation": {
            "chord_inversion": 0, "register": 0, "density": 0.7, "drum_style": 0, "extra": None,
            "bass": 0, "melody_octave": 1.0, "width": 1.0, "reverb": 0.85,
            "layering": {"pad": True, "stab": False, "arp": True, "bell": False, "lead": True, "harmony": False},
        },
    },
    {
        "name": "Pre-Chorus",
        "energy": 0.78, "weight": 0.10, "transition": "riser",
        "vocal_style": "lead",
        "variation": {
            "chord_inversion": 1, "register": 12, "density": 0.9, "drum_style": 1, "extra": "roll",
            "bass": 1, "melody_octave": 1.0, "width": 1.1, "reverb": 0.95,
            "layering": {"pad": True, "stab": True, "arp": True, "bell": False, "lead": True, "harmony": False},
        },
    },
    {
        "name": "Chorus",
        "energy": 1.0, "weight": 0.16, "transition": "crash",
        "vocal_style": "lead + backing",
        "variation": {
            "chord_inversion": 0, "register": 0, "density": 1.0, "drum_style": 0, "extra": None,
            "bass": 0, "melody_octave": 1.0, "width": 1.3, "reverb": 1.1,
            "layering": {"pad": True, "stab": True, "arp": True, "bell": True, "lead": True, "harmony": True},
        },
    },
    {
        "name": "Verse 2",
        "energy": 0.65, "weight": 0.14, "transition": "fill",
        "vocal_style": "lead",
        "variation": {
            "chord_inversion": 2, "register": -12, "density": 0.75, "drum_style": 2, "extra": None,
            "bass": 2, "melody_octave": 1.0, "width": 1.0, "reverb": 0.9,
            "layering": {"pad": True, "stab": False, "arp": False, "bell": True, "lead": True, "harmony": False},
        },
    },
    {
        "name": "Bridge",
        "energy": 0.45, "weight": 0.10, "transition": "reverse",
        "vocal_style": "lead",
        "variation": {
            "chord_inversion": 1, "register": 12, "density": 0.4, "drum_style": 2, "extra": None,
            "bass": 1, "melody_octave": 1.0, "width": 1.4, "reverb": 1.4,
            "layering": {"pad": True, "stab": False, "arp": True, "bell": False, "lead": True, "harmony": False},
        },
    },
    {
        "name": "Final Chorus",
        "energy": 1.15, "weight": 0.18, "transition": "crash",
        "vocal_style": "lead + backing + ad-libs",
        "variation": {
            "chord_inversion": 0, "register": 0, "density": 1.25, "drum_style": 0, "extra": "fill",
            "bass": 0, "melody_octave": 2.0, "width": 1.5, "reverb": 1.2,
            "layering": {"pad": True, "stab": True, "arp": True, "bell": True, "lead": True, "harmony": True},
        },
    },
    {
        "name": "Outro",
        "energy": 0.25, "weight": 0.10, "transition": "none",
        "vocal_style": "none",
        "variation": {
            "chord_inversion": 2, "register": -12, "density": 0.3, "drum_style": 0, "extra": None,
            "bass": None, "melody_octave": 1.0, "width": 0.8, "reverb": 1.4,
            "layering": {"pad": True, "stab": False, "arp": False, "bell": True, "lead": False, "harmony": False},
        },
    },
]


def _alloc_bars(n_bars):
    """Allocate n_bars across templates (>=1 each, exact total)."""
    k = len(SECTION_TEMPLATES)
    weights = [t["weight"] for t in SECTION_TEMPLATES]
    if n_bars < k:
        # degenerate: still give every section at least one bar by over-running
        return [1] * k
    base = [max(1, int(n_bars * w)) for w in weights]
    total = sum(base)
    fracs = sorted(
        range(k),
        key=lambda i: (n_bars * weights[i] - int(n_bars * weights[i]), i),
        reverse=True,
    )
    i = 0
    while total < n_bars:
        base[fracs[i % k]] += 1
        total += 1
        i += 1
    while total > n_bars:
        cands = [j for j in range(k) if base[j] > 1]
        if not cands:
            break
        j = max(cands, key=lambda j: base[j])
        base[j] -= 1
        total -= 1
    return base


def build_sections(n_bars, bpm, genre_name, seed=None, with_vocals=False):
    """Return the arranged sections for a song.

    Each section: {name, start_bar, end_bar, energy, transition, vocal_style,
    instruments (genre palette), duration_s, variation}.
    """
    bars = _alloc_bars(n_bars)
    from .genres import GENRES

    instruments = list(GENRES[genre_name].get("instruments", []))
    sections = []
    pos = 0
    bar_len = 4 * 60.0 / bpm
    for t, n in zip(SECTION_TEMPLATES, bars):
        end = min(pos + n, n_bars)
        if end <= pos:
            continue
        sections.append(
            {
                "name": t["name"],
                "start_bar": pos,
                "end_bar": end,
                "energy": t["energy"],
                "transition": t["transition"],
                "vocal_style": t["vocal_style"],
                "instruments": instruments,
                "duration_s": (end - pos) * bar_len,
                "variation": dict(t["variation"]),
            }
        )
        pos = end
    return sections


def vocal_start_bar(sections):
    """First bar where vocals should enter (first non-instrumental section)."""
    for sec in sections:
        if sec["vocal_style"] not in ("", "none"):
            return sec["start_bar"]
    return sections[1]["start_bar"] if len(sections) > 1 else 0


def section_times(sections, bpm):
    """Map each section to a 'm:ss-m:ss' string."""
    bar_len = 4 * 60.0 / bpm

    def fmt(s):
        m = int(s // 60)
        ss = int(s % 60)
        return "%d:%02d" % (m, ss)

    out = []
    for sec in sections:
        s0 = sec["start_bar"] * bar_len
        s1 = sec["end_bar"] * bar_len
        out.append("%s-%s" % (fmt(s0), fmt(s1)))
    return out


def variation_label(v):
    """Human-readable anti-repetition summary for a section."""
    parts = []
    if v["chord_inversion"]:
        parts.append("chords inverted")
    if v["register"] != 0:
        parts.append("register %+d" % v["register"])
    if v["bass"] not in (None, 0):
        parts.append("bass v%d" % v["bass"])
    if v["bass"] is None:
        parts.append("no bass")
    parts.append("drums %.2fx" % v["density"])
    if v["drum_style"]:
        parts.append("drum style %d" % v["drum_style"])
    if v["extra"]:
        parts.append(v["extra"])
    if v["melody_octave"] != 1.0:
        parts.append("lead x%.0f" % v["melody_octave"])
    if v["width"] not in (1.0,):
        parts.append("width %.1f" % v["width"])
    if v["reverb"] != 1.0:
        parts.append("reverb %.1f" % v["reverb"])
    return ", ".join(parts) or "baseline"
