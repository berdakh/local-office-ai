import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { AudioLines, BookOpenCheck, ChevronDown, ChevronRight, ListChecks, Mic, Sparkles, Upload } from "lucide-react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { isActive, useActivity, useBackgroundDraft, useJobLink } from "../activity";
import { api, type Job, type RunResult, type ScriptureCheck, type Segment, type TranscriptSummary } from "../api/client";
import JobProgress from "../components/JobProgress";
import Microphone from "../components/Microphone";
import Outputs from "../components/Outputs";
import RecordingPlayer from "../components/RecordingPlayer";
import ScripturePanel from "../components/ScripturePanel";
import sampleRecording from "../assets/sample-sermon.mp3";
import { sermonStarter } from "../data/starters";
import { transcriptDate, useWorkspace } from "../workspace";

const sources = [
  { id: "recording", text: "Recording" },
  { id: "microphone", text: "Microphone" },
  { id: "paste", text: "Paste text" },
  { id: "saved", text: "Saved transcripts" },
] as const;
const drafts = [
  ["summary", "Sermon summary"],
  ["key_points", "Key points"],
  ["discussion_guide", "Discussion guide"],
  ["blog_post", "Blog post"],
  ["social_posts", "Social posts"],
  ["bulletin_blurb", "Bulletin blurb"],
] as const;
const allDrafts = drafts.map(([id]) => id);
const audioExtensions = ".mp3,.m4a,.wav,.mp4,.ogg,.flac,.aac,.webm,.wma";
type Source = (typeof sources)[number]["id"];
type Draft = (typeof drafts)[number][0];

