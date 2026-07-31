# SautiGen - AI Song & Instrumental Generator

Generate songs and instrumentals from a **prompt**, **uploaded lyrics**, or your **own recorded voice**.

Built with a fully procedural audio synthesis engine (no paid AI APIs, no sample packs, works offline). Sauti means "voice/sound" in Swahili.

## Features

- **Three input modes**
  - Prompt a track: describe genre, mood, tempo and key in plain English
  - Upload lyrics: the engine scans syllables and mood, composes a melody line and arranges a full backing track
  - Record your voice: tempo and key are detected from your recording, then a matching backing track is generated
- **7 genre presets**: Afrobeats, Gospel, Hip Hop, Amapiano, Ballad, EDM, Dancehall
- **Key & tempo intelligence**: keys, scales (major/minor/dorian/pentatonic/hijaz) and prompt parsing for "in D minor", "110 BPM", "fast", "slow", moods and genre aliases
- **Melody engine**: syllable-driven lyric-to-melody conversion with phrase contour and line resolution
- **Full production chain**: sidechain pumping, FFT convolution reverb, stereo delay, soft-clip limiting, fade-outs
- **Track library**: per-client storage, playback, download and delete
- **Subscription-ready**: tier/quota system (`free`/`pro`/`studio`) is built in and just needs a payments provider

## Tech Stack

| Layer | Tech |
| --- | --- |
| Backend | FastAPI, NumPy |
| Frontend | React + TypeScript + Vite |
| Audio | Pure NumPy DSP (oscillators, envelopes, filters, drums, effects) |
| Storage | Local filesystem (WAV + JSON metadata) |

## Architecture

```
React Frontend  →  FastAPI API  →  Music Generator
  (record/         /api/generate/    prompt parser
   lyrics/           prompt|lyrics|    melody engine
   prompt)           recording        genre patterns
                                     synthesis engine
                                         |
                                   WAV render + FX
                                         |
                                   local storage  →  stream back to UI
```

## Quick Start

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --port 8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` and `/data` to the backend).

## API

### POST /api/generate/prompt
```json
{
  "prompt": "Upbeat afrobeats track for a Kenyan love song in G major",
  "duration_s": 40
}
```

### POST /api/generate/lyrics
```json
{
  "lyrics": "Nairobi at night, city of lights,\nwe dance through the streets until morning light.",
  "duration_s": 40,
  "genre": null
}
```

### POST /api/generate/recording (multipart)
```
file: recording.webm | genre: afrobeats
```

All generation endpoints accept an `X-Client-Id` header that scopes storage per user.

### Others

| Method | Path | Description |
| --- | --- | --- |
| GET | `/api/tracks` | List generated tracks |
| DELETE | `/api/tracks/{id}` | Delete a track |
| GET | `/api/tiers` | Subscription tiers |
| GET | `/api/health` | Health check |

## Project Layout

```
backend/
  main.py                 FastAPI app + routes
  app/
    music/
      engine.py           Synthesis engine (oscillators, drums, instruments, Track mixer)
      effects.py          Reverb, delay, sidechain, limiting
      scales.py           Notes, keys, scale degrees, chords
      melody.py           Lyrics-to-melody + procedural melodies
      genres.py           Genre presets, drum/bass patterns, mood keywords
      analysis.py         Tempo & key detection for recordings
      generator.py        Arrangement builder + prompt parsing
    config.py             Subscription tiers & quota enforcement
    storage.py            Per-client WAV/JSON storage
    models.py             Pydantic request models
frontend/
  src/
    App.tsx               Tabs: Prompt / Lyrics / Record + library
    api.ts                API client with client-id scoping
    components/           Recorder, LyricsForm, PromptForm, TrackList
```

## Subscription Roadmap

The tier system (`config.py`) is already enforced server-side. To launch paid plans:

1. Add user auth (JWT) and replace the `X-Client-Id` header
2. Wire `tier_for(client_id)` to a payments provider (Stripe/M-Pesa)
3. Serve `stems` (instrumental/melody split) for Pro/Studio tiers
4. Add generation job queue for long tracks

## Examples

`examples/` contains the standalone procedural arrangement of the classic Kenyan gospel chorus "Kanisa Itachengwa Na Akina Nani" that seeded this project.

## License

MIT
