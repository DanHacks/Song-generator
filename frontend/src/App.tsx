import { useState } from "react";
import Recorder from "./components/Recorder";
import LyricsForm from "./components/LyricsForm";
import PromptForm from "./components/PromptForm";
import TrackList from "./components/TrackList";
import Pricing from "./components/Pricing";
import Auth from "./components/Auth";

type Tab = "prompt" | "lyrics" | "record" | "library" | "plans";

export default function App() {
  const [tab, setTab] = useState<Tab>("prompt");
  const [toast, setToast] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  function notify(msg: string) {
    setToast(msg);
    window.setTimeout(() => setToast(null), 5000);
  }

  function refresh() {
    setRefreshKey((k) => k + 1);
  }

  return (
    <div className="app root-reset">
      <div className="hero">
        <h1>SautiGen</h1>
        <p>
          Generate songs and instrumentals from a prompt, your lyrics, or your own voice.
          <br />
          <span style={{ opacity: 0.8 }}>Building the future of African tech.</span>
        </p>
      </div>

      <Auth onAuthed={refresh} onError={notify} />

      <div className="tabs">
        <button className={"tab-btn" + (tab === "prompt" ? " active" : "")} onClick={() => setTab("prompt")}>
          Prompt
        </button>
        <button className={"tab-btn" + (tab === "lyrics" ? " active" : "")} onClick={() => setTab("lyrics")}>
          Lyrics
        </button>
        <button className={"tab-btn" + (tab === "record" ? " active" : "")} onClick={() => setTab("record")}>
          Record Voice
        </button>
        <button className={"tab-btn" + (tab === "library" ? " active" : "")} onClick={() => setTab("library")}>
          Library
        </button>
        <button className={"tab-btn plans" + (tab === "plans" ? " active" : "")} onClick={() => setTab("plans")}>
          Plans
        </button>
      </div>

      {tab === "prompt" && <PromptForm onGenerated={refresh} onError={notify} />}
      {tab === "lyrics" && <LyricsForm onGenerated={refresh} onError={notify} />}
      {tab === "record" && <Recorder onGenerated={refresh} onError={notify} />}
      {tab === "library" && (
        <div className="panel">
          <h2>Your Library</h2>
          <p className="sub">Everything you've generated, stored on your device's client profile.</p>
          <TrackList refreshKey={refreshKey} onError={notify} />
        </div>
      )}
      {tab === "plans" && <Pricing onError={notify} />}

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
}
