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
- **Subscriptions**: M-Pesa (Daraja STK Push), Stripe, and a sandbox mock provider with tier/quota enforcement (`free`/`pro`/`studio`)

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
| GET | `/api/plans` | Subscription plans + provider availability |
| GET | `/api/billing/status` | Current plan, expiry & generation usage |
| POST | `/api/billing/checkout` | Start checkout (`plan`, `provider` `mock\|mpesa\|stripe`, `phone` for M-Pesa) |
| POST | `/api/billing/mock/confirm` | Confirm a mock checkout (dev/demo) |
| POST | `/api/billing/mpesa/callback` | M-Pesa STK Push callback (webhook) |
| POST | `/api/billing/stripe/webhook` | Stripe webhook |
| GET | `/api/tiers` | Subscription tiers |
| GET | `/api/health` | Health check |

## Payments

Providers activate automatically when their credentials are present:

| Provider | Environment variables |
| --- | --- |
| M-Pesa (Daraja STK Push) | `MPESA_ENV` (`sandbox`/`production`), `MPESA_CONSUMER_KEY`, `MPESA_CONSUMER_SECRET`, `MPESA_PASSKEY`, `MPESA_SHORTCODE`, `MPESA_CALLBACK_BASE` (public HTTPS URL for the callback) |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `APP_URL` |
| Mock (sandbox demo) | none — always available for local testing |

Without credentials, the **mock** provider lets the whole flow run locally: start checkout, confirm, and the plan activates (no real money moves).

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
    billing.py            Subscriptions: M-Pesa / Stripe / mock providers
    storage.py            Per-client WAV/JSON storage
    models.py             Pydantic request models
frontend/
  src/
    App.tsx               Tabs: Prompt / Lyrics / Record / Library / Plans
    api.ts                API client with client-id scoping
    components/           Recorder, LyricsForm, PromptForm, TrackList, Pricing
```

## Subscription Roadmap

Billing is live (M-Pesa, Stripe, mock). Remaining work:

1. Add user auth (JWT) and replace the `X-Client-Id` header
2. Create Stripe recurring price IDs for true auto-renewing subscriptions
3. Serve `stems` (instrumental/melody split) for Pro/Studio tiers
4. Add generation job queue for long tracks

## Examples

`examples/` contains the standalone procedural arrangement of the classic Kenyan gospel chorus "Kanisa Itachengwa Na Akina Nani" that seeded this project.

## License

MIT
