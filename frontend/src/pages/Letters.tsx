import { useEffect, useState, type FormEvent } from "react";
import { ContactRound, Download, FileText, Mail, Plus, Save, Search, Sparkles } from "lucide-react";
import { api, type Contact, type Job, type MessageDraft, type SavedDraft } from "../api/client";
import { isActive, useBackgroundDraft, useJobLink } from "../activity";
import JobProgress from "../components/JobProgress";
import StarterPicker from "../components/StarterPicker";
import { correspondenceTemplates } from "../data/starters";
import { transcriptDate } from "../workspace";

const templates = correspondenceTemplates.map((item) => item.title);
const empty: MessageDraft = { recipient: "", email: "", subject: "", body: "", template: templates[0], notes: "" };

export default function Letters() {
  const [draft, setDraft] = useState<MessageDraft>(empty);
  const [draftId, setDraftId] = useState<number>();
  const [savedValue, setSavedValue] = useState<MessageDraft>(empty);
  const [drafts, setDrafts] = useState<SavedDraft[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [section, setSection] = useState<"drafts" | "contacts">("drafts");
  const [contactName, setContactName] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [search, setSearch] = useState("");
  const [action, setBusy] = useState("");
  const writing = useBackgroundDraft("letter");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const link = useJobLink("/letters", (job) => {
    if (job.kind !== "workflow") throw new Error("This link does not point to a correspondence draft.");
    const inputs = job.context?.inputs;
    const fields = inputs?.fields as Record<string, unknown> | undefined;
    setDraftId(undefined);
    setSavedValue(empty);
    setDraft({
      ...empty,
      template: typeof inputs?.letter_type === "string" ? inputs.letter_type : empty.template,
      recipient: typeof fields?.recipient === "string" ? fields.recipient : "",
      subject: typeof fields?.subject === "string" ? fields.subject : "",
      notes: typeof fields?.details === "string" ? fields.details : "",
      email: job.context?.email ?? "",
    });
    setNotice("");
    setError("");
    if (isActive(job)) writing.resume(job.id);
    else onDrafted(job);
  });
  const busy = writing.busy || link.loading ? "Writing…" : action;

  useEffect(() => {
    Promise.all([api.drafts(), api.contacts()]).then(([messages, people]) => {
      setDrafts(messages); setContacts(people);
    }).catch((err) => setError(err.message));
  }, []);

  function edit(update: Partial<MessageDraft>) {
    setDraft((value) => ({ ...value, ...update }));
    setNotice("");
  }

  function useTemplate(template: (typeof correspondenceTemplates)[number]) {
    if ((draft.subject.trim() || draft.body.trim()) &&
        !window.confirm("Replace this message’s subject and body with the template?")) return;
    const recipient = draft.recipient.trim();
    edit({
      subject: template.subject,
      body: recipient ? template.body.replace("[Name]", () => recipient) : template.body,
      template: template.title,
    });
    setError("");
    setNotice("Template loaded. Replace the bracketed details before exporting.");
  }

  function open(message?: SavedDraft) {
    if (JSON.stringify(draft) !== JSON.stringify(savedValue) && !window.confirm("Leave this message without saving your changes?")) return;
    const { id, updated_at: _date, ...fields } = message ?? { ...empty, id: undefined, updated_at: "" };
    setDraftId(id);
    setDraft(fields);
    setSavedValue(fields);
    setError("");
    setNotice("");
  }

  async function save() {
    setBusy("Saving…"); setError("");
    try {
      const { id, updated_at, ...fields } = await api.saveDraft(draft, draftId);
      setDraftId(id); setDraft(fields); setSavedValue(fields);
      setDrafts((previous) => [{ ...fields, id, updated_at }, ...previous.filter((item) => item.id !== id)]);
      setNotice("Draft saved on this computer.");
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(""); }
  }

  async function addContact(event: FormEvent) {
    event.preventDefault();
    setBusy("Saving…"); setError("");
    try {
      const contact = await api.saveContact({ name: contactName, email: contactEmail });
      setContacts((previous) => [...previous.filter((item) => item.id !== contact.id), contact].sort((a, b) => a.name.localeCompare(b.name)));
      setContactName(""); setContactEmail("");
      setNotice("Contact saved.");
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(""); }
  }

  async function generate() {
    if (draft.body.trim() && !window.confirm("Replace the current message with a new draft?")) return;
    setError("");
    try {
      const startedAt = window.location.pathname + window.location.search;
      const id = await writing.start({
        letter_type: draft.template,
        fields: { recipient: draft.recipient, subject: draft.subject, details: draft.notes },
      }, { resume: { email: draft.email } });
      link.remember(id, startedAt);
    } catch (err) { setError((err as Error).message); }
  }

  function onDrafted(job: Job) {
    try {
      const draftResult = writing.finish(job);
      edit({ body: draftResult.outputs.letter });
      setNotice("Draft generated and added to Generated Texts.");
    } catch (err) { setError((err as Error).message); }
  }

  async function exportFile(kind: "eml" | "docx") {
    setBusy("Preparing…"); setError("");
    try {
      const data = kind === "eml" ? await api.exportMail(draft) : await api.exportOutput("letter", "letter", draft.body, "docx");
      const url = URL.createObjectURL(data);
      const anchor = document.createElement("a");
      anchor.href = url; anchor.download = `office-draft.${kind}`; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(""); }
  }

  const filter = search.trim().toLowerCase();
  const matchingDrafts = drafts.filter((item) => `${item.subject} ${item.recipient} ${item.email}`.toLowerCase().includes(filter));
  const matchingContacts = contacts.filter((item) => `${item.name} ${item.email}`.toLowerCase().includes(filter));
  return (
    <div className="page">
      <header className="page-heading"><h1>Correspondence</h1><p>Keep your contacts and prepare messages, emails, and letters in one workspace.</p></header>
      <div className="mail-grid">
        <aside className="card workspace-panel mailbox">
          <button className="primary" disabled={!!busy} onClick={() => open()}><Plus size={18} /> New message</button>
          <div className="segmented" role="group" aria-label="Correspondence lists">
            <button aria-pressed={section === "drafts"} onClick={() => { setSection("drafts"); setSearch(""); }}><FileText size={15} /> Drafts</button>
            <button aria-pressed={section === "contacts"} onClick={() => { setSection("contacts"); setSearch(""); }}><ContactRound size={15} /> Contacts</button>
          </div>
          <span className="search-input"><Search size={16} aria-hidden="true" /><input aria-label={section === "contacts" ? "Search contacts" : "Search drafts"} placeholder={section === "contacts" ? "Search contacts…" : "Search drafts…"} value={search} onChange={(e) => setSearch(e.target.value)} /></span>
          {section === "drafts" ? (
            <div className="mail-list">
              {matchingDrafts.length ? matchingDrafts.map((item) => <button key={item.id} className="mail-item" disabled={!!busy} aria-pressed={draftId === item.id} onClick={() => open(item)}><strong>{item.subject || "(No subject)"}</strong><span>{item.recipient || item.email || "No recipient"}</span><small>{transcriptDate(item.updated_at)}</small></button>) : <p className="muted small">{filter ? "No matching drafts." : "Saved drafts will appear here."}</p>}
            </div>
          ) : (
            <>
              <div className="mail-list">
                {matchingContacts.length ? matchingContacts.map((contact) => <button key={contact.id} className="mail-item" disabled={!!busy} onClick={() => edit({ recipient: contact.name, email: contact.email })}><strong>{contact.name}</strong><span>{contact.email}</span></button>) : <p className="small muted">{filter ? "No matching contacts." : "Add a contact to reuse their address."}</p>}
              </div>
              <details className="mail-add">
                <summary>Add contact</summary>
                <form onSubmit={addContact}>
                  <label>Name<input value={contactName} maxLength={140} onChange={(e) => setContactName(e.target.value)} required /></label>
                  <label>Email<input value={contactEmail} type="email" maxLength={254} onChange={(e) => setContactEmail(e.target.value)} required /></label>
                  <button disabled={!!busy}>Save contact</button>
                </form>
              </details>
            </>
          )}
        </aside>
        <section className="card workspace-panel mail-composer">
          <div className="panel-heading"><span className="tool-icon mint"><Mail size={19} /></span><div><h2>{draftId ? "Edit draft" : "New message"}</h2><p>Write a message or start with a letter template.</p></div></div>
          <StarterPicker label="Message templates" action="Use template" items={correspondenceTemplates} disabled={!!busy} onUse={useTemplate} />
          <div className="two-col">
            <label>To · Name<input value={draft.recipient} disabled={writing.busy || link.loading} maxLength={140} onChange={(e) => edit({ recipient: e.target.value })} placeholder="Recipient name" /></label>
            <label>Email address<input type="email" value={draft.email} disabled={writing.busy || link.loading} maxLength={254} onChange={(e) => edit({ email: e.target.value })} placeholder="name@example.org" /></label>
          </div>
          <label>Subject<input value={draft.subject} disabled={writing.busy || link.loading} maxLength={250} onChange={(e) => edit({ subject: e.target.value })} /></label>
          <label>Message<textarea aria-label="Message" value={draft.body} disabled={writing.busy || link.loading} maxLength={30000} rows={9} onChange={(e) => edit({ body: e.target.value })} placeholder="Write your message…" /></label>
          <details className="mail-add">
            <summary><Sparkles size={16} /> Draft with AI</summary>
            <label>Letter type<select value={draft.template} disabled={writing.busy || link.loading} onChange={(e) => edit({ template: e.target.value })}>{templates.map((template) => <option key={template}>{template}</option>)}</select></label>
            <label>Points to include<textarea value={draft.notes} disabled={writing.busy || link.loading} maxLength={5000} rows={3} onChange={(e) => edit({ notes: e.target.value })} placeholder={correspondenceTemplates.find((item) => item.title === draft.template)?.notes ?? "What should the recipient know?"} /></label>
            <button disabled={!!busy || !draft.notes.trim()} onClick={() => void generate()}><Sparkles size={15} /> {busy === "Writing…" ? busy : "Generate message"}</button>
          </details>
          {writing.jobId && <JobProgress jobId={writing.jobId} label="Drafting correspondence" onDone={onDrafted} />}
          <div className="row">
            <button className="primary" disabled={!!busy || !Object.values({ message: draft.body, subject: draft.subject, recipient: draft.recipient, notes: draft.notes }).some((value) => value.trim())} onClick={() => void save()}><Save size={16} /> {busy === "Saving…" ? busy : "Save draft"}</button>
            <button disabled={!!busy || !draft.body.trim()} onClick={() => void exportFile("eml")}><Download size={16} /> Export email</button>
            <button disabled={!!busy || !draft.body.trim()} onClick={() => void exportFile("docx")}><Download size={16} /> Export Word</button>
          </div>
          {(link.error || error) && <p className="error" role="alert">{link.error || error}</p>}
          {notice && <p className="success-text" role="status">{notice}</p>}
        </section>
      </div>
    </div>
  );
}
