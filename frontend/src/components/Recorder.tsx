import { useEffect, useRef, useState } from "react";
import { generateRecording } from "../api";

interface Props {
  onGenerated: () => void;
  onError: (msg: string) => void;
}

export default function Recorder({ onGenerated, onError }: Props) {
  const [recording, setRecording] = useState(false);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [result, setResult] = useState<any>(null);
  const [genre, setGenre] = useState("afrobeats");

  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      if (timerRef.current) window.clearInterval(timerRef.current);
    };
  }, []);

  async function start() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const rec = new MediaRecorder(stream);
      mediaRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setAudioBlob(blob);
      };
      rec.start();
      setRecording(true);
      setElapsed(0);
      timerRef.current = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    } catch (err) {
      onError("Microphone access denied. Check browser permissions.");
    }
  }

  function stop() {
    mediaRef.current?.stop();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    if (timerRef.current) window.clearInterval(timerRef.current);
    setRecording(false);
  }

  async function upload() {
    if (!audioBlob) return;
    setLoading(true);
    try {
      const file = new File([audioBlob], "recording.webm", { type: audioBlob.type });
      const res = await generateRecording(file, genre);
      setResult(res);
      setAudioBlob(null);
      onGenerated();
    } catch (err) {
      onError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const mmss = `${String(Math.floor(elapsed / 60)).padStart(2, "0")}:${String(elapsed % 60).padStart(2, "0")}`;

  return (
    <div className="panel">
      <h2>Record your voice</h2>
      <p className="sub">
        Sing, hum or tap a beat. We detect your tempo and key, then build a backing track around it.
      </p>

      <label className="field-label">Genre for the backing track</label>
      <select value={genre} onChange={(e) => setGenre(e.target.value)}>
        <option value="afrobeats">Afrobeats</option>
        <option value="gospel">Gospel</option>
        <option value="hiphop">Hip Hop</option>
        <option value="amapiano">Amapiano</option>
        <option value="ballad">Ballad</option>
        <option value="edm">EDM</option>
        <option value="dancehall">Dancehall</option>
      </select>

      <div className="recorder-row" style={{ marginTop: 16 }}>
        {!recording ? (
          <button className="rec-btn" onClick={start} disabled={loading}>
            Start Recording
          </button>
        ) : (
          <button className="rec-btn recording" onClick={stop}>
            Stop
          </button>
        )}
        {recording && <span className="timer">{mmss}</span>}
        {audioBlob && !recording && (
          <button className="rec-btn" onClick={upload} disabled={loading}>
            {loading ? (
              <>
                <span className="spinner" /> Generating...
              </>
            ) : (
              "Generate Backing Track"
            )}
          </button>
        )}
      </div>

      <div className="visualizer">{recording ? "Recording... speak or sing" : "Ready"}</div>

      {audioBlob && !recording && (
        <audio controls src={URL.createObjectURL(audioBlob)} style={{ marginTop: 8 }} />
      )}

      {result && (
        <div className="result">
          <h3>Backing track generated</h3>
          <p style={{ color: "#94a3b8", margin: 0 }}>
            Detected {result.meta.recording_analysis?.bpm} BPM, key of {result.meta.recording_analysis?.key}{" "}
            {result.meta.recording_analysis?.mode}
          </p>
          <audio controls src={result.audio_url} />
        </div>
      )}
    </div>
  );
}
