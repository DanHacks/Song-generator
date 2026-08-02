"""Auto-lyrics generator (Phase 3).

Builds a full, structured song (Verse 1 / Pre-Chorus / Chorus / Verse 2 /
Bridge / Final Chorus) from a theme + mood, seeded through SongDirector.
Rule + word-bank based so it's instant and offline. The output is structured
(verse/chorus/bridge) text that feeds the Edge-TTS singing pipeline.

Later, swap ``generate()`` for an LLM call that returns the same shape.
"""

import random


# ---------------------------------------------------------------------------
# Rhyme banks keyed by theme. Each entry is a rhyming (line_a, line_b) pair.
# ---------------------------------------------------------------------------

_BANKS = {
    "love": {
        "verse": [
            ("You and me under the moonlit sky", "hold on, never say goodbye"),
            ("Every beat of my heart calls your name", "we rise together, stay the same"),
            ("In your eyes I found my home", "wherever we go, I'm not alone"),
            ("Soft touch and a warm embrace", "your love is written on my face"),
        ],
        "pre": [
            ("And as the night begins to fall", "I hear your whisper through it all"),
        ],
        "chorus": [
            ("Hold me till the morning light", "nothing can keep us apart tonight"),
            ("We'll chase the stars across the sky", "one heartbeat, you and I"),
        ],
        "bridge": [
            ("Even when the seasons change", "my love for you will still remain"),
        ],
    },
    "party": {
        "verse": [
            ("Speakers pumping, the crowd goes wild", "hands up high, dance floor alive"),
            ("We move to the rhythm all night long", "no stopping now, this is our time"),
            ("Neon lights and golden drums", "everybody here, undone"),
            ("Feel the bass drop to the floor", "then we turn it up once more"),
        ],
        "pre": [
            ("The tension rising in the air", "we let the beat take over here"),
        ],
        "chorus": [
            ("We don't stop until sunrise", "hands up, feel the fire rise"),
            ("Let it go and let it slide", "we rock it through the night"),
        ],
        "bridge": [
            ("Turn it up and let us sing", "we're chasing everything"),
        ],
    },
    "faith": {
        "verse": [
            ("We lift our voices to the sky", "in every season you are my guide"),
            ("Praise in the morning, thanks at night", "your love surrounds me, I'm alive"),
            ("When the storm is raging cold", "your hand still holds me strong"),
            ("I walk the narrow road", "and I will never walk alone"),
        ],
        "pre": [
            ("I lift my eyes up to the light", "your grace is bending through the night"),
        ],
        "chorus": [
            ("Lift your hands and praise", "you are good all our days"),
            ("We sing your mercy from on high", "your love will never die"),
        ],
        "bridge": [
            ("Even when the world falls away", "your word is here to stay"),
        ],
    },
    "hustle": {
        "verse": [
            ("City streets calling, gotta keep the pace", "turn my dreams to gold, no time to waste"),
            ("Every step forward leaves a trail", "one day they'll remember my name"),
            ("Rising from the bottom, building every day", "my grind, my goals, my way"),
            ("No shortcuts through this long road", "I carry fire, light my load"),
        ],
        "pre": [
            ("The hunger in my chest won't ease", "until I make my vision peace"),
        ],
        "chorus": [
            ("We hustle for the dream", "stake our claim, become the theme"),
            ("Turn the grind into victory", "we're building our story"),
        ],
        "bridge": [
            ("When doors close I climb the wall", "my vision cannot fall"),
        ],
    },
    "home": {
        "verse": [
            ("Miles away but my heart stays here", "the soil remembers every tear"),
            ("Calling me back to the place I belong", "home is the melody, sweet and strong"),
            ("Green hills and the river wide", "I carry you close inside"),
            ("Under the broad and open sun", "my homeland, we are one"),
        ],
        "pre": [
            ("I hear the rhythm of the land", "it reaches out and takes my hand"),
        ],
        "chorus": [
            ("Back to my homeland", "where the music always flows"),
            ("Home is the anthem", "calling me wherever I go"),
        ],
        "bridge": [
            ("No land like the one that raised", "my mother's song is engraved"),
        ],
    },
    "night": {
        "verse": [
            ("City lights flicker like falling stars", "neon dreams under the boulevard"),
            ("Midnight secrets whispered in the dark", "dancing shadows leave their mark"),
            ("Street lamps guide the wanderer", "a cold moonbeam over the river"),
            ("The night is young and full of fire", "every corner holds desire"),
        ],
        "pre": [
            ("And as the hours gently pass", "the city hums beneath the stars"),
        ],
        "chorus": [
            ("Under the city lights", "we stay till the morning rise"),
            ("Let the night be our stage", "glow with every silhouette"),
        ],
        "bridge": [
            ("When the dawn begins to steal", "we're dancing, lost in the light"),
        ],
    },
}

_HOOKS = {
    "love": "I need your love tonight",
    "party": "dance all night with me",
    "faith": "lift your hands and praise",
    "hustle": "we hustle for the dream",
    "home": "back to my homeland",
    "night": "under the city lights",
    "energetic": "we don't stop until sunrise",
    "sad": "why did you leave me here",
}


def _bank(theme):
    return _BANKS.get(theme, _BANKS["love"])


def _pairs(lines):
    return [_split_pair(l) for l in lines]


def _split_pair(line):
    if isinstance(line, (tuple, list)):
        a, b = line[0], (line[1] if len(line) > 1 else "")
        return (a.strip(), b.strip())
    a, _, b = line.partition(",")
    return (a.strip(), b.strip()) if b else (a.strip(), "")


def _hook(mood, hook):
    return (hook or _HOOKS.get(mood) or _HOOKS["love"]).strip(",.")

_RHYME_SECOND = [
    ("tonight", ["align", "tonight", "starlight", "ignite"]),
    ("rise", ["eyes", "skies", "realize", "paradise"]),
    ("free", ["me", "dream", "you and me", "be"]),
    ("now", ["how", "wow", "allowed", "the crowd"]),
    ("rhythm", ["this", "with him", "within"]),
]


def _make_chorus(bank, rng, hook):
    """A memorable hook line + a paired payoff line."""
    lines = []
    payoff = _split_pair(bank["chorus"][rng.randrange(len(bank["chorus"]))])
    lines.append(hook + ",")
    lines.append(payoff[1] if rng.random() < 0.6 else payoff[0])
    return lines


def _section_lines(bank, part, rng, n):
    p = bank.get(part, [])
    chosen = rng.sample(p, min(n, len(p))) if p else []
    out = []
    for c in chosen:
        a, b = _split_pair(c)
        if a:
            out.append(a)
        if b:
            out.append(b)
    return out


def generate(theme="love", mood="love", hook=None, verses=2, rng=None):
    """Return a song as [ ('Verse 1', [...lines]), ('Chorus', [...]), ... ]."""
    rng = rng or random.Random()
    bank = _bank(theme)
    hook = _hook(mood, hook)

    chorus = _make_chorus(bank, rng, hook)
    bridge = _section_lines(bank, "bridge", rng, 1)
    pre = _section_lines(bank, "pre", rng, 1)

    song = []
    for v in range(1, max(1, verses) + 1):
        song.append(("Verse %d" % v, _section_lines(bank, "verse", rng, 2)))
        if v == 1 and pre:
            song.append(("Pre-Chorus", pre))
        song.append(("Chorus", list(chorus)))
    song.append(("Bridge", bridge))
    song.append(("Final Chorus", list(chorus)))
    return song


def to_text(song):
    blocks = []
    for name, lines in song:
        blocks.append("[%s]" % name)
        blocks.extend(lines)
    return "\n".join(blocks)