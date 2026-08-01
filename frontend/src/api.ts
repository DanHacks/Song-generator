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
  audio_url?: string;
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

let token: string | null = localStorage.getItem("sautigen_token");

export function setToken(t: string | null) {
  token = t;
  if (t) localStorage.setItem("sautigen_token", t);
  else localStorage.removeItem("sautigen_token");
}

export function authHeaders(): Record<string, string> {
  return token ? { Authorization: "Bearer " + token } : {};
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    ...options,
    headers: {
      "X-Client-Id": clientId!,
      "Content-Type": "application/json",
      ...authHeaders(),
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

export function signup(username: string, password: string) {
  return api<{ username: string; client_id: string; token: string }>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function login(username: string, password: string) {
  return api<{ username: string; client_id: string; token: string }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function getMe() {
  return api<{ username: string; client_id: string }>("/api/auth/me");
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
    headers: { "X-Client-Id": clientId!, ...authHeaders() },
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

export interface Plan {
  label: string;
  max_generations: number | null;
  max_duration_s: number;
  stems: boolean;
  price_usd: number;
  price_kes: number;
}

export interface ProvidersStatus {
  mock: boolean;
  mpesa: boolean;
  stripe: boolean;
}

export interface PlansResponse {
  plans: Record<string, Plan>;
  providers: ProvidersStatus;
}

export interface BillingStatus {
  tier: string;
  label: string;
  expires_at: string | null;
  max_duration_s: number;
  stems: boolean;
  usage: { used: number; max: number | null; remaining: number | null };
  payments: Array<{ plan: string; source: string; reference: string; date: string; amount: number }>;
}

export function getPlans() {
  return api<PlansResponse>("/api/plans");
}

export function getBillingStatus() {
  return api<BillingStatus>("/api/billing/status");
}

export async function checkout(plan: string, provider: string, phone?: string) {
  return api<Record<string, unknown>>("/api/billing/checkout", {
    method: "POST",
    body: JSON.stringify({ plan, provider, phone: phone || null }),
  });
}

export async function mockConfirm(checkoutId: string) {
  return api<Record<string, unknown>>("/api/billing/mock/confirm", {
    method: "POST",
    body: JSON.stringify({ checkout_id: checkoutId }),
  });
}
