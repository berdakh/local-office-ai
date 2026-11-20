import { useState, type FormEvent } from "react";
import { Check, ChevronRight, Code2, Cpu, Folder, Palette, RefreshCw, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import HardwarePanel from "../components/HardwarePanel";
import { defaultAppearance, useWorkspace, type Appearance } from "../workspace";

const accents: { id: Appearance["accent"]; label: string; color: string }[] = [
  { id: "forest", label: "Forest", color: "#28604c" },
  { id: "blue", label: "Atlantic", color: "#3258a2" },
  { id: "plum", label: "Plum", color: "#77507e" },
];

export default function Settings() {
  const { appearance, setAppearance, health, models, refresh, modelError } = useWorkspace();
  const [selectedModel, setSelectedModel] = useState<string | null>(null);
  const [workspaceName, setWorkspaceName] = useState(appearance.workspaceName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const currentModel = selectedModel ?? health?.chat_model ?? "";

  async function saveModel(model: string | null) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api.saveModel(model);
      setSelectedModel(null);
      await refresh();
      setNotice(`Default model set to ${result.chat_model}.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function saveName(event: FormEvent) {
    event.preventDefault();
    const name = workspaceName.trim() || defaultAppearance.workspaceName;
    setWorkspaceName(name);
    setAppearance({ ...appearance, workspaceName: name });
  }

  return (
    <div className="page">
      <header className="page-heading">
        <h1>Settings</h1>
        <p>Choose a local drafting model and make the workspace your own.</p>
      </header>
      <div className="settings-grid">
        <section className="card workspace-panel">
          <div className="panel-heading">
            <span className="tool-icon mint"><Cpu size={20} aria-hidden="true" /></span>
            <div><h2>Models</h2><p>Models installed on this computer.</p></div>
          </div>
          <label className="field">
            Default drafting model
            <select value={currentModel} onChange={(e) => { setSelectedModel(e.target.value); setNotice(""); setError(""); }} disabled={busy || !models.length}>
              {!currentModel && <option value="">Choose a model</option>}
              {currentModel && !models.includes(currentModel) && <option value={currentModel}>{currentModel} · unavailable</option>}
              {models.map((model) => <option key={model} value={model}>{model}</option>)}
            </select>
            <span className="help">Used for sermons, letters, announcements, and document answers.</span>
          </label>
          <div className="row">
            <button className="primary" disabled={busy || !models.includes(currentModel) || currentModel === health?.chat_model} onClick={() => void saveModel(currentModel)}>{busy ? "Saving…" : "Save model"}</button>
            <button disabled={busy || !health} onClick={() => void saveModel(null)}>Use install default</button>
            <button className="icon-button" title="Refresh installed models" aria-label="Refresh installed models" disabled={busy} onClick={() => void refresh()}><RefreshCw size={17} /></button>
          </div>
          {!models.length && health && <p className="small muted">{health.ollama.available ? "No drafting models are installed in Ollama." : "Start Ollama, then refresh the model list."}</p>}
          {(error || modelError) && <p className="error" role="alert">{error || modelError}</p>}
          {notice && <p className="success-text" role="status"><Check size={16} />{notice}</p>}
        </section>
        <section className="card workspace-panel">
          <div className="panel-heading">
            <span className="tool-icon lavender"><Palette size={20} aria-hidden="true" /></span>
            <div><h2>Appearance</h2><p>Saved in this browser.</p></div>
          </div>
          <form onSubmit={saveName}>
            <label className="field field-caption" htmlFor="workspace-name">Workspace name</label>
            <div className="inline-input"><input id="workspace-name" value={workspaceName} maxLength={48} onChange={(e) => setWorkspaceName(e.target.value)} /><button disabled={workspaceName.trim() === appearance.workspaceName}>Save name</button></div>
          </form>
          <div className="two-col">
            <label className="field">Theme
              <select aria-label="Theme" value={appearance.theme} onChange={(e) => setAppearance({ ...appearance, theme: e.target.value as Appearance["theme"] })}>
                <option value="light">Light</option><option value="dark">Dark</option><option value="system">Match system</option>
              </select>
            </label>
            <label className="field">Layout density
              <select aria-label="Layout density" value={appearance.density} onChange={(e) => setAppearance({ ...appearance, density: e.target.value as Appearance["density"] })}>
                <option value="comfortable">Comfortable</option><option value="compact">Compact</option>
              </select>
            </label>
          </div>
          <fieldset className="accent-picker">
            <legend>Accent color</legend>
            {accents.map(({ id, label, color }) => (
              <button key={id} aria-pressed={appearance.accent === id} onClick={() => setAppearance({ ...appearance, accent: id })}>
                <span style={{ backgroundColor: color }} />{label}
              </button>
            ))}
          </fieldset>
        </section>
      </div>
      <HardwarePanel />
      {health && (
        <section className="card workspace-panel diagnostics">
          <div className="panel-heading"><span className="tool-icon blue"><ShieldCheck size={20} aria-hidden="true" /></span><div><h2>Local system</h2><p>Readiness and storage for this installation.</p></div></div>
          <dl>
            <div><dt>Ollama</dt><dd>{health.ollama.available ? "Connected" : "Unavailable"} · {health.ollama.url}</dd></div>
            <div><dt>Transcription</dt><dd>{health.transcription_available ? "Ready" : "Unavailable"} · {health.whisper_model}</dd></div>
            <div><dt>Document search</dt><dd>{health.embed_model_installed ? "Ready" : "Embedding model unavailable"} · {health.embed_model}</dd></div>
            <div><dt>Scripture and letterhead</dt><dd>{health.bible_installed ? "Bible installed" : "Bible unavailable"} · {health.letterhead_installed ? "Letterhead installed" : "Letterhead unavailable"}</dd></div>
          </dl>
          <div className="storage-path"><Folder size={17} aria-hidden="true" /><span>Data folder</span><code>{health.data_dir}</code></div>
        </section>
      )}
      <Link className="card system-card" to="/settings/workbench"><span className="tool-icon lavender"><Code2 size={19} /></span>
        <span><strong>Advanced workbench</strong><small>Python experiments and local diagnostics</small></span><ChevronRight size={17} /></Link>
    </div>
  );
}
