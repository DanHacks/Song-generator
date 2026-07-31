import { useState } from "react";
import { generateLyrics } from "../api";

interface Props {
  onGenerated: () => void;
  onError: (msg: string) => void;
}

export default function LyricsForm({ onGenerated, onError }: Props) {
  const [lyrics, setLyrics] = useState("");
  const [genre, setGenre] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function submit() {
    if (!lyrics.trim()) return;
    setLoading(true);
    try {
      const res = await generateLyrics(lyrics, 40, genre);
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
      <h2>Upload lyrics</h2>
      <p className="sub">
        We scan the syllables and mood of your words, compose a melody line and produce a full arrangement.
      </p>

      <label className="field-label">Lyrics</label>
      <textarea
        value={lyrics}
        onChange={(e) => setLyrics(e.target.value)}
        placeholder={"Nairobi at night, city of lights,\nwe dance through the streets until morning light..."}
      />

      <label className="field-label">Genre (optional - auto-detected from lyrics)</label>
      <select value={genre} onChange={(e) => setGenre(e.target.value)}>
        <option value="">Auto detect</option>
        <option value="afrobeats">Afrobeats</option>
        <option value="gospel">Gospel</option>
        <option value="hiphop">Hip Hop</option>
        <option value="amapiano">Amapiano</option>
        <option value="ballad">Ballad</option>
        <option value="edm">EDM</option>
        <option value="dancehall">Dancehall</option>
      </select>

      <button className="gen-btn" onClick={submit} disabled={loading || !lyrics.trim()}>
        {loading ? (
          <>
            <span className="spinner" /> Composing melody...
          </>
        ) : (
          "Generate Song"
        )}
      </button>

      {result && (
        <div className="result">
          <h3>Song generated</h3>
          <div className="chips">
            <span className="chip">{result.meta.genre_name}</span>
            <span className="chip">Key of {result.meta.key}</span>
            <span className="chip">{result.meta.bpm} BPM</span>
            <span className="chip">{result.meta.scale}</span>
          </div>
          <audio controls src={result.audio_url} />
        </div>
      )}
    </div>
  );
}
