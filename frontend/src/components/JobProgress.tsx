import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Job } from "../api/client";

type Props = { jobId: string; label: string; onDone: (job: Job) => void };

/** Polls a background job and reports it once when finished. */
export default function JobProgress({ jobId, label, onDone }: Props) {
  const [job, setJob] = useState<Job | null>(null);
  const [disconnected, setDisconnected] = useState(false);
  const latest = useRef(onDone);
  latest.current = onDone;

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    setJob(null);
    setDisconnected(false);
    const tick = async () => {
      try {
        const j = await api.job(jobId);
        if (stopped) return;
        setDisconnected(false);
        setJob(j);
        if (j.status === "done" || j.status === "error") {
          latest.current(j);
          return;
        }
      } catch (error) {
        if (stopped) return;
        if (error instanceof ApiError && error.status === 404) {
          const missing: Job = {
            id: jobId, kind: "", status: "error", progress: 0, result: null,
            error: "This background task is no longer available. Start it again to retry.",
          };
          setJob(missing);
          latest.current(missing);
          return;
        }
        setDisconnected(true);
      }
      if (!stopped) timer = window.setTimeout(tick, 1400);
    };
    tick();
    return () => { stopped = true; window.clearTimeout(timer); };
  }, [jobId]);

  if (disconnected) return <p className="muted" role="status">Reconnecting to the local app…</p>;
  if (!job) return <p className="muted" role="status">Starting {label}…</p>;
  if (job.status === "error") return <p className="error">{label} failed: {job.error?.split("\n")[0]}</p>;
  if (job.status === "done") return <p className="muted">{label} finished.</p>;
  const pct = Math.round(job.progress * 100);
  return (
    <div className="progress" role="status">
      <progress aria-label={label} max={100} value={pct || undefined} />
      <span className="small muted">{job.status === "queued" ? "Queued" : job.detail ?? label}{pct > 0 ? ` · ${pct}%` : ""}</span>
    </div>
  );
}
