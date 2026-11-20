import { useState } from "react";
import { Clipboard, Download } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type RunResult } from "../api/client";

function Draft({ workflowId, name, initialText, hidden }: {
  workflowId: string;
  name: string;
  initialText: string;
  hidden: boolean;
}) {
  const [text, setText] = useState(initialText);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState("");
  const title = name.replace(/_/g, " ");

  async function copy() {
    setError("");
    setFeedback("");
    try {
      await navigator.clipboard.writeText(text);
      setFeedback("Copied draft.");
    } catch {
      setError("Could not access the clipboard. Select and copy the draft text.");
    }
  }

  async function download(format: "md" | "docx") {
    setBusy(true);
    setError("");
    setFeedback("");
    try {
      const blob = await api.exportOutput(workflowId, name, text, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${name.replace(/_/g, "-")}.${format}`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch {
      setError("Could not download the draft. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card workspace-panel" hidden={hidden}>
      <h3>{title}</h3>
      <textarea
        aria-label={`${title} draft`}
        value={text}
        onChange={(event) => {
          setText(event.target.value);
          setFeedback("");
          setError("");
        }}
        rows={12}
      />
      <div className="row">
        <button onClick={copy}><Clipboard size={16} />Copy</button>
        <button disabled={busy} onClick={() => download("docx")}><Download size={16} />Download Word</button>
        <button disabled={busy} onClick={() => download("md")}>Download Markdown</button>
      </div>
      {feedback && <p className="muted small" role="status">{feedback}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function DraftCollection({ workflowId, result }: { workflowId: string; result: RunResult }) {
  const [active, setActive] = useState(Object.keys(result.outputs)[0]);
  const outputs = Object.entries(result.outputs);
  return (
    <div className="outputs">
      <div className="section-heading"><h2 className="section-title">Generated drafts</h2>
        <Link to={`/generated?run=${encodeURIComponent(result.run_id)}`}>View in Generated Texts</Link>
      </div>
      {outputs.length > 1 && <div className="segmented output-tabs" role="group" aria-label="Generated drafts">
        {outputs.map(([name]) => <button key={name} aria-pressed={active === name} onClick={() => setActive(name)}>{name.replace(/_/g, " ")}</button>)}
      </div>}
      {outputs.map(([name, text]) => (
        <Draft
          key={`${result.run_id}:${name}`}
          workflowId={workflowId}
          name={name}
          initialText={String(text ?? "")}
          hidden={name !== active}
        />
      ))}
    </div>
  );
}

export default function Outputs({ workflowId, result }: {
  workflowId: string;
  result: RunResult | null;
}) {
  return result ? <DraftCollection key={result.run_id} workflowId={workflowId} result={result} /> : null;
}
