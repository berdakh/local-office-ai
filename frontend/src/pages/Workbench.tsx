import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { indentWithTab } from "@codemirror/commands";
import { python } from "@codemirror/lang-python";
import { EditorState, Prec } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { basicSetup } from "codemirror";
import { Code2, Download, FolderOpen, Play, Plus, RefreshCw, Terminal, X } from "lucide-react";
import { api, type Diagnostics, type ExperimentResult } from "../api/client";
import { experiments } from "../data/experiments";

type Script = { id: string; name: string; code: string };
type RunMode = "file" | "cell" | "selection";
type Run = { script: string; mode: RunMode; result: ExperimentResult };
const MAX_CODE = 20_000;
const firstScript = { id: "timing", name: experiments[0].name, code: experiments[0].code };
const cellMarker = /^\s*#\s*%%/;

function restoreScripts(): Script[] {
  try {
    const stored: Script[] = JSON.parse(sessionStorage.getItem("loa-workbench-scripts") ?? "null");
    if (Array.isArray(stored) && stored.length) return stored;
  } catch { /* the editor can run without browser storage */ }
  return [firstScript];
}

function target(view: EditorView, mode: RunMode) {
  const { doc, selection } = view.state;
  if (mode === "file") return doc.toString();
  const { from, to, head } = selection.main;
  const line = doc.lineAt(head);
  if (mode === "selection") {
    const lines = (from === to ? line.text : doc.sliceString(from, to)).split("\n");
    const indent = Math.min(...lines.filter((text) => text.trim()).map((text) => text.match(/^\s*/)?.[0].length ?? 0));
    return lines.map((text) => text.slice(indent)).join("\n");
  }
  let first = line.number;
  while (first > 1 && !cellMarker.test(doc.line(first).text)) first--;
  if (cellMarker.test(doc.line(first).text)) first++;
  let last = first;
  while (last <= doc.lines && !cellMarker.test(doc.line(last).text)) last++;
  return first < last ? doc.sliceString(doc.line(first).from, doc.line(last - 1).to) : "";
}

function PythonEditor({ script, onChange, onRun, register }: {
  script: Script; onChange: (code: string) => void;
  onRun: (mode: RunMode) => boolean; register: (view: EditorView | null) => void;
}) {
  const mount = useRef<HTMLDivElement>(null);
  const callbacks = useRef({ onChange, onRun, register });
  callbacks.current = { onChange, onRun, register };
  useEffect(() => {
    if (!mount.current) return;
    const view = new EditorView({
      parent: mount.current,
      state: EditorState.create({
        doc: script.code,
        extensions: [
          basicSetup, python(),
          EditorView.contentAttributes.of({ "aria-label": "Python code", spellcheck: "false" }),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) callbacks.current.onChange(update.state.doc.toString());
          }),
          Prec.highest(keymap.of([
            { key: "F5", run: () => callbacks.current.onRun("file") },
            { key: "F9", run: () => callbacks.current.onRun("selection") },
            { key: "Mod-Enter", run: () => callbacks.current.onRun("cell") },
            indentWithTab,
          ])),
        ],
      }),
    });
    callbacks.current.register(view);
    return () => { callbacks.current.register(null); view.destroy(); };
  }, []);
  return <div className="workbench-code" ref={mount} />;
}

