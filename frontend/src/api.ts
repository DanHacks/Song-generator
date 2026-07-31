const BASE = "";

export interface TrackMeta {
  id: string;
  mode: string;
  genre: string;
  genre_name: string;
  bpm: number;
  key: string;
  scale: string;
  duration_s: number;
  prompt?: string;
  lyrics?: string;
  recording_analysis?: {
    bpm: number;
    key: string;
    mode: string;
    duration_s: number;
    recording_name?: string;
  };
  filename?: string;
  created_at?: string;
}

export interface Track {
  meta?: TrackMeta;
  [key: string]: unknown;
}

let clientId = localStorage.getItem("songforge_client_id");
if (!clientId) {
  clientId = "client_" + Math.random().toString(36).slice(2, 10);
  localStorage.setItem("songforge_client_id", clientId);
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    ...options,
    headers: {
      "X-Client-Id": clientId!,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json() as Promise<T>;
}

export function generatePrompt(prompt: string, duration: number) {
  return api("/api/generate/prompt", {
    method: "POST",
    body: JSON.stringify({ prompt, duration_s: duration }),
  });
}

export function generateLyrics(lyrics: string, duration: number, genre: string) {
  return api("/api/generate/lyrics", {
    method: "POST",
    body: JSON.stringify({ lyrics, duration_s: duration, genre: genre || null }),
  });
}

export async function generateRecording(file: File, genre: string) {
  const form = new FormData();
  form.append("file", file);
  if (genre) form.append("genre", genre);
  const res = await fetch(BASE + "/api/generate/recording", {
    method: "POST",
    headers: { "X-Client-Id": clientId! },
    body: form,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export function listTracks() {
  return api<TrackMeta[]>("/api/tracks");
}

export function deleteTrack(id: string) {
  return api("/api/tracks/" + id, { method: "DELETE" });
}

export function audioUrl(path: string) {
  return BASE + path;
}
