# SautiGen - AI Song & Instrumental Generator

Generate songs and instrumentals from a **prompt**, **uploaded lyrics**, or your **own recorded voice** — with **real neural-voice vocals** and a natural **text-to-speech** studio.

Built with a **hybrid generation stack**: Meta's **MusicGen** (transformer-based, real audio from text) is the primary engine, with a fully procedural NumPy synthesis + royalty-free sample engine as an offline CPU fallback (no paid AI APIs). Sauti means "voice/sound" in Swahili. Real vocals use Microsoft Edge's free neural voices (edge-tts) + DSP (YIN pitch detection, phase-vocoder time-stretch/pitch-shift).

## Features

- **Three input modes**
  - Prompt a track: describe genre, mood, tempo and key in plain English
  - Upload lyrics: the engine scans syllables and mood, composes a melody line and arranges a full backing track
  - Record your voice: tempo and key are detected from your recording, then a matching backing track is generated
- **Real vocals on your songs**: lyrics tracks can be generated with **singing** vocals (each word auto-tuned to the composed melody via edge-tts pitch + DSP) or **spoken/rap** vocals over the beat, in your choice of African/global neural voice
- **Text-to-speech studio**: type any text and get natural neural speech (WAV download) in 8 accents
- **Accounts**: JWT signup/login; your library, quota and subscription follow your account on any device
- **7 genre presets**: Afrobeats, Gospel, Hip Hop, Amapiano, Ballad, EDM, Dancehall
- **Key & tempo intelligence**: keys, scales (major/minor/dorian/pentatonic/hijaz) and prompt parsing for "in D minor", "110 BPM", "fast", "slow", moods and genre aliases
- **Professional HYDAN-style arrangement**: every song is built as a commercial macro-structure — Intro → Verse 1 → Pre-Chorus → Chorus → Verse 2 → Bridge → Final Chorus → Outro — with an anti-repetition rule (each section changes chord inversion, bass rhythm, drum density/style, lead register, stereo width, reverb and transition FX). A full **JSON spec** (sections timeline, instruments, vocal guidance, mix & mastering notes) is attached to every generated track
- **Melody engine**: syllable-driven lyric-to-melody conversion with phrase contour and line resolution
- **Full production chain**: sidechain pumping, FFT convolution reverb, stereo delay, soft-clip limiting, fade-outs
- **Track library**: per-client storage, playback, download and delete
- **Subscriptions**: M-Pesa (Daraja STK Push), Stripe, and a sandbox mock provider with tier/quota enforcement (`free`/`pro`/`studio`)

## Tech Stack

| Layer | Tech |
| --- | --- |
| Backend | FastAPI, NumPy |
| Frontend | React + TypeScript + Vite |
| Audio (primary) | MusicGen (`transformers`, 32kHz → 44.1kHz upmix) |
| Audio (fallback) | NumPy DSP + royalty-free samples (drums/bass/keys) |
| Vocals | Edge-TTS neural voices (singing + spoken + plain TTS) |
| Storage | Local filesystem (WAV + JSON metadata) |

## Generation engines

`GET /api/engine` reports which engine is active.

- **musicgen** (primary): `facebook/musicgen-small` text-to-audio via `transformers`.
  Set `SONGFORGE_MUSICGEN_MODEL` for `facebook/musicgen-medium`/`large` and
  `SONGFORGE_DEVICE=cuda` on GPU hosts. First load downloads ~1.5GB into the HF
  cache; generation runs ~24x realtime on a 4-core CPU, much faster on GPU.
- **samples** (fallback): hybrid NumPy synth + real one-shots from
  `assets/samples/` (see `scripts/fetch_samples.sh`). Always available offline.
  Falls back automatically if MusicGen or its deps are missing.

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

## Share it online

```bash
./scripts/start.sh          # backend + frontend + public Cloudflare tunnel
./scripts/start.sh --stop   # stop everything
```

`start.sh` prints a public `https://*.trycloudflare.com` URL that tunnels straight
to the local API — no account or credit card needed. Point `MPESA_CALLBACK_BASE`
at it in `backend/.env` to receive M-Pesa callbacks (note: quick-tunnel URLs are
ephemeral; use a named tunnel + domain for a permanent URL).

