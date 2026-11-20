import { useEffect, useLayoutEffect, useRef, useState, type FormEvent } from "react";
import { ArrowDown, ArrowUp, BookOpen, Copy, MessageCircle, Search, Square, Trash2 } from "lucide-react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useActivity } from "../activity";
import { api, type ChatMessage, type Citation, type Passage } from "../api/client";

type Mode = "general" | "bible" | "office";
type Turn = ChatMessage & { passages?: Passage[]; citations?: Citation[] };
const modes: { id: Mode; label: string; description: string; samples: string[] }[] = [
  { id: "general", label: "General", description: "Ask a question, brainstorm, or work through an idea with your local model.", samples: ["Help me plan a volunteer appreciation evening.", "Turn this rough idea into a checklist.", "Explain compound interest in plain English."] },
  { id: "bible", label: "Bible & Christianity", description: "Ask about scripture or Christian traditions. Open the passages alongside the answer.", samples: ["What do Christians believe about baptism?", "What does Philippians 4:6–7 say about worry?", "How do Christian traditions understand communion?"] },
  { id: "office", label: "Office documents", description: "Find answers in excerpts from your Library.", samples: ["What have we announced recently?", "What do our documents say about building use?"] },
];
const emptyThread: Turn[] = [];

function readThreads(): Record<Mode, Turn[]> {
  const blank = { general: [], bible: [], office: [] };
  try { return { ...blank, ...JSON.parse(sessionStorage.getItem("loa-chat") ?? "{}") }; }
  catch { return blank; }
}

function PassageCards({ passages }: { passages: Passage[] }) {
  return <div className="passage-list">{passages.map((passage, index) => (
    <details key={passage.ref}><summary><BookOpen size={15} />{index + 1}. {passage.ref}<small>WEB</small></summary><p>{passage.text}</p></details>
  ))}</div>;
}

