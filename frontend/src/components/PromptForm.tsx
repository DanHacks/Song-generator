import { useState } from "react";
import { generatePrompt } from "../api";

interface Props {
  onGenerated: () => void;
  onError: (msg: string) => void;
}

const EXAMPLES = [
  "Upbeat afrobeats track about Nairobi nightlife",
  "Gospel worship song praising God's faithfulness",
  "Slow romantic ballad about lost love",
  "Dark hip hop beat for a street hustle anthem",
  "Amapiano jam with a chill South African vibe",
];

export default function PromptForm({ onGenerated, onError }: Props) {
  const [prompt, setPrompt] = useState("");
  const [duration, setDuration] = useState(40);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function submit(text?: string) {
    const value = (text ?? prompt).trim();
    if (!value) return;
    if (text) setPrompt(text);
    setLoading(true);
    try {
      const res = await generatePrompt(value, duration);
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
        Describe the track you want - genre, mood, tempo, key. The engine handles the rest.
      </p>

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

      <button className="gen-btn" onClick={() => submit()} disabled={loading || !prompt.trim()}>
        {loading ? (
          <>
            <span className="spinner" /> Generating track...
          </>
        ) : (
          "Generate Track"
        )}
      </button>

      <div className="chips" style={{ marginTop: 14 }}>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            className="chip"
            style={{ cursor: "pointer", border: "1px solid #334155" }}
            onClick={() => submit(ex)}
          >
            {ex}
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
