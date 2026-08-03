import { useState, useEffect } from "react";
import { generatePrompt, getEngines, getGenres, EngineInfo, GenreInfo } from "../api";

interface Props {
  onGenerated: () => void;
  onError: (msg: string) => void;
}

const EXAMPLES: Array<{ text: string; genre?: string }> = [
  { text: "Upbeat nightlife anthem about the city", genre: "afrobeats" },
  { text: "Worship song praising God's faithfulness", genre: "gospel" },
  { text: "Emotional love song about a long-distance heart", genre: "ballad" },
  { text: "Street hustle anthem with a hard-hitting 808", genre: "hiphop" },
  { text: "Chill log-drum dance jam for summer", genre: "amapiano" },
];

export default function PromptForm({ onGenerated, onError }: Props) {
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(40);
  const [engine, setEngine] = useState("fast");
  const [engines, setEngines] = useState<EngineInfo[]>([]);
  const [genres, setGenres] = useState<GenreInfo[]>([]);
  const [selectedGenre, setSelectedGenre] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    getEngines()
      .then((r) => {
        setEngines(r.engines);
        setEngine(r.default || "fast");
      })
      .catch(() => setEngines([{ id: "fast", label: "Fast", description: "", available: true }]));
    getGenres()
      .then((r) => setGenres(r.genres))
      .catch(() => setGenres([]));
  }, []);

  function engineHint() {
    const e = engines.find((x) => x.id === engine);
    if (!e) return "";
    if (!e.available) return "Not available on this machine";
    return e.latency_hint || "";
  }

  async function submit() {
    const value = prompt.trim();
    if (!value) return;
    setLoading(true);
    try {
      const res = await generatePrompt(value, duration, engine, selectedGenre);
      setResult(res);
      onGenerated();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  async function quickStart(ex: { text: string; genre?: string }) {
    setPrompt(ex.text);
    if (ex.genre) setSelectedGenre(ex.genre);
    setLoading(true);
    try {
      const res = await generatePrompt(ex.text, duration, engine, ex.genre || selectedGenre);
      setResult(res);
      onGenerated();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel">
      <h2>Prompt a song</h2>
      <p className="sub">
        Pick a style, then describe the track you want. The engine handles the rest.
      </p>

      <label className="field-label">Pick a genre</label>
      <div className="genre-grid">
        {genres.map((g) => (
          <button
            key={g.id}
            type="button"
            className={"genre-card" + (selectedGenre === g.id ? " active" : "")}
            onClick={() => setSelectedGenre(selectedGenre === g.id ? "" : g.id)}
          >
            <span className="genre-icon">{g.icon}</span>
            <span className="genre-name">{g.name}</span>
            <span className="genre-tag">{g.tagline}</span>
            <span className="genre-bpm">{g.bpm} BPM</span>
          </button>
        ))}
      </div>

      <label className="field-label">Your idea</label>
      <input
        type="text"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. Energetic EDM drop in C minor for a festival set"
      />

      <label className="field-label">Duration: {duration}s</label>
      <input
        type="range"
        min={20}
        max={120}
        step={10}
        value={duration}
        onChange={(e) => setDuration(Number(e.target.value))}
      />

      <label className="field-label">Engine</label>
      <div className="engine-switch">
        {engines.map((e) => (
          <button
            key={e.id}
            type="button"
            className={"engine-opt" + (engine === e.id ? " active" : "") + (e.available ? "" : " disabled")}
            onClick={() => e.available && setEngine(e.id)}
            title={e.error || e.description}
          >
            {e.id === "musicgen" ? "AI MusicGen" : "Fast synth"}
            {!e.available && <span className="engine-offline"> offline</span>}
          </button>
        ))}
        <span className="engine-hint">{engineHint()}</span>
      </div>

      <button className="gen-btn" onClick={() => submit()} disabled={loading || !prompt.trim()}>
        {loading ? (
          <>
            <span className="spinner" />{" "}
            {engine === "musicgen"
              ? "MusicGen is generating (can take a few minutes on CPU)..."
              : "Arranging instruments and mixing..."}
          </>
        ) : (
          "Generate Track"
        )}
      </button>

      <div className="chips" style={{ marginTop: 14 }}>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.text}
            className="chip"
            style={{ cursor: "pointer", border: "1px solid #334155" }}
            onClick={() => quickStart(ex)}
            disabled={loading}
          >
            {ex.text}
          </button>
        ))}
      </div>

      {result && (
        <div className="result">
          <h3>Track generated</h3>
          <div className="chips">
            <span className="chip">{result.meta.genre_name}</span>
            <span className="chip">Key of {result.meta.key}</span>
            <span className="chip">{result.meta.bpm} BPM</span>
          </div>
          <audio controls src={result.audio_url} />
          {result.meta.spec?.sections && (
            <div className="structure">
              <h4>Song structure</h4>
              <ol className="section-list">
                {result.meta.spec.sections.map(
                  (sec: { name: string; duration: string; vocal_style: string; variation: string }, i: number) => (
                    <li key={i} className="section-row">
                      <span className="section-name">{sec.name}</span>
                      <span className="section-time">{sec.duration}</span>
                      <span className="section-vocals">{sec.vocal_style}</span>
                      <span className="section-variation">{sec.variation}</span>
                    </li>
                  ),
                )}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}