export default function Ask() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const { track } = useActivity();
  const [previousMode, setPreviousMode] = useState<Mode>("general");
  const requested = location.pathname === "/ask" ? modes.find((item) => item.id === params.get("mode")) : undefined;
  const mode = requested ?? modes.find((item) => item.id === previousMode) ?? modes[0];
  useEffect(() => { if (requested) setPreviousMode(requested.id); }, [requested]);
  const [threads, setThreads] = useState(readThreads);
  const [questions, setQuestions] = useState<Record<Mode, string>>({ general: "", bible: "", office: "" });
  const query = questions[mode.id];
  function setQuery(value: string) {
    setQuestions((previous) => ({ ...previous, [mode.id]: value }));
  }
  const [passageQuery, setPassageQuery] = useState("");
  const [passages, setPassages] = useState<Passage[] | null>(null);
  const [lookupError, setLookupError] = useState("");
  const [looking, setLooking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);
  const [notice, setNotice] = useState("");
  const [atLatest, setAtLatest] = useState(true);
  const request = useRef<{ controller: AbortController; mode: Mode } | null>(null);
  const composer = useRef<HTMLTextAreaElement>(null);
  const conversation = useRef<HTMLDivElement>(null);
  const clearDialog = useRef<HTMLDialogElement>(null);
  const followLatest = useRef(true);
  const lastMode = useRef(mode.id);
  const thread = threads[mode.id] ?? emptyThread;
  const modeBusy = busy && request.current?.mode === mode.id;

  useEffect(() => () => request.current?.controller.abort(), []);
  useEffect(() => {
    try { sessionStorage.setItem("loa-chat", JSON.stringify(threads)); } catch { /* tab history is optional */ }
  }, [threads]);

  function jumpToLatest() {
    if (!conversation.current) return;
    followLatest.current = true;
    conversation.current.scrollTop = conversation.current.scrollHeight;
    setAtLatest(true);
  }

  useLayoutEffect(() => {
    if (location.pathname !== "/ask") return;
    if (lastMode.current !== mode.id) {
      lastMode.current = mode.id;
      followLatest.current = true;
    }
    if (followLatest.current) jumpToLatest();
  }, [thread, mode.id, location.pathname]);

  function clearChat() {
    if (request.current?.mode === mode.id) {
      const previous = request.current;
      request.current = null;
      previous.controller.abort();
      setBusy(false);
    }
    setThreads((history) => ({ ...history, [mode.id]: [] }));
    setQuery("");
    setError("");
    setCopied(false);
    setNotice(`${mode.label} chat cleared.`);
    followLatest.current = true;
    setAtLatest(true);
    clearDialog.current?.close();
    window.requestAnimationFrame(() => composer.current?.focus({ preventScroll: true }));
  }

  async function ask(question = query) {
    const clean = question.trim();
    if (!clean || request.current) return;
    const controller = new AbortController();
    const modeId = mode.id;
    request.current = { controller, mode: modeId };
    const done = track(`${mode.label} answer`, `/ask?mode=${modeId}`, "Generating a local answer");
    let failure = "";
    const history: Turn[] = [...thread, { role: "user", content: clean }];
    let answer: Turn = { role: "assistant", content: "" };
    const publish = () => {
      if (request.current?.controller !== controller || controller.signal.aborted) return;
      const turns = [...history, answer];
      setThreads((previous) => ({ ...previous, [modeId]: turns }));
    };
    followLatest.current = true;
    setQuery("");
    setError("");
    setCopied(false);
    setNotice("");
    setBusy(true);
    publish();
    try {
      if (modeId === "office") {
        const reply = await api.ask(clean, controller.signal);
        if (request.current?.controller === controller && !controller.signal.aborted) {
          answer = { role: "assistant", content: reply.answer, citations: reply.citations };
          publish();
        }
      } else {
        await api.chat(modeId, history.filter((turn) => turn.content.trim()).slice(-15).map(({ role, content }) =>
          ({ role, content: content.slice(0, 4000) })), (event) => {
          if (event.type === "error") throw new Error(event.value);
          if (event.type === "text") answer = { ...answer, content: answer.content + event.value };
          if (event.type === "sources") answer = { ...answer, passages: event.value };
          publish();
        }, controller.signal);
      }
    } catch (err) {
      if (request.current?.controller === controller && !controller.signal.aborted) {
        failure = (err as Error).message;
        setError(failure);
      }
    } finally {
      if (controller.signal.aborted) failure = "Stopped";
      done(failure ? "error" : "done", failure || undefined);
      if (request.current?.controller === controller) {
        if (!answer.content.trim()) setThreads((previous) => ({ ...previous, [modeId]: history }));
        request.current = null;
        setBusy(false);
      }
    }
  }

  async function find(event: FormEvent) {
    event.preventDefault();
    if (!passageQuery.trim()) return;
    setLooking(true);
    setLookupError("");
    try { setPassages((await api.lookup(passageQuery.trim())).passages); }
    catch (err) { setLookupError((err as Error).message); }
    finally { setLooking(false); }
  }

  return (
    <div className="page ask-workspace">
      <header className="page-heading studio-heading">
        <div><h1>Ask</h1><p>{mode.description}</p></div>
        <button disabled={!modeBusy && !thread.length && !query.trim()} onClick={() => clearDialog.current?.showModal()}>
          <Trash2 size={17} aria-hidden="true" /> Clear chat
        </button>
      </header>
      <dialog ref={clearDialog} className="clear-chat-dialog" aria-labelledby="clear-chat-title">
        <h2 id="clear-chat-title">Clear {mode.label} chat?</h2>
        <p>This clears the messages and any unsent question in this mode. Saved answers stay in Generated Texts.</p>
        <div className="row">
          <button autoFocus onClick={() => clearDialog.current?.close()}>Cancel</button>
          <button className="primary" onClick={clearChat}>Clear this chat</button>
        </div>
      </dialog>
      <section className="card workspace-panel chat-card">
        <div className="segmented" role="group" aria-label="Answer sources">
          {modes.map((item) => <button key={item.id} aria-pressed={mode.id === item.id} disabled={busy} onClick={() => { setParams({ mode: item.id }); setError(""); setCopied(false); setNotice(""); }}>{item.label}</button>)}
        </div>
        {mode.id === "bible" && <details className="verse-lookup" open={params.get("find") === "yes" ? true : undefined}>
          <summary><BookOpen size={17} /> Find a Bible verse</summary>
          <form onSubmit={find} className="inline-input">
            <input aria-label="Verse, phrase, or topic" placeholder="John 3:16, love one another, or forgiveness" maxLength={260} value={passageQuery} onChange={(e) => setPassageQuery(e.target.value)} />
            <button disabled={looking || !passageQuery.trim()}><Search size={16} />{looking ? "Searching…" : "Find"}</button>
          </form>
          <div className="row verse-examples">{["John 3:16", "love one another", "forgiveness"].map((example) => (
            <button type="button" key={example} disabled={looking} onClick={() => setPassageQuery(example)}>{example}</button>
          ))}</div>
          {lookupError && <p className="error" role="alert">{lookupError}</p>}
          {passages?.length === 0 && <p className="muted small">No matches. Try a shorter phrase or a full reference.</p>}
          {passages && <PassageCards passages={passages} />}
        </details>}
        <div className="conversation" role="region" aria-label="Conversation" ref={conversation} tabIndex={thread.length ? 0 : undefined}
          onScroll={(event) => {
            const box = event.currentTarget;
            followLatest.current = box.scrollHeight - box.clientHeight - box.scrollTop < 32;
            setAtLatest(followLatest.current);
          }}>
          {!thread.length && <div className="chat-empty">
            <span className="tool-icon mint">{mode.id === "bible" ? <BookOpen size={20} /> : <MessageCircle size={20} />}</span>
            <h2>What would you like to ask?</h2>
            <div className="chat-prompts">{mode.samples.map((sample) => <button disabled={busy} key={sample} onClick={() => { setQuery(sample); composer.current?.focus(); }}>{sample}</button>)}</div>
          </div>}
          {thread.map((turn, index) => <article className={`chat-turn ${turn.role}`} key={index}>
            <strong>{turn.role === "user" ? "You" : mode.label}</strong>
            <p>{turn.content || "Thinking…"}</p>
            {!!turn.passages?.length && <PassageCards passages={turn.passages} />}
            {turn.citations?.map((citation, i) => <details key={citation.chunk_id}><summary>{i + 1}. {citation.title}{citation.page ? ` · p. ${citation.page}` : ""}</summary><p>{citation.text}</p></details>)}
          </article>)}
          {modeBusy && <span className="visually-hidden" role="status">Generating a local answer</span>}
        </div>
        {!atLatest && thread.length > 0 && <button className="jump-latest" onClick={jumpToLatest}><ArrowDown size={15} /> Jump to latest</button>}
        {error && <p className="error" role="alert">{error}</p>}
        <form className="chat-composer" onSubmit={(event) => { event.preventDefault(); if (!busy) void ask(); }}>
          <label className="visually-hidden" htmlFor="chat-composer">Your question</label>
          <textarea id="chat-composer" ref={composer} placeholder={mode.id === "office" ? "Ask about your documents…" : "Type a question…"} rows={2}
            value={query} maxLength={4000} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); if (!busy) void ask(); }
            }} />
          {modeBusy ? <button type="button" className="icon-button" aria-label="Stop answer" onClick={() => request.current?.controller.abort()}><Square size={17} /></button> :
            <button className="primary icon-button" aria-label="Ask question" disabled={busy || !query.trim()}><ArrowUp size={20} /></button>}
        </form>
        <div className="chat-footer"><small>{mode.id === "office" ? "Each question searches your Library." : "Chat history is kept in this browser tab."}</small>
          {notice && <small role="status">{notice}</small>}
          {thread.some((turn) => turn.role === "assistant" && turn.content) && <button className="text-button" disabled={busy} onClick={async () => {
            try { await navigator.clipboard.writeText([...thread].reverse().find((turn) => turn.role === "assistant")?.content ?? ""); setCopied(true); }
            catch { setError("Could not access the clipboard."); }
          }}><Copy size={13} />{copied ? "Copied" : "Copy last answer"}</button>}
        </div>
      </section>
    </div>
  );
}
