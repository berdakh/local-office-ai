import type { ScriptureCheck } from "../api/client";

const LABEL = { verified: "verified", not_found: "not found", unverified: "unverified" } as const;

export default function ScripturePanel({ refs }: { refs: ScriptureCheck[] }) {
  if (!refs.length) return null;
  return (
    <section className="card">
      <h3>Scripture references</h3>
      {refs.map((r) => (
        <div key={r.ref} className="cite">
          <strong>{r.ref}</strong> <span className={`badge ${r.status}`}>{LABEL[r.status]}</span>
          {r.text && <p className="small">{r.text}</p>}
          {!r.text && r.note && <p className="small muted">{r.note}</p>}
        </div>
      ))}
    </section>
  );
}
