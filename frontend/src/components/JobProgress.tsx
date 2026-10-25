import { useEffect, useState } from "react";
import { api, type Job } from "../api/client";

type Props = { jobId: string; label: string; onDone: (job: Job) => void };

/** Polls a background job and reports it once when finished. */
export default function JobProgress({ jobId, label, onDone }: Props) {
  const [job, setJob] = useState<Job | null>(null);

  useEffect(() => {
    let stopped = false;
    const tick = async () => {
      try {
        const j = await api.job(jobId);
        if (stopped) return;
        setJob(j);
        if (j.status === "done" || j.status === "error") {
          onDone(j);
          return;
        }
      } catch {
        /* keep polling */
      }
      if (!stopped) setTimeout(tick, 1500);
    };
    tick();
    return () => { stopped = true; };
  }, [jobId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!job) return <p className="muted">Starting {label}...</p>;
  if (job.status === "error") return <p className="error">{label} failed: {job.error?.split("\n")[0]}</p>;
  if (job.status === "done") return <p className="muted">{label} finished.</p>;
  const pct = Math.round(job.progress * 100);
  return (
    <div className="progress">
      <div className="bar"><div style={{ width: `${pct}%` }} /></div>
      <span className="small muted">{label}: {pct}%</span>
    </div>
  );
}
