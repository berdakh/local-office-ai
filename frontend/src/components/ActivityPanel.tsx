import { Activity, Check, CircleAlert, Clock } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { isActive, jobRoute, useActivity } from "../activity";
import type { ActivityJob } from "../api/client";
import { transcriptDate } from "../workspace";

const names: Record<string, string> = { transcribe: "Transcription", embed: "Library indexing", model_download: "Model download", workflow: "Draft generation" };

function details(job: ActivityJob) {
  if (job.status === "done") return "Complete";
  if (job.status === "error") return job.error?.split("\n")[0] ?? "Could not finish";
  return job.status === "queued" ? "Queued" : job.detail ?? "Working";
}

export default function ActivityPanel() {
  const { jobs, unavailable, refresh } = useActivity();
  const panel = useRef<HTMLDetailsElement>(null);
  const location = useLocation();
  useEffect(() => { if (panel.current) panel.current.open = false; }, [location.key]);
  const active = jobs.filter(isActive);
  const recent = [...active, ...jobs.filter((job) => !isActive(job)).sort((a, b) =>
    b.updated_at.replace(" ", "T").localeCompare(a.updated_at.replace(" ", "T")))].slice(0, 12);
  return (
    <details className="activity-menu" ref={panel} onKeyDown={(event) => {
      if (event.key === "Escape" && panel.current?.open) {
        panel.current.open = false;
        panel.current.querySelector("summary")?.focus();
      }
    }} onToggle={(event) => { if (event.currentTarget.open) void refresh(); }}>
      <summary title={active.length ? `${active.length} tasks in progress` : "Recent activity"}>
        <Activity size={17} aria-hidden="true" /> <span>Activity</span>
        {!!active.length && <span className="activity-count" aria-label={`${active.length} active tasks`}>{active.length}</span>}
      </summary>
      <section className="activity-popover" aria-label="Recent activity">
        <header><h2>Activity</h2><small>{active.length ? `${active.length} in progress` : "No work in progress"}</small></header>
        {unavailable && <p className="small muted">Waiting to reconnect to the local app…</p>}
        {!recent.length && <p className="small muted">Drafts, transcription, and downloads appear here as they run.</p>}
        <ul>{recent.map((job) => {
          const running = isActive(job);
          const pct = Math.round(job.progress * 100);
          const route = jobRoute(job);
          const exact = job.kind === "transcribe" || job.kind === "workflow";
          const href = exact && route ? `${route}?job=${encodeURIComponent(job.id)}` : route;
          const Indicator = job.status === "done" ? Check : job.status === "error" ? CircleAlert : Clock;
          return <li key={job.id}>
            <Indicator size={16} aria-hidden="true" />
            <div>
              <strong>{job.label ?? names[job.kind] ?? "Background work"}</strong>
              <p>{details(job)}{running && pct > 0 ? ` · ${pct}%` : ` · ${transcriptDate(job.updated_at)}`}</p>
              {running && <progress aria-label={job.label ?? "Task progress"} max={100} value={pct || undefined} />}
            </div>
            {href && <Link to={href} onClick={() => { if (panel.current) panel.current.open = false; }}>
              {job.kind === "transcribe" ? "Open recording" : job.kind === "workflow" && route !== "/generated" ? "Open draft" : "Open"}
            </Link>}
          </li>;
        })}</ul>
        <Link className="activity-footer" to="/generated" onClick={() => { if (panel.current) panel.current.open = false; }}>Open Generated Texts</Link>
      </section>
    </details>
  );
}