Local config lives in `backend/.env` (copy `backend/.env.example`).

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
  "genre": null,
  "vocal_style": "singing",
  "voice": "en-KE-AsiliaNeural"
}
```

`vocal_style`: `none` (instrumental), `singing` (real voice auto-tuned to the melody), `spoken` (speech over the beat). `voice`: any Edge neural voice, e.g. `en-KE-AsiliaNeural`, `en-NG-EzinneNeural`, `en-TZ-ImaniNeural`, `en-ZA-LeahNeural`, `en-IN-NeerjaNeural`, `en-US-EmmaNeural`. Requires internet at render time; falls back to instrumental if unavailable. The melody line is also now played continuously (not looped per bar).

### POST /api/tts
Natural text-to-speech with no DSP (pure neural voice):
```json
{
  "text": "Karibu SautiGen. Let us make music together.",
  "voice": "en-KE-AsiliaNeural",
  "rate": "+0%",
  "pitch": "+0Hz"
}
```
Returns `{id, audio_url, meta}`; the WAV is stored under `data/{client}/tts/` (separate from your song library). `rate` accepts e.g. `-25%`, `+25%`, `+50%`; `pitch` accepts e.g. `+30Hz`, `-20Hz`.

### POST /api/generate/recording (multipart)
```
file: recording.webm | genre: afrobeats
```

All generation endpoints accept an `X-Client-Id` header that scopes storage per user. Logged-in users can instead send `Authorization: Bearer <token>` — the account's own client id is used automatically.

### Response spec

Every generation response includes `meta.spec`, the structured arrangement blueprint:

```json
{
  "title": "Nairobi at night...",
  "genre": "afrobeats",
  "genre_name": "Afrobeats",
  "bpm": 112,
  "key": "E",
  "scale": "major",
  "mood": "upbeat",
  "sections": [
    { "name": "Intro", "duration": "0.0-6.4s", "bars": "1-2",
      "instruments": ["talking drum", "shaker"], "variation": "chords inverted...",
      "vocal_style": "none", "energy": 0.15 },
    { "name": "Verse 1", "duration": "6.4-17.1s", "bars": "3-5",
      "instruments": ["talking drum", "shaker", "drums"], "variation": "drums 0.70x...",
      "vocal_style": "lead", "energy": 0.55 }
  ],
  "lyrics": "...",
  "mix_notes": ["Long reverb on the piano", "..."],
  "mastering_notes": ["Dynamic, untouched peaks", "..."],
  "vocal_guidance": { "lead": "...", "backing": "...", "ad_libs": "..." }
}
```

The UI shows this as the **Song structure** timeline under each generated track.

## Auth

| Method | Path | Description |
| --- | --- | --- |
| POST | `/api/auth/signup` | Create account (`username`, `password`) → returns JWT |
| POST | `/api/auth/login` | Log in → returns JWT (30-day) |
| GET | `/api/auth/me` | Current user (needs Bearer token) |

Passwords are hashed with PBKDF2-HMAC-SHA256 (200k iterations) and sessions are HS256 JWTs. Tokens auto-migrate the legacy `X-Client-Id` scoping, so anonymous users still work without an account.

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
| POST | `/api/tts` | Natural text-to-speech generation |
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
      melody.py           Lyrics-to-melody (per-line) + procedural melodies
      vocals.py           edge-tts neural voices, YIN pitch detection, phase-vocoder
      genres.py           Genre presets, drum/bass patterns, mood keywords, palettes, mix/master notes
      analysis.py         Tempo & key detection for recordings
      arrangement.py      8-section macro-structure + anti-repetition variation vectors
      generator.py        Section-driven arrangement builder + prompt parsing + spec JSON
    config.py             Subscription tiers & quota enforcement
    billing.py            Subscriptions: M-Pesa / Stripe / mock providers
    auth.py               User accounts + JWT sessions (stdlib PBKDF2 / HS256)
    storage.py            Per-client WAV/JSON storage
    models.py             Pydantic request models
frontend/
  src/
    App.tsx               Tabs: Prompt / Lyrics / Voice / Record / Library / Plans + auth
    api.ts                API client with client-id scoping + JWT bearer
    components/           Recorder, LyricsForm, VoiceStudio, PromptForm, TrackList, Pricing, Auth
```

## Subscription Roadmap

Auth + billing are live (JWT accounts; M-Pesa, Stripe, mock). Remaining work:

1. Create Stripe recurring price IDs for true auto-renewing subscriptions
2. Serve `stems` (instrumental/melody split) for Pro/Studio tiers
3. Add generation job queue for long tracks
4. Email/password reset flows

## Vocals Roadmap

1. More expressive singing (vibrato, held notes, harmonies/second voice)
2. Closer timing (per-word targets already beat-aligned; add breath/gap modeling)
3. Streaming vocals during long generation

## Examples

`examples/` contains the standalone procedural arrangement of the classic Kenyan gospel chorus "Kanisa Itachengwa Na Akina Nani" that seeded this project.

## License

MIT
