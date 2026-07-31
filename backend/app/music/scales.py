"""Note, scale and key utilities."""

SEMIS = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
         "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}

# Scale intervals in semitones from the tonic, indexed by scale degree 0-6.
SCALES = {
    "major": [0, 2, 4, 5, 7, 9, 11],
    "minor": [0, 2, 3, 5, 7, 8, 10],
    "dorian": [0, 2, 3, 5, 7, 9, 10],
    "pentatonic_major": [0, 2, 4, 7, 9],
    "pentatonic_minor": [0, 3, 5, 7, 10],
    "hijaz": [0, 1, 4, 5, 7, 8, 10],
}

KEYS = list("ABCDEFG") + ["Bb", "Eb", "Ab", "Db", "F#", "C#", "Gb"]
MAJOR_KEYS = KEYS
MINOR_KEYS = [k + "m" for k in KEYS]
ALL_KEYS = MAJOR_KEYS + MINOR_KEYS


def name_to_midi(name):
    name = name.strip().upper()
    if name.endswith("M"):
        name = name[:-1]
    if len(name) >= 2 and name[1] in "#b":
        letter, octave = name[:2], int(name[2:])
    else:
        letter, octave = name[:1], int(name[1:]) if len(name) > 1 else 4
    return 60 + SEMIS[letter] + 12 * (octave - 4)


def midi_to_name(midi, octave=True):
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    pc = midi % 12
    name = names[pc]
    if octave:
        return "%s%d" % (name, (midi // 12) - 1)
    return name


def midi_to_freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12.0)


def parse_key(key):
    """Return (root_midi, scale_name). Accepts 'C', 'Am', 'G major', 'D minor'."""
    key = key.strip().lower().replace("-", " ")
    if key in ("", "auto", "none"):
        return None, None
    if key.endswith(" major") or key.endswith(" maj"):
        root = key.split()[0]
        return name_to_midi(root + "4"), "major"
    if key.endswith(" minor") or key.endswith(" min"):
        root = key.split()[0]
        return name_to_midi(root + "4"), "minor"
    if key.endswith("m"):
        root = key[:-1]
        return name_to_midi(root + "4"), "minor"
    return name_to_midi(key + "4"), "major"


def scale_pc(root_pc, scale_name, degree):
    """PC of a scale degree (0 = tonic) above root pitch class."""
    intervals = SCALES[scale_name]
    n = len(intervals)
    oct = degree // n
    return (root_pc + intervals[degree % n] + 12 * oct) % 12


def chord(root_midi, scale_name, degree, n_notes=3):
    """Build a chord voicing from scale degrees (degree, degree+2, degree+4...)."""
    roots = [root_midi + i * 12 for i in range(0, 3)]
    chosen = []
    base_degree = degree
    for i in range(n_notes):
        d = base_degree + i * 2
        pc = scale_pc(root_midi % 12, scale_name, d)
        # choose the octave that keeps the voicing tight and ascending
        target = chosen[-1] + 2 if chosen else roots[0]
        midi = pc + 12 * ((target - pc) // 12)
        while midi <= chosen[-1] if chosen else False:
            midi += 12
        chosen.append(midi)
    return chosen


def scale_degrees(root_midi, scale_name, lo=-2, hi=4):
    """All scale midi notes in a register range (octaves relative to root)."""
    pc = root_midi % 12
    root_octave = root_midi // 12
    out = []
    for octave in range(lo, hi + 1):
        for deg in range(len(SCALES[scale_name])):
            m = pc + SCALES[scale_name][deg] + 12 * (root_octave + octave)
            out.append(m)
    return sorted(set(out))
