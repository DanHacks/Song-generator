# Sample library

Drop royalty-free WAV one-shots into this folder and the **samples** fallback
engine will sequence them instead of synth tones. When a category is empty the
engine falls back to the NumPy synth automatically, so the app always works.

Layout (see `backend/app/music/samples.py`):

```
assets/samples/
  drums/{kick,snare,hihat,openhat,clap,shaker,cowbell,tom,crash,perc}/*.wav
  bass/      note-named one-shots (e.g. C2.wav, F#2.wav, F#2_02.wav)
  keys/      piano / electric keys one-shots
  guitars/   plucked guitar one-shots
  strings/   sustained string / bowed notes
  ir/        room impulse responses for convolution reverb
```

## Getting a free pack

Run the fetch script to download a small CC0 set (drums + a few notes):

```bash
./scripts/fetch_samples.sh
```

Or drop in any pack you already own. **Only use royalty-free / CC0 samples**
if you plan to publish.

## Fallback

Until samples are added, the `samples` engine produces the same synth output
as before. Add drum one-shots first (`drums/kick`, `drums/snare`, `drums/hihat`)
for the biggest realism gain.