import { useEffect, useState } from "react";
import { deleteTrack, listTracks, audioUrl } from "../api";
import type { TrackMeta } from "../api";

interface Props {
  refreshKey: number;
  onError: (msg: string) => void;
}

export default function TrackList({ refreshKey, onError }: Props) {
  const [tracks, setTracks] = useState<TrackMeta[] | null>(null);

  useEffect(() => {
    listTracks()
      .then(setTracks)
      .catch((err) => onError((err as Error).message));
  }, [refreshKey]);

  async function remove(id: string) {
    try {
      await deleteTrack(id);
      setTracks((t) => (t ? t.filter((x) => x.id !== id) : t));
    } catch (err) {
      onError((err as Error).message);
    }
  }

  if (tracks === null) return <div className="empty">Loading tracks...</div>;
  if (tracks.length === 0)
    return <div className="empty">No tracks yet. Generate your first one above.</div>;

  return (
    <div className="track-grid">
      {tracks.map((t) => (
        <div key={t.id} className="track-card">
          <h4>{(t.prompt || t.recording_analysis?.recording_name || t.genre_name || "Track").slice(0, 60)}</h4>
          <div className="track-meta">
            {t.genre_name} - {t.key} {t.scale} - {t.bpm} BPM -{" "}
            {Math.round(t.duration_s + (t.recording_analysis?.duration_s ?? 0))}s
            <br />
            <span style={{ opacity: 0.7 }}>
              via {t.mode} {t.created_at ? "- " + new Date(t.created_at).toLocaleString() : ""}
            </span>
          </div>
          {t.filename && <audio controls src={audioUrl("/data/" + t.filename)} />}
          <div className="track-actions">
            {t.filename && (
              <a href={audioUrl("/data/" + t.filename)} download>
                <button>Download</button>
              </a>
            )}
            <button className="danger" onClick={() => remove(t.id)}>
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