export default function Workbench() {
  const [scripts, setScripts] = useState(restoreScripts);
  const [active, setActive] = useState(() => scripts[0].id);
  const [template, setTemplate] = useState(experiments[0].name);
  const [run, setRun] = useState<Run | null>(null);
  const [panel, setPanel] = useState<"console" | "variables">("console");
  const [ready, setReady] = useState<Diagnostics | null>(null);
  const [busy, setBusy] = useState<RunMode | null>(null);
  const [error, setError] = useState("");
  const editor = useRef<EditorView | null>(null);
  const input = useRef<HTMLInputElement>(null);
  const script = scripts.find((item) => item.id === active) ?? scripts[0];
  const chosen = experiments.find((item) => item.name === template) ?? experiments[0];

  function diagnostics() { api.diagnostics().then(setReady).catch((err) => setError(err.message)); }
  useEffect(diagnostics, []);
  useEffect(() => {
    try { sessionStorage.setItem("loa-workbench-scripts", JSON.stringify(scripts)); } catch { /* saving scripts as files is still available */ }
  }, [scripts]);

  function create(name: string, code = "") {
    const next = { id: crypto.randomUUID(), name, code };
    setScripts((previous) => [...previous, next]);
    setActive(next.id);
    setError("");
  }

  function close(id: string) {
    const remaining = scripts.filter((item) => item.id !== id);
    if (remaining.length === 0) {
      setScripts([{ id: crypto.randomUUID(), name: "untitled.py", code: "" }]);
      return;
    }
    setScripts(remaining);
    if (id === active) setActive(remaining[0].id);
  }

  async function openFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      if (file.size > MAX_CODE * 4) throw new Error("Open a Python script under 20,000 characters.");
      const code = await file.text();
      if (code.length > MAX_CODE) throw new Error("Open a Python script under 20,000 characters.");
      create(file.name, code);
    } catch (err) { setError((err as Error).message); }
  }

  async function execute(mode: RunMode) {
    if (!editor.current || busy || !ready?.python_runner) return;
    const code = target(editor.current, mode);
    if (!code.trim()) {
      setError("There is no Python code in the selected area.");
      return;
    }
    if (code.length > MAX_CODE) {
      setError("Run up to 20,000 characters at a time.");
      return;
    }
    setBusy(mode);
    setPanel("console");
    setError("");
    try { setRun({ script: script.name, mode, result: await api.experiment(code) }); }
    catch (err) { setError((err as Error).message); }
    finally { setBusy(null); }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([script.code], { type: "text/x-python" }));
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = script.name; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  return <div className="page">
    <header className="page-heading"><h1>Workbench</h1><p>Open an experiment, edit the Python, and inspect its output.</p></header>
    <div className="workbench-grid">
      <section className="card workspace-panel workbench-editor">
        <div className="panel-heading"><span className="tool-icon blue"><Code2 size={19} /></span><div><h2>Editor</h2><p>Each run starts an isolated Python session.</p></div></div>
        <div className="workbench-template">
          <label>Experiment templates<select aria-label="Experiment templates" value={template} onChange={(event) => setTemplate(event.target.value)}>
            {experiments.map((item) => <option key={item.name} value={item.name}>{item.title}</option>)}
          </select></label>
          <button type="button" onClick={() => create(chosen.name, chosen.code)}>Open template</button>
          <p className="small muted">{chosen.about}</p>
        </div>
        <div className="row">
          <button onClick={() => create("untitled.py")}><Plus size={15} /> New script</button>
          <button onClick={() => input.current?.click()}><FolderOpen size={15} /> Open .py</button>
          <input type="file" className="visually-hidden" accept=".py,text/x-python" ref={input} tabIndex={-1} aria-label="Python script file" onChange={(event) => void openFile(event)} />
          <button onClick={download}><Download size={15} /> Save .py</button>
        </div>
        <div className="script-tabs" role="group" aria-label="Open scripts">
          {scripts.map((item) => <div key={item.id} className={item.id === script.id ? "active" : ""}>
            <button aria-pressed={item.id === script.id} onClick={() => setActive(item.id)}>{item.name}</button>
            <button className="tab-close" aria-label={`Close ${item.name}`} onClick={() => close(item.id)}><X size={13} /></button>
          </div>)}
        </div>
        <PythonEditor key={script.id} script={script} onChange={(code) => setScripts((existing) =>
          existing.map((item) => item.id === script.id ? { ...item, code } : item))}
          register={(view) => { editor.current = view; }} onRun={(mode) => { void execute(mode); return true; }} />
        <div className="row">
          <button className="primary" disabled={!!busy || !script.code.trim() || !ready?.python_runner} onClick={() => void execute("file")} title="F5"><Play size={16} />{busy === "file" ? "Running…" : "Run file"}</button>
          <button disabled={!!busy || !script.code.trim() || !ready?.python_runner} onClick={() => void execute("cell")} title="Ctrl+Enter">Run cell</button>
          <button disabled={!!busy || !script.code.trim() || !ready?.python_runner} onClick={() => void execute("selection")} title="F9">Run selection</button>
        </div>
        <p className="small muted workbench-help">F5 runs the file · Ctrl+Enter runs a # %% cell · F9 runs a selection or the current line.</p>
        {ready && !ready.python_runner && <p className="small muted">Running experiments requires Linux with Bubblewrap. You can still write and save scripts.</p>}
      </section>
      <section className="card workspace-panel">
        <div className="panel-heading"><span className="tool-icon mint"><Terminal size={19} /></span><div><h2>Results</h2><p>{run ? `${run.script} · ${run.mode}` : "Console output and variables from the last run."}</p></div></div>
        <div className="segmented results-tabs" role="group" aria-label="Experiment results">
          <button aria-pressed={panel === "console"} onClick={() => setPanel("console")}>Console</button>
          <button aria-pressed={panel === "variables"} onClick={() => setPanel("variables")}>Variables</button>
        </div>
        {panel === "console" ? (
          <pre className="workbench-output" role="log">{busy ? "Running…" : run ? `${run.result.output || "No output."}\n\nExit code ${run.result.exit_code}` : "Run an experiment to see its output."}</pre>
        ) : (
          <div className="variable-table">
            {run?.result.variables.length ? <table><thead><tr><th>Name</th><th>Type</th><th>Value</th></tr></thead>
              <tbody>{run.result.variables.map((item) => <tr key={item.name}><td><code>{item.name}</code></td><td>{item.type}</td><td><code>{item.value}</code></td></tr>)}</tbody>
            </table> : <p className="muted small">Run code that creates a value to inspect it here.</p>}
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </section>
    </div>
    <section className="card workspace-panel diagnostics">
      <div className="section-heading"><h2>Diagnostics</h2><button aria-label="Refresh diagnostics" onClick={diagnostics}><RefreshCw size={16} /> Refresh</button></div>
      {ready && <dl><div><dt>Runtime</dt><dd>Python {ready.python} · build {ready.build}</dd></div><div><dt>Database</dt><dd>{ready.database} · {ready.documents} documents</dd></div>
        <div><dt>Local model server</dt><dd>{ready.ollama_connected ? "Connected" : "Unavailable"}</dd></div><div><dt>Jobs</dt><dd>{Object.entries(ready.job_counts).map(([status, count]) => `${count} ${status}`).join(" · ") || "None"}</dd></div>
        <div><dt>Runtime assets</dt><dd>{Object.entries(ready.binary_assets).map(([name, ok]) => `${name} ${ok ? "ready" : "missing"}`).join(" · ")}</dd></div>
      </dl>}
    </section>
  </div>;
}
