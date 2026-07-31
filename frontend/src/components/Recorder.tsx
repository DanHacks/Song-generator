import { useEffect, useRef, useState } from "react";
import { generateRecording } from "../api";

interface Props {
  onGenerated: () => void;
  onError: (msg: string) => void;
}

async function toWav(blob: Blob): Promise<File> {
  const arrayBuffer = await blob.arrayBuffer();
  const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
  const decoded = await audioContext.decodeAudioData(arrayBuffer);
  const offline = new OfflineAudioContext(1, decoded.length, 44100);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start(0);
  const rendered = await offline.startRendering();
  const samples = rendered.getChannelData(0);
  const pcm = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  const buffer = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 44100, true);
  view.setUint32(28, 44100 * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  new Int16Array(buffer, 44).set(pcm);
  return new File([buffer], "recording.wav", { type: "audio/wav" });
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
      const wav = await toWav(audioBlob);
      const res = await generateRecording(wav, genre);
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
