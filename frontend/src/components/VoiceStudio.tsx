import { useState } from "react";
import { generateTTS, VOICES } from "../api";

interface Props {
  onError: (msg: string) => void;
}

export default function VoiceStudio({ onError }: Props) {
  const [text, setText] = useState(
    "Karibu SautiGen. We turn your words into music with natural African voices.",
  );
  const [voice, setVoice] = useState(VOICES[0]);
  const [rate, setRate] = useState("+0%");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function submit() {
    if (!text.trim()) return;
    setLoading(true);
    try {
      const res = await generateTTS(text, voice, rate);
      setResult(res);
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel">
      <h2>Text to Speech</h2>
      <p className="sub">
        A natural neural text-to-speech generator. Type anything and hear it spoken by an AI voice in your
        choice of accent.
      </p>

      <label className="field-label">Text</label>
      <textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="What should be spoken?" />

      <div className="row">
        <div className="col">
          <label className="field-label">Voice</label>
          <select value={voice} onChange={(e) => setVoice(e.target.value)}>
            {VOICES.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </div>
        <div className="col">
          <label className="field-label">Speed</label>
          <select value={rate} onChange={(e) => setRate(e.target.value)}>
            <option value="-25%">Slow</option>
            <option value="+0%">Normal</option>
            <option value="+25%">Fast</option>
            <option value="+50%">Rap</option>
          </select>
        </div>
      </div>

      <button className="gen-btn" onClick={submit} disabled={loading || !text.trim()}>
        {loading ? (
          <>
            <span className="spinner" /> Speaking...
          </>
        ) : (
          "Generate Speech"
        )}
      </button>

      {result && (
        <div className="result">
          <h3>Speech generated</h3>
          <div className="chips">
            <span className="chip">{result.meta.voice}</span>
            <span className="chip">{result.meta.duration_s}s</span>
            <span className="chip">{result.meta.rate}</span>
          </div>
          <audio controls src={result.audio_url} />
          <a className="dl-link" href={result.audio_url} download>
            Download WAV
          </a>
        </div>
      )}
    </div>
  );
}
