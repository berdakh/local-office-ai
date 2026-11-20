import { useCallback, useEffect, useState } from "react";
import { Cpu, Download, RefreshCw } from "lucide-react";
import { api, type Hardware, type Job } from "../api/client";
import { useActivity } from "../activity";
import { useWorkspace } from "../workspace";
import JobProgress from "./JobProgress";

export default function HardwarePanel() {
  const { refresh: refreshActivity } = useActivity();
  const { refresh, health } = useWorkspace();
  const [machine, setMachine] = useState<Hardware | null>(null);
  const [job, setJob] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const scan = useCallback(async () => {
    setError("");
    try { setMachine(await api.hardware()); }
    catch (err) { setError((err as Error).message); }
  }, []);
  useEffect(() => { void scan(); }, [scan]);

  async function select(model: string, installed: boolean) {
    setBusy(model); setError(""); setFeedback("");
    try {
      if (installed) {
        await api.saveModel(model);
        await refresh();
        setFeedback(`Default model set to ${model}.`);
      } else {
        const result = await api.downloadModel(model);
        if (result.job_id) { setJob(result.job_id); void refreshActivity(); }
        else await scan();
      }
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(""); }
  }

  function onDownloaded(next: Job) {
    setJob(null);
    void refreshActivity();
    if (next.status === "done") {
      setFeedback(`${next.result?.model} is installed. Choose Use model to make it your default.`);
      void scan(); void refresh();
    } else setError(next.error?.split("\n")[0] ?? "The download failed.");
  }

  return (
    <section className="card workspace-panel diagnostics hardware-panel">
      <div className="section-heading"><div className="panel-heading"><span className="tool-icon blue"><Cpu size={20} /></span>
        <div><h2>Hardware &amp; model downloads</h2><p>Find models sized for this computer.</p></div></div>
        <button className="icon-button" aria-label="Scan hardware again" onClick={() => void scan()}><RefreshCw size={16} /></button>
      </div>
      {!machine && !error && <p className="small muted">Checking this computer…</p>}
      {machine && <>
        <dl><div><dt>Processor</dt><dd>{machine.cpu} · {machine.threads ?? "?"} threads</dd></div>
          <div><dt>Memory</dt><dd>{machine.ram_gib === null ? "Unknown" : `${machine.ram_gib} GiB RAM`}</dd></div>
          <div><dt>Graphics detected</dt><dd>{machine.gpus.map((gpu) => gpu.name + (gpu.vram_gib ? ` · ${gpu.vram_gib} GiB` : "")).join(", ") || "None reported"}</dd></div>
          <div><dt>Free space on the app drive</dt><dd>{machine.free_gb} GB</dd></div></dl>
        <p className="small muted">{machine.running.length ? machine.running.map((item) => `${item.name} · ${!item.size_vram ? "CPU" : item.size_vram >= item.size ? "GPU" : "CPU + GPU"}`).join(" | ") :
          "Ollama chooses CPU or GPU when it loads a model. GPU use depends on drivers and available memory."}</p>
        <div className="model-list">{machine.models.map((entry) => <div key={entry.tag}>
          <span><strong>{entry.label}{machine.recommended === entry.tag ? " · Recommended" : ""}</strong><small>{entry.tag} · {entry.download_gb} GB · {entry.gpu_candidate ? "GPU candidate" : "CPU compatible"}</small></span>
          <button disabled={!!busy || !!job || health?.chat_model === entry.tag} onClick={() => void select(entry.tag, entry.installed)}>
            {!entry.installed && <Download size={15} />}{health?.chat_model === entry.tag ? "In use" : entry.installed ? "Use model" : busy === entry.tag ? "Starting…" : "Download"}
          </button>
        </div>)}</div>
        {!machine.models.length && <p className="small muted">No model recommendation for this reported memory.</p>}
        {machine.models.some((entry) => !entry.installed) && <p className="small muted">Downloads use the internet once. Installed models run locally.</p>}
      </>}
      {job && <JobProgress jobId={job} label="Downloading model" onDone={onDownloaded} />}
      {feedback && <p className="success-text" role="status">{feedback}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