export default function SermonStudio() {
  const { models, health } = useWorkspace();
  const [params] = useSearchParams();
  const visible = useLocation().pathname === "/sermon";
  const linkedTranscript = visible && !params.has("job") ? Number(params.get("transcript")) : 0;
  const [source, setSource] = useState<Source>(linkedTranscript || params.get("source") === "saved" ? "saved" : "recording");
  const [transcript, setTranscript] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [recordingJob, setRecordingJob] = useState<string | null>(null);
  const [refs, setRefs] = useState<ScriptureCheck[]>([]);
  const [past, setPast] = useState<TranscriptSummary[]>([]);
  const [savedId, setSavedId] = useState<number | null>(null);
  const [audio, setAudio] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [localUrl, setLocalUrl] = useState("");
  const [savedAudioId, setSavedAudioId] = useState<number | null>(null);
  const [timeline, setTimeline] = useState<Segment[]>([]);
  const [micActive, setMicActive] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [loadingSaved, setLoadingSaved] = useState(false);
  const [checking, setChecking] = useState(false);
  const [checked, setChecked] = useState(false);
  const run = useBackgroundDraft("sermon_studio");
  const busy = run.busy;
  const { refresh } = useActivity();
  const [error, setError] = useState("");
  const [result, setResult] = useState<RunResult | null>(null);
  const [model, setModel] = useState("");
  const [selected, setSelected] = useState<Draft[]>(allDrafts);
  const fileInput = useRef<HTMLInputElement>(null);
  const link = useJobLink("/sermon", (job) => {
    if (job.kind !== "transcribe" && job.kind !== "workflow") {
      throw new Error("This link does not point to sermon work.");
    }
    setError("");
    setJobId(null);
    run.resume(null);
    setFile(null);
    setAudio("");
    setTimeline([]);
    setRecordingJob(null);
    setSavedAudioId(null);
    setSavedId(null);
    setRefs([]);
    setChecked(false);
    setResult(null);
    if (job.kind === "transcribe") {
      setSource("recording");
      setTranscript("");
      setAudio(job.context?.name ?? String(job.result?.title ?? ""));
      if (job.context?.recording) setRecordingJob(job.id);
      if (isActive(job)) setJobId(job.id);
      else onTranscribed(job);
    } else {
      const context = job.context;
      const value = context?.inputs?.transcript;
      setSource("paste");
      setTranscript(typeof value === "string" ? value : "");
      setSavedAudioId(context?.transcript_id ?? null);
      setModel(context?.chat_model ?? "");
      setSelected(context?.selected_outputs?.filter((id): id is Draft => allDrafts.includes(id as Draft)) ?? allDrafts);
      if (isActive(job)) run.resume(job.id);
      else onDrafted(job);
    }
  });
  const hasRecording = uploading || Boolean(jobId);
  const editingLocked = hasRecording || busy || link.loading || loadingSaved || checking || micActive;
  const audioSrc = file ? localUrl
    : recordingJob ? `/api/transcription-jobs/${recordingJob}/audio`
    : savedAudioId ? `/api/transcripts/${savedAudioId}/audio` : "";
  const words = transcript.trim().match(/\S+/g)?.length ?? 0;
  const showEditor = source === "paste" || Boolean(transcript);
  const generationModel = model || health?.chat_model;
  const unavailableModel = Boolean(health && (!generationModel || !models.includes(generationModel)));

  const loadPast = useCallback(() => api.transcripts().then(setPast).catch(() => undefined), []);
  useEffect(() => { void loadPast(); }, [loadPast]);
  useEffect(() => { if (!visible) setMicActive(false); }, [visible]);
  useEffect(() => {
    if (!file) { setLocalUrl(""); return; }
    const url = URL.createObjectURL(file);
    setLocalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    if (!savedAudioId) return;
    let cancelled = false;
    void api.transcript(savedAudioId).then((saved) => {
      if (!cancelled) setTimeline(saved.timeline);
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [savedAudioId]);

  const pickPast = useCallback(async (id: number) => {
    setLoadingSaved(true);
    setError("");
    try {
      const saved = await api.transcript(id);
      setSavedId(id);
      setTranscript(saved.text);
      setFile(null);
      setRecordingJob(null);
      setAudio("");
      setTimeline(saved.timeline);
      setSavedAudioId(saved.audio_available ? id : null);
      setRefs((saved.meta.scripture as ScriptureCheck[]) ?? []);
      setChecked(false);
      setResult(null);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoadingSaved(false);
    }
  }, []);

  useEffect(() => {
    if (linkedTranscript > 0) void pickPast(linkedTranscript);
  }, [linkedTranscript, pickPast]);

  async function uploadAudio(file: File, fromMicrophone = false) {
    if (editingLocked && !fromMicrophone) return;
    setError("");
    setUploading(true);
    setAudio(file.name);
    const startedAt = window.location.pathname + window.location.search;
    try {
      const response = await api.transcribe(file);
      setFile(file);
      setRecordingJob(null);
      setTimeline([]);
      setSavedAudioId(null);
      setJobId(response.job_id);
      link.remember(response.job_id, startedAt);
      void refresh();
    } catch (err) {
      setError((err as Error).message);
      setAudio("");
    } finally {
      setUploading(false);
    }
  }

  function trySample(asAudio: boolean) {
    if (editingLocked || (transcript.trim() && transcript !== sermonStarter &&
        !window.confirm("Replace the current transcript with the sample?"))) return;
    if (asAudio) {
      setSource("recording");
      setUploading(true);
      setError("");
      void fetch(sampleRecording).then(async (response) => {
        if (!response.ok) throw new Error("The sample recording could not be loaded.");
        await uploadAudio(new File([await response.blob()], "Sample sermon - Loving Our Neighbors.mp3", { type: "audio/mpeg" }));
      }).catch((err) => { setError(err.message); setUploading(false); });
      return;
    }
    setSource("paste");
    setTranscript(sermonStarter);
    setRecordingJob(null);
    setFile(null);
    setTimeline([]);
    setSavedAudioId(null);
    setSavedId(null);
    setAudio("");
    setRefs([]);
    setChecked(false);
    setResult(null);
    setError("");
  }

  function onAudio(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (file) void uploadAudio(file);
    event.target.value = "";
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files.length > 1) {
      setError("Choose one recording at a time.");
      return;
    }
    const file = event.dataTransfer.files[0];
    if (file) void uploadAudio(file);
  }

  function onTranscribed(job: Job) {
    setJobId(null);
    void refresh();
    if (job.status === "error") {
      setError(job.error?.split("\n")[0] ?? "Transcription failed.");
      return;
    }
    if (!job.result) return;
    setTranscript(String(job.result.text ?? ""));
    setRefs((job.result.scripture as ScriptureCheck[]) ?? []);
    setChecked(false);
    setResult(null);
    setSavedId(null);
    const id = Number(job.result.document_id);
    setSavedAudioId(id && job.result.audio_available ? id : null);
    void loadPast();
  }

  async function checkRefs() {
    setChecking(true);
    setChecked(false);
    setError("");
    try {
      setRefs((await api.checkScripture(transcript)).refs);
      setChecked(true);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setChecking(false);
    }
  }

  async function generate() {
    setError("");
    try {
      const startedAt = window.location.pathname + window.location.search;
      const id = await run.start({ transcript }, {
        chat_model: model || undefined, selected_outputs: selected,
        resume: { transcript_id: savedAudioId ?? undefined },
      });
      link.remember(id, startedAt);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  function onDrafted(job: Job) {
    try {
      const result = run.finish(job);
      setResult(result);
      if (result.scripture?.refs) setRefs(result.scripture.refs);
    } catch (err) { setError((err as Error).message); }
  }

  return (
    <div className="page">
      <header className="page-heading studio-heading">
        <div><h1>Sermon Studio</h1><p>Transcribe a recording, verify scripture, and prepare drafts for your church.</p></div>
        <span className="heading-symbol"><AudioLines size={26} strokeWidth={1.7} aria-hidden="true" /></span>
      </header>
      <div className="studio-grid">
        <div className="studio-main">
          <section className="card workspace-panel recording-panel">
            <h2>Recording &amp; transcript</h2>
            <div className="segmented" role="group" aria-label="Transcript source">
              {sources.map(({ id, text }) => (
                <button key={id} aria-pressed={source === id} disabled={editingLocked} onClick={() => setSource(id)}>
                  {text}
                </button>
              ))}
            </div>
            {source === "recording" && (
              <>
                <input className="visually-hidden" type="file" aria-label="Recording" tabIndex={-1} accept={audioExtensions} ref={fileInput} onChange={onAudio} disabled={editingLocked} />
                <button type="button" className={`dropzone ${dragging ? "dragging" : ""}`} disabled={editingLocked}
                  onClick={() => fileInput.current?.click()}
                  onDragOver={(event) => { event.preventDefault(); if (!editingLocked) setDragging(true); }}
                  onDragLeave={() => setDragging(false)} onDrop={onDrop}>
                  <span className="upload-icon"><Upload size={20} aria-hidden="true" /></span>
                  <strong>{uploading ? "Uploading recording…" : jobId ? "Transcribing recording…" : "Drop a recording here or browse files"}</strong>
                  <small>MP3, M4A, WAV, MP4, and other common audio formats</small>
                </button>
                {audio && <p className="file-label"><Mic size={15} aria-hidden="true" />{audio}</p>}
              </>
            )}
            {source === "microphone" && visible && <Microphone disabled={editingLocked} onActive={setMicActive} onRecording={(capture) => void uploadAudio(capture, true)} />}
            {source === "saved" && (
              <label className="field">
                Saved transcript
                <select value={savedId ?? ""} onChange={(e) => { if (e.target.value) void pickPast(Number(e.target.value)); }} disabled={editingLocked || !past.length}>
                  <option value="">{past.length ? "Choose a recording" : "No saved recordings"}</option>
                  {past.map((item) => <option key={item.id} value={item.id}>{item.title} · {transcriptDate(item.created_at)} · #{item.id}</option>)}
                </select>
              </label>
            )}
            {jobId && <JobProgress jobId={jobId} label="Transcribing" onDone={onTranscribed} />}
            {audioSrc && <RecordingPlayer key={audioSrc} src={audioSrc} track={timeline} />}
            {!micActive && <details className="starter-details">
              <summary>Try a sample sermon</summary>
              <div className="row">
                <button disabled={editingLocked} onClick={() => trySample(true)}>Transcribe sample MP3</button>
                <button disabled={editingLocked} onClick={() => trySample(false)}>Use sample transcript</button>
              </div>
            </details>}
            {showEditor && <>
            <div className="editor-header"><label htmlFor="sermon-transcript">Transcript</label>{!!words && <span>{words.toLocaleString()} {words === 1 ? "word" : "words"}</span>}</div>
            <textarea id="sermon-transcript" rows={11} value={transcript} disabled={editingLocked} onChange={(e) => {
              setTranscript(e.target.value);
              setRefs([]);
              setChecked(false);
            }} placeholder={source === "paste" ? "Paste your sermon transcript here…" : "Your transcript will appear here. You can also paste or edit text."} />
            <div className="row">
              <button disabled={editingLocked || !words} onClick={() => void checkRefs()}><BookOpenCheck size={17} />{checking ? "Checking references…" : "Check scripture"}</button>
              {checked && !refs.length && <span className="muted small" role="status">No scripture references found.</span>}
            </div>
            </>}
            {(link.error || error) && <p className="error" role="alert">{link.error || error}</p>}
          </section>
          <ScripturePanel refs={refs} />
        </div>
        <aside className="card workspace-panel draft-options">
          <div className="panel-heading">
            <span className="tool-icon mint"><ListChecks size={21} aria-hidden="true" /></span>
            <div><h2>Drafts</h2><p>{words ? `${selected.length} of ${drafts.length} selected` : "Add a transcript to begin."}</p></div>
          </div>
          <details className="draft-customize">
          <summary><span>Customize drafts</span><ChevronDown size={17} aria-hidden="true" /></summary>
          <label className="field">Drafting model
            <select aria-label="Drafting model" value={model} onChange={(e) => setModel(e.target.value)} disabled={busy || !models.length}>
              <option value="">{health?.chat_model ? `Default · ${health.chat_model}` : "Use workspace default"}</option>
              {models.filter((name) => name !== health?.chat_model || name === model).map((name) => <option key={name} value={name}>{name}</option>)}
            </select>
          </label>
          <fieldset className="draft-picker" disabled={busy}>
            <legend>Drafts</legend>
            <button type="button" className="text-button" onClick={() => setSelected(selected.length === drafts.length ? [] : allDrafts)}>
              {selected.length === drafts.length ? "Clear all" : "Select all"}
            </button>
            {drafts.map(([id, title]) => (
              <label key={id}><input type="checkbox" checked={selected.includes(id)} onChange={(e) =>
                setSelected(e.target.checked ? [...selected, id] : selected.filter((item) => item !== id))} />{title}</label>
            ))}
          </fieldset>
          </details>
          {unavailableModel && <p className="small muted">Choose an available model or <Link to="/settings">open model settings</Link>.</p>}
          <button className="primary generate-button" disabled={editingLocked || !words || !selected.length || unavailableModel} onClick={() => void generate()}>
            <Sparkles size={18} />{busy ? "Generating…" : !words || !selected.length ? "Generate drafts" : `Generate ${selected.length} ${selected.length === 1 ? "draft" : "drafts"}`}<ChevronRight size={17} className="generate-arrow" />
          </button>
          {run.jobId && <JobProgress jobId={run.jobId} label="Generating sermon drafts" onDone={onDrafted} />}
          {busy && <p className="small muted">Writing with {generationModel ?? "your local model"}. You can leave this page and return.</p>}
        </aside>
      </div>
      <Outputs workflowId="sermon_studio" result={result} />
    </div>
  );
}
