import { useState } from "react";
import { generateLyrics, VOICES } from "../api";

interface Props {
  onGenerated: () => void;
  onError: (msg: string) => void;
}

export default function LyricsForm({ onGenerated, onError }: Props) {
  const [lyrics, setLyrics] = useState("");
  const [genre, setGenre] = useState("");
  const [vocalStyle, setVocalStyle] = useState("singing");
  const [voice, setVoice] = useState(VOICES[0]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);

  async function submit() {
    if (!lyrics.trim()) return;
    setLoading(true);
    try {
      const res = await generateLyrics(lyrics, 40, genre, vocalStyle, voice);
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
        We scan the syllables and mood of your words, compose a melody line, and produce a full arrangement
        with a real neural voice singing them.
      </p>

      <label className="field-label">Lyrics</label>
      <textarea
        value={lyrics}
        onChange={(e) => setLyrics(e.target.value)}
        placeholder={"Nairobi at night, city of lights,\nwe dance through the streets until morning light..."}
      />

      <div className="row">
        <div className="col">
          <label className="field-label">Genre (optional - auto-detected)</label>
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
        </div>
        <div className="col">
          <label className="field-label">Vocals</label>
          <select value={vocalStyle} onChange={(e) => setVocalStyle(e.target.value)}>
            <option value="singing">Singing (melody)</option>
            <option value="spoken">Spoken / rap over beat</option>
            <option value="none">Instrumental only</option>
          </select>
        </div>
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
      </div>

      <button className="gen-btn" onClick={submit} disabled={loading || !lyrics.trim()}>
        {loading ? (
          <>
            <span className="spinner" /> Composing with {voice.split("-")[1]} voice...
          </>
        ) : (
          "Generate Song"
        )}
      </button>
      <p className="sub" style={{ marginTop: 8 }}>
        Singing vocals use the free Edge neural voices (needs internet). If unavailable, the track falls back to
        instrumental.
      </p>

      {result && (
        <div className="result">
          <h3>Song generated</h3>
          <div className="chips">
            <span className="chip">{result.meta.genre_name}</span>
            <span className="chip">Key of {result.meta.key}</span>
            <span className="chip">{result.meta.bpm} BPM</span>
            {result.meta.vocals && <span className="chip">Real vocals</span>}
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
