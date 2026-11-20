export type Health = {
  ok: boolean;
  pack: string;
  pack_title: string;
  ollama: { available: boolean; url: string; models: string[] };
  chat_model: string;
  embed_model: string;
  chat_model_installed: boolean;
  embed_model_installed: boolean;
  data_dir: string;
  transcription_available: boolean;
  whisper_model: string;
  bible_installed: boolean;
  letterhead_installed: boolean;
};

export type ScriptureCheck = {
  ref: string;
  status: "verified" | "not_found" | "unverified";
  text: string | null;
  note: string | null;
};

export type Job = {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error";
  progress: number;
  result: Record<string, unknown> | null;
  error: string | null;
  label?: string | null;
  detail?: string | null;
  route?: string | null;
  context?: {
    workflow?: string;
    inputs?: Record<string, unknown>;
    chat_model?: string;
    selected_outputs?: string[] | null;
    email?: string | null;
    transcript_id?: number | null;
    name?: string;
    recording?: string;
  } | null;
};

export type ActivityJob = Omit<Job, "result" | "context"> & { created_at: string; updated_at: string };
export type WorkflowOptions = {
  chat_model?: string;
  selected_outputs?: string[];
  resume?: { email?: string; transcript_id?: number };
};
export type GeneratedStatus = "draft" | "reviewed";
export type GeneratedRecord = {
  id: number; run_id: string; workflow: string; output_key: string; title: string;
  model: string; sources: string[]; tags: string[]; status: GeneratedStatus;
  created_at: string; updated_at: string;
};
export type GeneratedRow = GeneratedRecord & { preview: string };
export type GeneratedText = GeneratedRecord & { body: string };
export type GeneratedUpdate = Pick<GeneratedText, "title" | "body" | "status" | "tags">;

export type TranscriptSummary = {
  id: number;
  title: string;
  created_at: string;
  duration: number | null;
  scripture: ScriptureCheck[];
};

export type Citation = {
  chunk_id: number;
  document_id: number;
  title: string;
  page: number | null;
  text: string;
  score: number;
};

export type Passage = { ref: string; text: string };
export type Segment = { start: number; end: number; text: string };
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type ChatEvent =
  | { type: "text" | "error"; value: string }
  | { type: "sources"; value: Passage[] }
  | { type: "done"; value: null };
export type Contact = { id: number; name: string; email: string };
export type MessageDraft = { recipient: string; email: string; subject: string; body: string; template: string; notes: string };
export type SavedDraft = MessageDraft & { id: number; updated_at: string };
export type Hardware = {
  os: string; cpu: string; threads: number | null; ram_gib: number | null; free_gb: number;
  gpus: { name: string; vram_gib: number | null; candidate: boolean }[];
  models: { tag: string; label: string; download_gb: number; gpu_candidate: boolean; installed: boolean }[];
  recommended: string | null;
  running: { name: string; size: number; size_vram: number }[];
};
export type Diagnostics = {
  python_runner: boolean; python: string; build: string; database: string; documents: number;
  job_counts: Record<string, number>; ollama_connected: boolean; binary_assets: Record<string, boolean>;
};
export type PythonVariable = { name: string; type: string; value: string };
export type ExperimentResult = { exit_code: number; output: string; variables: PythonVariable[] };

export type RunResult = {
  run_id: string;
  outputs: Record<string, string>;
  citations: Citation[];
  files: string[];
  scripture?: { refs: ScriptureCheck[]; context: string; verified: boolean } | null;
};

export type Document = {
  id: number;
  title: string;
  kind: string;
  created_at: string;
  chunks: number;
};

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const message = typeof body?.detail === "string" ? body.detail :
      Array.isArray(body?.detail) ? body.detail[0]?.msg ?? "Check the entered values." : `Request failed (${res.status}).`;
    throw new ApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}

