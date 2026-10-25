import { useEffect, useState } from "react";
import { api, type Job, type RunResult, type ScriptureCheck, type TranscriptSummary } from "../api/client";
import JobProgress from "../components/JobProgress";
import Outputs from "../components/Outputs";
import ScripturePanel from "../components/ScripturePanel";

export default function SermonStudio() {
  const [transcript, setTranscript] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [refs, setRefs] = useState<ScriptureCheck[]>([]);
  const [past, setPast] = useState<TranscriptSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);

  const loadPast = () => api.transcripts().then(setPast).catch(() => undefined);
  useEffect(() => { loadPast(); }, []);

  async function onAudio(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setResult(null);
    try {
      const r = await api.transcribe(file);
      setJobId(r.job_id);
    } catch (err) {
      setError(String(err));
    }
  }

  function onTranscribed(job: Job) {
    setJobId(null);
    if (job.status !== "done" || !job.result) return;
    setTranscript(String(job.result.text ?? ""));
    setRefs((job.result.scripture as ScriptureCheck[]) ?? []);
    loadPast();
  }

  async function pickPast(id: number) {
    const t = await api.transcript(id);
    setTranscript(t.text);
    setRefs(((t.meta.scripture as ScriptureCheck[]) ?? []));
  }

  async function checkRefs() {
    try {
      setRefs((await api.checkScripture(transcript)).refs);
    } catch (err) {
      setError(String(err));
    }
  }

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.runWorkflow("sermon_studio", { transcript });
      setResult(r);
      if (r.scripture?.refs) setRefs(r.scripture.refs);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <h2>Sermon Studio</h2>
      <p className="muted">Drop in Sunday's recording, or paste a transcript. Everything runs on this computer.</p>

      <div className="two-col">
        <label>
          Recording (mp3, m4a, wav, mp4)
          <input type="file" accept=".mp3,.m4a,.wav,.mp4,.ogg,.flac,.aac,.webm" onChange={onAudio} disabled={!!jobId} />
        </label>
        <label>
          Or a past transcript
          <select defaultValue="" onChange={(e) => e.target.value && pickPast(Number(e.target.value))}>
            <option value="">Choose...</option>
            {past.map((p) => <option key={p.id} value={p.id}>{p.title} ({p.created_at.slice(0, 10)})</option>)}
          </select>
        </label>
      </div>
      {jobId && <JobProgress jobId={jobId} label="Transcribing" onDone={onTranscribed} />}

      <label>
        Transcript
        <textarea rows={12} value={transcript} onChange={(e) => setTranscript(e.target.value)} placeholder="Transcript appears here after transcription, or paste one." />
      </label>
      <div className="row">
        <button className="primary" disabled={busy || !transcript.trim()} onClick={generate}>
          {busy ? "Working..." : "Generate"}
        </button>
        <button disabled={!transcript.trim()} onClick={checkRefs}>Check scripture references</button>
      </div>
      {error && <p className="error">{error}</p>}
      <ScripturePanel refs={refs} />
      <Outputs result={result} />
    </div>
  );
}
