import { useEffect, useState } from "react";
import { ArrowRight, AudioLines, BookOpen, CircleHelp, Cpu, Mail, Megaphone, Mic, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { api, type TranscriptSummary } from "../api/client";
import chapel from "../assets/chapel.webp";
import { transcriptDate, useWorkspace } from "../workspace";

const tools = [
  { to: "/announcements", title: "Announcements", description: "Turn notes into bulletin, email, and social drafts.", icon: Megaphone, tone: "amber" },
  { to: "/ask", title: "Ask", description: "Think through a question or find answers in office documents.", icon: CircleHelp, tone: "mint" },
  { to: "/letters", title: "Correspondence", description: "Reuse contacts and prepare emails and letters.", icon: Mail, tone: "lavender" },
  { to: "/ask?mode=bible&find=yes", title: "Find a Bible verse", description: "Look up a reference, phrase, or topic in the local Bible.", icon: BookOpen, tone: "blue" },
];

export default function Home() {
  const { appearance, health } = useWorkspace();
  const [recent, setRecent] = useState<TranscriptSummary[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api.transcripts().then(setRecent).catch(() => setError("Could not load recent recordings."));
  }, []);

  return (
    <div className="page home-page">
      <header className="page-heading">
        <h1>{appearance.workspaceName}</h1>
        <p>Turn Sunday’s recording into the materials you’ll use all week.</p>
      </header>

      <section className="workspace-hero">
        <div className="hero-copy">
          <span className="hero-icon"><AudioLines size={24} aria-hidden="true" /></span>
          <h2>Sermon Studio</h2>
          <p>Replay what was said, check scripture, and draft a study guide or bulletin recap.</p>
          <Link className="button hero-button" to="/sermon">Open Sermon Studio <ArrowRight size={18} /></Link>
        </div>
        <img src={chapel} alt="" />
      </section>

      <div className="home-grid">
        <section>
          <h2 className="section-title">Office tools</h2>
          <div className="tool-grid">
            {tools.map(({ to, title, description, icon: Icon, tone }) => (
              <Link className="tile" key={to} to={to}>
                <span className={`tool-icon ${tone}`}><Icon size={20} aria-hidden="true" /></span>
                <span className="tile-copy"><strong>{title}</strong><span>{description}</span></span>
                <ArrowRight className="tile-arrow" size={17} aria-hidden="true" />
              </Link>
            ))}
          </div>
        </section>
        <aside className="home-side">
          <section>
            <div className="section-heading"><h2 className="section-title">Recent recordings</h2><Link to="/sermon?source=saved">View all</Link></div>
            <div className="card recent-card">
              {error && <p className="small muted">{error}</p>}
              {!recent && !error && <p className="small muted">Loading recordings…</p>}
              {recent?.length === 0 && <div className="recent-empty"><Mic size={22} /><p>No recordings yet</p><span>Transcribed recordings appear here.</span></div>}
              {recent?.slice(0, 3).map((item) => (
                <Link className="recent-item" key={item.id} to={`/sermon?transcript=${item.id}`}>
                  <Mic size={18} aria-hidden="true" />
                  <span><strong>{item.title}</strong><small>{transcriptDate(item.created_at)}</small></span>
                  <ArrowRight size={15} aria-hidden="true" />
                </Link>
              ))}
            </div>
          </section>
          <Link className="card system-card" to="/settings">
            <span className="system-icon"><Cpu size={20} aria-hidden="true" /></span>
            <span><strong>Local models</strong><small>{health?.chat_model ?? "Open model settings"}</small></span>
            <ShieldCheck size={19} aria-hidden="true" />
          </Link>
        </aside>
      </div>
    </div>
  );
}
