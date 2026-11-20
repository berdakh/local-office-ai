import { useCallback, useEffect, useRef, useState, type ChangeEvent } from "react";
import { BookOpen, Search, Trash2, Upload } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type Document, type Job } from "../api/client";
import JobProgress from "../components/JobProgress";
import { useActivity } from "../activity";
import { libraryStarters } from "../data/starters";
import { transcriptDate } from "../workspace";

export default function Library() {
  const { refresh: refreshActivity } = useActivity();
  const [docs, setDocs] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(() => api.documents().then(setDocs).catch((e) => setError(e.message)).finally(() => setLoading(false)), []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await upload(file);
  }

  async function upload(file: File) {
    setUploading(true);
    setError("");
    setNotice("");
    try {
      const document = await api.upload(file);
      setJobId(document.job_id);
      void refreshActivity();
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setUploading(false);
    }
  }

  function onIndexed(job: Job) {
    setJobId(null);
    void refreshActivity();
    if (job.status === "done") setNotice("Document added to the search index.");
    else setError("The file was saved, but indexing failed. Check the embedding model in Settings.");
  }

  async function remove(doc: Document) {
    if (!window.confirm(`Remove “${doc.title}” from the library and search results?`)) return;
    setDeleting(doc.id);
    setError("");
    setNotice("");
    try {
      await api.deleteDocument(doc.id);
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setDeleting(null);
    }
  }

  const kinds = [...new Set(docs.map((doc) => doc.kind))].sort();
  const visible = docs.filter((doc) => (!kind || doc.kind === kind) && doc.title.toLowerCase().includes(query.toLowerCase().trim()));

  return (
    <div className="page">
      <header className="page-heading studio-heading">
        <div><h1>Document Library</h1><p>Manage the documents and saved transcripts available to Ask the Office.</p></div>
        <input type="file" className="visually-hidden" aria-label="Document file" tabIndex={-1} accept=".pdf,.docx,.md,.txt" ref={fileInput} disabled={uploading || Boolean(jobId)} onChange={onFile} />
        <button className="primary" disabled={uploading || Boolean(jobId)} onClick={() => fileInput.current?.click()}><Upload size={17} />{uploading ? "Uploading…" : "Add document"}</button>
      </header>
      <section className="card workspace-panel">
        <details className="starter-details">
          <summary>Try sample documents</summary>
          <p className="muted small">Add a fictional example, then try a question in <Link to="/ask?mode=office">Office documents</Link>.</p>
          <div className="row">{libraryStarters.map((sample) => {
            const added = docs.some((doc) => doc.title.toLowerCase().replace(/_/g, " ") === sample.title.toLowerCase());
            return <button key={sample.filename} disabled={uploading || !!jobId || loading || added}
              onClick={() => void upload(new File([sample.text], sample.filename, { type: "text/markdown" }))}>
              {added ? `${sample.title} added` : `Add ${sample.title.toLowerCase()}`}
            </button>;
          })}</div>
        </details>
        <div className="library-controls">
          <label>Search files<span className="search-input"><Search size={16} aria-hidden="true" /><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by title…" /></span></label>
          <label>File type<select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All file types</option>
            {kinds.map((option) => <option key={option} value={option}>{option === "transcript" ? "Transcript" : option.toUpperCase()}</option>)}
          </select></label>
        </div>
        {jobId && <JobProgress jobId={jobId} label="Indexing document" onDone={onIndexed} />}
        {notice && <p className="success-text" role="status">{notice}</p>}
        {error && <p className="error" role="alert">{error}</p>}
        {loading && <p className="muted small">Loading documents…</p>}
        {!loading && !visible.length && <div className="library-empty"><BookOpen size={25} /><h2>{docs.length ? "No matching files" : "Your library is empty"}</h2><p className="muted">{docs.length ? "Try a different search or file type." : "Add a PDF, Word, Markdown, or plain text document."}</p></div>}
        {!!visible.length && <div className="table-scroll"><table>
          <thead><tr><th>Title</th><th>Type</th><th>Added</th><th><span className="visually-hidden">Actions</span></th></tr></thead>
          <tbody>
            {visible.map((doc) => (
              <tr key={doc.id}>
                <td>{doc.kind === "transcript" ? <Link to={`/sermon?transcript=${doc.id}`}>{doc.title}</Link> : doc.title}</td>
                <td><span className="badge">{doc.kind === "transcript" ? "Transcript" : doc.kind.toUpperCase()}</span></td>
                <td>{transcriptDate(doc.created_at)}</td>
                <td><button className="icon-button" aria-label={`Remove ${doc.title}`} title="Remove from search" disabled={deleting !== null} onClick={() => void remove(doc)}><Trash2 size={16} /></button></td>
              </tr>
            ))}
          </tbody>
        </table></div>}
      </section>
    </div>
  );
}
