import { useState } from "react";
import { type Job, type RunResult } from "../api/client";
import { isActive, useBackgroundDraft, useJobLink } from "../activity";
import JobProgress from "./JobProgress";
import Outputs from "./Outputs";
import StarterPicker from "./StarterPicker";

type Props = {
  workflowId: string;
  title: string;
  description: string;
  inputName: string;
  inputLabel: string;
  placeholder?: string;
  starters?: readonly { title: string; text: string }[];
};

/** One text input in, a set of editable outputs out. Covers most church workflows. */
export default function WorkflowRunner(p: Props) {
  const [value, setValue] = useState("");
  const draft = useBackgroundDraft(p.workflowId);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RunResult | null>(null);

  const link = useJobLink("/announcements", (job) => {
    if (job.kind !== "workflow") throw new Error("This link does not point to an announcement draft.");
    const input = job.context?.inputs?.[p.inputName];
    setValue(typeof input === "string" ? input : "");
    setError(null);
    setResult(null);
    if (isActive(job)) draft.resume(job.id);
    else onDone(job);
  });
  const busy = draft.busy || link.loading;

  async function run() {
    setError(null);
    try {
      const startedAt = window.location.pathname + window.location.search;
      link.remember(await draft.start({ [p.inputName]: value }), startedAt);
    } catch (e) {
      setError(String(e));
    }
  }

  function onDone(job: Job) {
    try { setResult(draft.finish(job)); }
    catch (err) { setError((err as Error).message); }
  }

  return (
    <div className="page">
      <header className="page-heading"><h1>{p.title}</h1><p>{p.description}</p></header>
      <section className="card workspace-panel">
      {!!p.starters?.length && <StarterPicker label="Notes starters" items={p.starters} disabled={busy} onUse={(starter) => {
        if (value.trim() && value !== starter.text && !window.confirm("Replace the current notes with this starter?")) return;
        setValue(starter.text);
        setError(null);
        setResult(null);
      }} />}
      <label>
        {p.inputLabel}
        <textarea
          aria-label={p.inputLabel}
          rows={10}
          value={value}
          disabled={busy}
          placeholder={p.placeholder}
          onChange={(e) => setValue(e.target.value)}
        />
      </label>
      <button className="primary" disabled={busy || !value.trim()} onClick={run}>
        {busy ? "Working..." : "Generate"}
      </button>
      {draft.jobId && <JobProgress jobId={draft.jobId} label="Generating announcements" onDone={onDone} />}
      {(link.error || error) && <p role="alert" className="error">{link.error || error}</p>}
      </section>
      <Outputs workflowId={p.workflowId} result={result} />
    </div>
  );
}