function send(path: string, body: unknown, method = "POST", signal?: AbortSignal) {
  return fetch(path, {
    method, signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  health: () => fetch("/api/health").then((r) => json<Health>(r)),
  models: () => fetch("/api/settings/models").then((r) => json<string[]>(r)),
  saveModel: (chatModel: string | null) =>
    fetch("/api/settings/models", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_model: chatModel }),
    }).then((r) => json<{ chat_model: string }>(r)),
  runWorkflow: (id: string, inputs: Record<string, unknown>, options?: {
    chat_model?: string;
    selected_outputs?: string[];
  }) =>
    fetch(`/api/workflows/${id}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ inputs, ...options }),
    }).then((r) => json<RunResult>(r)),
  startWorkflow: (id: string, inputs: Record<string, unknown>, options?: WorkflowOptions) =>
    send(`/api/workflows/${id}/jobs`, { inputs, ...options }).then((r) => json<{ job_id: string }>(r)),
  jobs: () => fetch("/api/jobs").then((r) => json<ActivityJob[]>(r)),
  generated: (params: URLSearchParams) => fetch(`/api/generated?${params}`).then((r) => json<{ items: GeneratedRow[]; total: number }>(r)),
  generatedText: (id: number) => fetch(`/api/generated/${id}`).then((r) => json<GeneratedText>(r)),
  updateGenerated: (id: number, data: GeneratedUpdate) =>
    send(`/api/generated/${id}`, data, "PUT").then((r) => json<GeneratedText>(r)),
  exportOutput: async (
    workflowId: string,
    outputName: string,
    text: string,
    format: "md" | "docx",
  ) => {
    const path = `/api/workflows/${encodeURIComponent(workflowId)}/outputs/${encodeURIComponent(outputName)}/export`;
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, format }),
    });
    if (!response.ok) throw new Error(`Download failed (HTTP ${response.status}).`);
    return response.blob();
  },
  ask: (question: string, signal?: AbortSignal) =>
    fetch("/api/ask", {
      method: "POST",
      signal,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    }).then((r) => json<{ answer: string; citations: Citation[] }>(r)),
  documents: () => fetch("/api/library").then((r) => json<Document[]>(r)),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/library", { method: "POST", body: form }).then((r) =>
      json<{ document_id: number; job_id: string; pages: number }>(r),
    );
  },
  deleteDocument: (id: number) =>
    fetch(`/api/library/${id}`, { method: "DELETE" }).then((r) => json<{ ok: boolean }>(r)),
  audit: () => fetch("/api/audit").then((r) => json<unknown[]>(r)),
  contacts: () => fetch("/api/correspondence/contacts").then((r) => json<Contact[]>(r)),
  saveContact: (contact: Omit<Contact, "id">) => send("/api/correspondence/contacts", contact).then((r) => json<Contact>(r)),
  drafts: () => fetch("/api/correspondence/drafts").then((r) => json<SavedDraft[]>(r)),
  saveDraft: (draft: MessageDraft, id?: number) => send(
    id ? `/api/correspondence/drafts/${id}` : "/api/correspondence/drafts",
    draft, id ? "PUT" : "POST",
  ).then((r) => json<SavedDraft>(r)),
  exportMail: async (draft: MessageDraft) => {
    const response = await send("/api/correspondence/export", draft);
    if (!response.ok) await json<never>(response);
    return response.blob();
  },
  hardware: () => fetch("/api/settings/hardware").then((r) => json<Hardware>(r)),
  downloadModel: (model: string) => send("/api/settings/hardware/download", { model }).then((r) => json<{ job_id: string | null }>(r)),
  diagnostics: () => fetch("/api/workbench/diagnostics").then((r) => json<Diagnostics>(r)),
  experiment: (code: string) => send("/api/workbench/python", { code }).then((r) => json<ExperimentResult>(r)),
  lookup: (q: string) => fetch(`/api/scripture/lookup?q=${encodeURIComponent(q)}`).then((r) => json<{ version: string; passages: Passage[] }>(r)),
  chat: async (
    mode: "general" | "bible", messages: ChatMessage[], onEvent: (event: ChatEvent) => void,
    signal: AbortSignal,
  ) => {
    const response = await send("/api/chat", { mode, messages }, "POST", signal);
    if (!response.ok) await json<never>(response);
    if (!response.body) throw new Error("Chat streaming is unavailable.");
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
    let buffer = "";
    let finished = false;
    const publish = (line: string) => {
      if (!line.trim()) return;
      const event = JSON.parse(line) as ChatEvent;
      if (event.type === "done") finished = true;
      onEvent(event);
    };
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const lines = (buffer + value).split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) publish(line);
      }
      publish(buffer);
      if (!finished && !signal.aborted) throw new Error("The local app disconnected before the answer finished.");
    } finally {
      await reader.cancel().catch(() => undefined);
    }
  },
  micPreview: (pcm: ArrayBuffer, signal: AbortSignal) => fetch("/api/transcribe/live", {
    method: "POST", body: pcm, signal, headers: { "Content-Type": "application/octet-stream" },
  }).then((r) => json<{ text: string }>(r)),
  transcribe: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/transcribe", { method: "POST", body: form }).then((r) =>
      json<{ job_id: string; name: string }>(r),
    );
  },
  job: (id: string) => fetch(`/api/jobs/${id}`).then((r) => json<Job>(r)),
  transcripts: () => fetch("/api/transcripts").then((r) => json<TranscriptSummary[]>(r)),
  transcript: (id: number) =>
    fetch(`/api/transcripts/${id}`).then((r) =>
      json<{ id: number; title: string; text: string; meta: Record<string, unknown>; timeline: Segment[]; audio_available: boolean }>(r),
    ),
  checkScripture: (text: string) =>
    fetch("/api/scripture/check", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    }).then((r) => json<{ verified_against: string | null; refs: ScriptureCheck[] }>(r)),
};
