import { useEffect, useState } from "react";
import { login, signup, setToken, getMe } from "../api";

interface Props {
  onAuthed?: () => void;
  onError?: (msg: string) => void;
}

export default function Auth({ onAuthed, onError }: Props) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [user, setUser] = useState<string | null>(null);

  useEffect(() => {
    if (!localStorage.getItem("sautigen_token")) return;
    getMe()
      .then((me) => setUser(me.username))
      .catch(() => {
        setToken(null);
        setUser(null);
      });
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const res = mode === "login" ? await login(username, password) : await signup(username, password);
      setToken(res.token);
      setUser(res.username);
      setPassword("");
      onAuthed?.();
    } catch (err) {
      onError?.(err instanceof Error ? err.message : "Authentication failed.");
    } finally {
      setBusy(false);
    }
  }

  function logout() {
    setToken(null);
    setUser(null);
    onAuthed?.();
  }

  if (user) {
    return (
      <div className="auth-bar">
        <span className="auth-name">Signed in as <b>{user}</b></span>
        <button className="auth-btn" onClick={logout}>Log out</button>
      </div>
    );
  }

  return (
    <form className="auth-bar" onSubmit={submit}>
      <input
        className="auth-input"
        placeholder="Username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
        minLength={3}
        maxLength={32}
        required
      />
      <input
        className="auth-input"
        type="password"
        placeholder="Password (8+ chars)"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        minLength={8}
        required
      />
      <button className="auth-btn" disabled={busy}>
        {busy ? "…" : mode === "login" ? "Log in" : "Create account"}
      </button>
      <button type="button" className="auth-link" onClick={() => setMode(mode === "login" ? "signup" : "login")}>
        {mode === "login" ? "Sign up instead" : "Log in instead"}
      </button>
    </form>
  );
}
