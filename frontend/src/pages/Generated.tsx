import { useCallback, useEffect, useState } from "react";
import { Copy, Database, Download, RefreshCw, Search, X } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api, type GeneratedRow, type GeneratedText, type GeneratedStatus } from "../api/client";
import { useActivity } from "../activity";
import { transcriptDate } from "../workspace";

const workflowNames: Record<string, string> = {
  sermon_studio: "Sermon Studio", announcements: "Announcements", letter: "Correspondence",
  ask: "Office documents", general: "General chat", bible: "Bible & Christianity",
};
const names = (workflow: string) => workflowNames[workflow] ?? workflow.replace(/_/g, " ");

export default function Generated() {
  const { jobs } = useActivity();
  const completed = jobs.filter((job) => job.status === "done" && ["workflow", "chat"].includes(job.kind))
    .map((job) => job.id).sort().join(",");
  const [params, setParams] = useSearchParams();
  const jobId = params.get("job");
  const requestedRun = params.get("run");
  const [runId, setRunId] = useState("");
  const [query, setQuery] = useState("");
  const [workflow, setWorkflow] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("newest");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<{ items: GeneratedRow[]; total: number }>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<GeneratedText | null>(null);
  const [editing, setEditing] = useState<GeneratedText | null>(null);
  const [tagText, setTagText] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [loadKey, setLoadKey] = useState(0);
  const dirty = !!open && !!editing && (JSON.stringify(open) !== JSON.stringify(editing) || open.tags.join(", ") !== tagText);

  useEffect(() => {
    let ignore = false;
    setRunId(requestedRun ?? "");
    setOffset(0);
    if (jobId) api.job(jobId).then((job) => {
      if (!ignore && typeof job.result?.run_id === "string") setRunId(job.result.run_id);
    }).catch((err) => { if (!ignore) setError(err.message); });
    return () => { ignore = true; };
  }, [jobId, requestedRun]);

  useEffect(() => {
    let ignore = false;
    setLoading(true);
    setError("");
    const timer = window.setTimeout(() => {
      const options = new URLSearchParams({ q: query, workflow, sort, offset: String(offset), run_id: runId });
      if (status) options.set("status", status);
      api.generated(options).then((result) => { if (!ignore) setData(result); })
        .catch((err) => { if (!ignore) setError(err.message); })
        .finally(() => { if (!ignore) setLoading(false); });
    }, 170);
    return () => { ignore = true; window.clearTimeout(timer); };
  }, [query, workflow, status, sort, runId, offset, loadKey, completed]);

  const refresh = useCallback(() => setLoadKey((key) => key + 1), []);

  async function select(id: number) {
    if (dirty && !window.confirm("Leave this text without saving your edits?")) return;
    setError("");
    setNote("");
    try {
      const item = await api.generatedText(id);
      setOpen(item);
      setEditing(item);
      setTagText(item.tags.join(", "));
    } catch (err) { setError((err as Error).message); }
  }

  async function save() {
    if (!editing) return;
    setSaving(true);
    setError("");
    try {
      const saved = await api.updateGenerated(editing.id, {
        title: editing.title, body: editing.body, status: editing.status, tags: tagText.split(","),
      });
      setOpen(saved); setEditing(saved); setTagText(saved.tags.join(", "));
      setNote("Changes saved.");
      refresh();
    } catch (err) { setError((err as Error).message); }
    finally { setSaving(false); }
  }

  function exportText() {
    if (!editing) return;
    const url = URL.createObjectURL(new Blob([editing.body], { type: "text/markdown;charset=utf-8" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = (editing.title.trim().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "") || "generated-text") + ".md";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return (
    <div className="page">
      <header className="page-heading studio-heading">
        <div><h1>Generated Texts</h1><p>Drafts and answers are saved here automatically when they finish.</p></div>
        <button className="icon-button" aria-label="Refresh Generated Texts" onClick={refresh}><RefreshCw size={17} /></button>
      </header>
      <section className="card workspace-panel">
        {runId && <div className="row generated-run-filter"><span className="badge verified">Selected generation run</span><button onClick={() => setParams({})}>Show all texts</button></div>}
        <div className="generated-filters">
          <label>Search texts<span className="search-input"><Search size={16} aria-hidden="true" />
            <input aria-label="Search generated texts" value={query} maxLength={250} placeholder="Search titles, text, or tags…" onChange={(e) => { setQuery(e.target.value); setOffset(0); }} />
          </span></label>
          <label>Workflow<select aria-label="Workflow" value={workflow} onChange={(e) => { setWorkflow(e.target.value); setOffset(0); }}>
            <option value="">All workflows</option>{Object.entries(workflowNames).map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select></label>
          <label>Status<select aria-label="Filter by status" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
            <option value="">All statuses</option><option value="draft">Draft</option><option value="reviewed">Reviewed</option>
          </select></label>
          <label>Sort<select aria-label="Sort generated texts" value={sort} onChange={(e) => { setSort(e.target.value); setOffset(0); }}>
            <option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="title">Title</option>
          </select></label>
        </div>
        {error && <p className="error" role="alert">{error}</p>}
        {loading && !data.items.length && <p className="small muted" role="status">Loading generated texts…</p>}
        {!loading && !data.items.length && <div className="library-empty"><Database size={25} /><h2>No matching texts</h2><p className="muted">Generate a draft or ask a question to add your first text.</p></div>}
        {!!data.items.length && <div className="table-scroll generated-table">
          <table><thead><tr><th>Title</th><th>Workflow</th><th>Status</th><th>Generated</th><th>Model</th></tr></thead>
          <tbody>{data.items.map((item) => <tr key={item.id}>
            <td><button className="text-button" onClick={() => void select(item.id)}>{item.title}</button>
              <span className="small muted">{item.tags.length ? item.tags.join(" · ") : item.preview}</span></td>
            <td>{names(item.workflow)}</td>
            <td><span className={`badge ${item.status === "reviewed" ? "verified" : ""}`}>{item.status === "reviewed" ? "Reviewed" : "Draft"}</span></td>
            <td><time dateTime={item.created_at}>{transcriptDate(item.created_at)}</time></td>
            <td><code>{item.model}</code></td>
          </tr>)}</tbody></table>
          <div className="row"><span className="small muted">{offset + 1}–{Math.min(offset + data.items.length, data.total)} of {data.total}</span>
            <button disabled={offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - 40))}>Previous</button>
            <button disabled={offset + 40 >= data.total || loading} onClick={() => setOffset(offset + 40)}>Next</button></div>
        </div>}
      </section>
      {editing && <section className="card workspace-panel generated-editor">
        <div className="section-heading"><h2>Edit generated text</h2><button className="icon-button" aria-label="Close text" onClick={() => {
          if (!dirty || window.confirm("Close this text without saving your edits?")) { setOpen(null); setEditing(null); }
        }}><X size={17} /></button></div>
        <p className="small muted">{names(editing.workflow)} · {editing.model} · Generated {transcriptDate(editing.created_at)} · Updated {transcriptDate(editing.updated_at)}</p>
        {!!editing.sources.length && <p className="small muted">Sources · {editing.sources.join(", ")}</p>}
        <label>Title<input value={editing.title} maxLength={200} onChange={(e) => setEditing({ ...editing, title: e.target.value })} /></label>
        <div className="two-col">
          <label>Review status<select value={editing.status} onChange={(e) => setEditing({ ...editing, status: e.target.value as GeneratedStatus })}>
            <option value="draft">Draft</option><option value="reviewed">Reviewed</option></select></label>
          <label>Tags<input value={tagText} onChange={(e) => setTagText(e.target.value)} placeholder="bulletin, volunteers, Easter" /></label>
        </div>
        <label>Text<textarea aria-label="Generated text" rows={12} value={editing.body} maxLength={100000} onChange={(e) => setEditing({ ...editing, body: e.target.value })} /></label>
        <div className="row">
          <button className="primary" disabled={saving || !dirty || !editing.title.trim() || !editing.body.trim()} onClick={() => void save()}>{saving ? "Saving…" : "Save changes"}</button>
          <button onClick={exportText}><Download size={16} /> Export Markdown</button>
          <button onClick={async () => {
            try { await navigator.clipboard.writeText(editing.body); setNote("Copied."); }
            catch { setNote("The clipboard is unavailable."); }
          }}><Copy size={16} /> Copy text</button>
        </div>
        {note && <p className="small muted" role="status">{note}</p>}
      </section>}
    </div>
  );
}
