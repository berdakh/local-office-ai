import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { AudioLines, BookOpen, ChevronRight, CircleHelp, Cpu, Database, House, Mail, Megaphone, Settings2, ShieldCheck } from "lucide-react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { api, type Health } from "./api/client";
import Home from "./pages/Home";
import SermonStudio from "./pages/SermonStudio";
import Announcements from "./pages/Announcements";
import Ask from "./pages/Ask";
import Letters from "./pages/Letters";
import Library from "./pages/Library";
import Settings from "./pages/Settings";
import Generated from "./pages/Generated";
import ActivityPanel from "./components/ActivityPanel";
import { ActivityProvider } from "./activity";
import { readAppearance, Workspace } from "./workspace";

const Workbench = lazy(() => import("./pages/Workbench"));

const nav = [
  { to: "/", label: "Overview", icon: House },
  { to: "/sermon", label: "Sermon Studio", icon: AudioLines },
  { to: "/announcements", label: "Announcements", icon: Megaphone },
  { to: "/ask", label: "Ask", icon: CircleHelp },
  { to: "/letters", label: "Correspondence", icon: Mail },
  { to: "/library", label: "Library", icon: BookOpen },
  { to: "/generated", label: "Generated Texts", icon: Database },
  { to: "/settings", label: "Settings", icon: Settings2 },
];

const retained: Record<string, React.ComponentType> = {
  "/sermon": SermonStudio, "/announcements": Announcements, "/ask": Ask, "/letters": Letters,
  "/library": Library, "/settings": Settings,
  "/generated": Generated,
};

export default function App() {
  const [appearance, setAppearance] = useState(readAppearance);
  const [health, setHealth] = useState<Health | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [modelError, setModelError] = useState("");
  const location = useLocation();
  const active = nav.find(({ to }) => to === location.pathname);
  const [visited, setVisited] = useState<string[]>([]);
  const retain = Object.prototype.hasOwnProperty.call(retained, location.pathname);
  if (retain && !visited.includes(location.pathname)) setVisited([...visited, location.pathname]);
  const refresh = useCallback(async () => {
    try {
      const [nextHealth, nextModels] = await Promise.all([api.health(), api.models()]);
      setHealth(nextHealth);
      setModels(nextModels);
      setModelError("");
    } catch (error) {
      setModelError((error as Error).message);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    document.documentElement.dataset.theme = appearance.theme;
    document.documentElement.dataset.accent = appearance.accent;
    document.documentElement.dataset.density = appearance.density;
    localStorage.setItem("loa-appearance", JSON.stringify(appearance));
  }, [appearance]);

  return (
    <Workspace.Provider value={{ appearance, setAppearance, health, models, modelError, refresh }}>
      <ActivityProvider>
      <div className="shell">
        <aside className="sidebar">
          <Link className="brand" to="/">
            <span className="brand-icon"><AudioLines size={23} /></span>
            <span><strong>Local Office AI</strong><small>{appearance.workspaceName}</small></span>
          </Link>
          <nav aria-label="Workspace">
            {nav.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={to} end={to === "/"} className={to === "/library" ? "nav-section" : undefined}>
                <Icon size={18} strokeWidth={1.8} aria-hidden="true" /> <span>{label}</span>
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-footer">
            <ShieldCheck size={18} aria-hidden="true" />
            <div><strong>On-device workspace</strong><small>{health?.ollama.available ? "Ollama connected" : health ? "Ollama unavailable" : "Checking Ollama…"}</small></div>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <div className="breadcrumb"><span>Workspace</span><ChevronRight size={14} aria-hidden="true" /><strong>{active?.label ?? (location.pathname === "/settings/workbench" ? "Workbench" : "Page")}</strong></div>
            <div className="topbar-tools"><ActivityPanel />
            <Link className="model-pill" to="/settings" title="Change the default drafting model">
              <Cpu size={15} aria-hidden="true" /><span>{health?.chat_model ?? "Model settings"}</span>
              <span className={health?.chat_model_installed ? "status-dot online" : "status-dot"} aria-hidden="true" />
            </Link>
            </div>
          </header>
          <main className="content" id="main-content">
            {visited.map((path) => {
              const Page = retained[path];
              return <div key={path} className="retained-page" hidden={location.pathname !== path}><Page /></div>;
            })}
            {!retain && <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/settings/workbench" element={<Suspense fallback={<p role="status">Opening the Python editor…</p>}><Workbench /></Suspense>} />
              <Route path="*" element={<Home />} />
            </Routes>}
          </main>
        </div>
      </div>
      </ActivityProvider>
    </Workspace.Provider>
  );
}
