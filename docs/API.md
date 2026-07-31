# SautiGen API

Base URL: `http://localhost:8000` (FastAPI, auto docs at `/docs`).

## Health
`GET /api/health` -> `{"status": "ok"}`

## Generate from prompt
`POST /api/generate/prompt`
```json
{ "prompt": "upbeat afrobeats love song", "duration_s": 40, "client_id": "optional" }
```
Returns track `id`, `audio_url`, and `meta` (genre, key, bpm, duration).

## Generate from lyrics
`POST /api/generate/lyrics` — body: `{ "lyrics": "...", "genre": "optional", "client_id": "optional" }`

## Generate from recording
`POST /api/generate/recording` — multipart form `client_id` + `file` (`.wav` only).
Analyzes key/tempo from the recording and generates an accompaniment.

## Streaming audio
`GET /data/<client_id>/<filename>.wav` — full mix as stereo 44.1 kHz WAV.

## Tracks
`GET /api/tracks?client_id=...` — list a client's generated tracks.

## Tiers & quota
- Free: 5 generations
- Pro: 100 generations
- Studio: unlimited
`GET /api/tiers` — plan limits. Exceeding quota returns HTTP 403.
