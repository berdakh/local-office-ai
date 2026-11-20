import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, type ActivityJob, type Job, type RunResult, type WorkflowOptions } from "./api/client";

const Context = createContext<{
  jobs: ActivityJob[];
  unavailable: boolean;
  refresh: () => Promise<void>;
  track: (label: string, route: string, detail: string) => (status?: "done" | "error", error?: string) => void;
} | null>(null);

export const isActive = (job: Pick<Job, "status">) => job.status === "queued" || job.status === "running";

export const jobRoute = (job: Pick<Job, "route" | "kind">) =>
  job.route ?? (job.kind === "transcribe" ? "/sermon" : null);

export function ActivityProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<ActivityJob[]>([]);
  const [live, setLive] = useState<ActivityJob[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  const active = jobs.some(isActive);
  const refresh = useCallback(async () => {
    try { setJobs(await api.jobs()); setUnavailable(false); }
    catch { setUnavailable(true); }
  }, []);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), active ? 1800 : 5000);
    return () => window.clearInterval(timer);
  }, [active, refresh]);

  const track = useCallback((label: string, route: string, detail: string) => {
    const id = crypto.randomUUID();
    const time = new Date().toISOString();
    const job: ActivityJob = { id, label, route, detail, kind: "chat", progress: 0, status: "running",
      error: null, created_at: time, updated_at: time };
    setLive((existing) => [job, ...existing.filter(isActive), ...existing.filter((item) => !isActive(item)).slice(0, 10)]);
    return (status: "done" | "error" = "done", error?: string) => setLive((existing) => existing.map((item) =>
      item.id === id ? { ...item, status, error: error ?? null, progress: status === "done" ? 1 : 0, updated_at: new Date().toISOString() } : item));
  }, []);

  return <Context.Provider value={{ jobs: [...live, ...jobs], unavailable, refresh, track }}>{children}</Context.Provider>;
}

export function useActivity() {
  const value = useContext(Context);
  if (!value) throw new Error("Activity provider is missing.");
  return value;
}

/** Open an explicit Activity link once. Leaving a mounted page keeps its edits intact. */
export function useJobLink(path: string, open: (job: Job) => void) {
  const location = useLocation();
  const navigate = useNavigate();
  const id = location.pathname === path ? new URLSearchParams(location.search).get("job") : null;
  const lastOpened = useRef<string | null>(null);
  const latest = useRef(open);
  latest.current = open;
  const [loaded, setLoaded] = useState<{ id: string; error?: string }>();

  useEffect(() => {
    if (!id || id === lastOpened.current) return;
    let cancelled = false;
    void api.job(id).then((job) => {
      if (cancelled) return;
      if (jobRoute(job) !== path) throw new Error("This task belongs to another page. Open it from Activity.");
      latest.current(job);
      lastOpened.current = id;
      setLoaded({ id });
    }).catch((error: Error) => {
      if (!cancelled) setLoaded({ id, error: error.message });
    });
    return () => { cancelled = true; };
  }, [id, path, location.key]);

  function remember(jobId: string, startedAt: string) {
    // A slow upload can finish while the user is on a different page.
    if (window.location.pathname + window.location.search !== startedAt) return;
    lastOpened.current = jobId;
    navigate({ pathname: path, search: new URLSearchParams({ job: jobId }).toString() }, { replace: true });
  }

  return {
    remember,
    loading: Boolean(id && id !== lastOpened.current && id !== loaded?.id),
    error: id === loaded?.id ? loaded?.error : undefined,
  };
}

export function useBackgroundDraft(workflow: string) {
  const key = `loa-active-${workflow}`;
  const { refresh } = useActivity();
  const [jobId, setJobId] = useState<string | null>(() => {
    if (new URLSearchParams(window.location.search).has("job")) return null;
    try { return sessionStorage.getItem(key); } catch { return null; }
  });
  const [starting, setStarting] = useState(false);

  async function start(inputs: Record<string, unknown>, options?: WorkflowOptions) {
    setStarting(true);
    try {
      const run = await api.startWorkflow(workflow, inputs, options);
      setJobId(run.job_id);
      try { sessionStorage.setItem(key, run.job_id); } catch { /* the current page still tracks the job */ }
      void refresh();
      return run.job_id;
    } finally { setStarting(false); }
  }

  function finish(job: Job): RunResult {
    setJobId(null);
    try { sessionStorage.removeItem(key); } catch { /* the current page has already reattached */ }
    void refresh();
    if (job.status !== "done" || !job.result || !job.result.outputs) {
      throw new Error(job.error?.split("\n")[0] ?? "The draft could not finish.");
    }
    return job.result as RunResult;
  }

  return { jobId, busy: starting || Boolean(jobId), start, finish, resume: setJobId };
}
