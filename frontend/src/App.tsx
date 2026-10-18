import LibraryPage from "./features/LibraryPage";
import { motion } from "motion/react";
import BrandMark from "./components/atoms/BrandMark";
import { useEffect, useState } from "react";
import {
  Activity,
  BookOpen,
  ChevronRight,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Settings,
  ShieldCheck,
  Workflow,
} from "./components/atoms/Icons";
import { Notice } from "./components/atoms";
import BottomNav from "./components/molecules/BottomNav";
import { api, setCsrf, active } from "./lib/api";
import { useLive } from "./lib/useLive";
import type { Schema, Update } from "./lib/types";
import JobComposer from "./features/JobComposer";
import RunWorkspace from "./features/RunWorkspace";
import Login from "./features/Login";
import OverviewPage from "./features/OverviewPage";
import ResourcePage from "./features/ResourcePage";
import GuidePage from "./features/GuidePage";
import SettingsPage from "./features/SettingsPage";
function Workspace({ onLogout }: { onLogout: () => void }) {
  const { jobs, resources, connected, error: liveError } = useLive();
  const [schema, setSchema] = useState<Schema | null>(null),
    [updates, setUpdates] = useState<Update | null>(null),
    [route, setRoute] = useState(location.hash.slice(1) || "overview"),
    [error, setError] = useState("");
  const navigate = (to: string) => {
    location.hash = to;
    setRoute(to);
    window.scrollTo({ top: 0 });
  };
  useEffect(() => {
    const sync = () => setRoute(location.hash.slice(1) || "overview");
    window.addEventListener("hashchange", sync);
    api<Schema>("/schema")
      .then(setSchema)
      .catch((e) => setError(e.message));
    const refreshUpdates = () =>
      api<Update>("/updates")
        .then(setUpdates)
        .catch((e) => setError(e.message));
    void refreshUpdates();
    const updateTimer = window.setInterval(refreshUpdates, 60000);
    return () => {
      window.removeEventListener("hashchange", sync);
      window.clearInterval(updateTimer);
    };
  }, []);
  const logout = async () => {
    try {
      await api("/logout", { method: "POST" });
      setCsrf("");
      onLogout();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const job = jobs.find((j) => route === `run/${j.id}`);
  const running = jobs.filter(active).length;
  const nav = [
    { id: "overview", label: "Ruang kerja", icon: LayoutDashboard },
    { id: "experiments", label: "Eksperimen", icon: Workflow },
    { id: "resources", label: "Mesin & sumber daya", icon: Activity },
    { id: "guide", label: "Panduan", icon: BookOpen },
    { id: "library", label: "Materi & sitasi", icon: BookOpen },
    { id: "settings", label: "Akses & pembaruan", icon: Settings },
  ];
  return (
    <div className="app-shell">
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          document.getElementById("main-content")?.focus();
        }}
      >
        Lewati navigasi
      </a>
      <aside className="sidebar" aria-label="Menu ruang kerja">
        <a
          className="brand"
          href="#overview"
          onClick={(e) => {
            e.preventDefault();
            navigate("overview");
          }}
        >
          <BrandMark />
          chemflow<span>3.0</span>
        </a>
        <div className="workspace-label">Molecular workspace</div>
        <nav aria-label="Navigasi utama">
          {nav.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              className={
                route === n.id ||
                (n.id === "experiments" && route.startsWith("run/"))
                  ? "current"
                  : ""
              }
              aria-current={route === n.id ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                navigate(n.id);
              }}
            >
              <n.icon size={19} aria-hidden="true" />
              {n.label}
              {n.id === "experiments" && running > 0 && (
                <span className="nav-count">{running}</span>
              )}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="server-status">
            <span
              className={`connection-dot ${connected ? "live" : ""}`}
              aria-hidden="true"
            />
            <span>
              {connected ? "Server terhubung" : "Server menyambungkan"}
            </span>
          </div>
          <small>
            {resources?.platform || "Server"} · workspace terautentikasi
          </small>
          <button onClick={logout}>
            <LogOut size={17} aria-hidden="true" />
            Keluar
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <a
            className="mobile-brand"
            href="#overview"
            onClick={(e) => {
              e.preventDefault();
              navigate("overview");
            }}
          >
            <BrandMark />
            chemflow
          </a>
          <span>
            <span className="subtle">ChemFlow</span>
            <ChevronRight size={15} aria-hidden="true" />
            {route.startsWith("run/")
              ? "Eksperimen"
              : route.startsWith("new")
                ? "Eksperimen baru"
                : nav.find((n) => n.id === route)?.label || "Ruang kerja"}
          </span>
          <span className="topbar-status">
            <span
              className={`connection-dot ${connected ? "live" : ""}`}
              aria-hidden="true"
            />
            <span className="connection-label">
              {connected ? "Pemantauan langsung" : "Menyambungkan ulang"}
            </span>
            <ShieldCheck size={16} aria-hidden="true" />
            <span className="security-label">Sesi aman</span>
          </span>
        </header>
        <motion.main
          key={route}
          initial={{ opacity: 0, y: 7 }}
          animate={{ opacity: 1, y: 0 }}
          id="main-content"
          tabIndex={-1}
        >
          {(error || liveError) && <Notice>{error || liveError}</Notice>}
          {route.startsWith("new") ? (
            schema ? (
              <JobComposer
                key={route}
                preset={
                  route.startsWith("new/resume/")
                    ? { command: "resume", source: route.split("/")[2] }
                    : undefined
                }
                schema={schema}
                jobs={jobs}
                onBack={() => navigate("overview")}
                onCreated={(id) => navigate(`run/${id}`)}
              />
            ) : (
              <p role="status">Memuat pengaturan pipeline…</p>
            )
          ) : route.startsWith("run/") ? (
            job ? (
              <RunWorkspace
                job={job}
                onBack={() => navigate("experiments")}
                onResume={(id) => navigate(`new/resume/${id}`)}
              />
            ) : (
              <p role="status">
                Mencari eksperimen. Jika run tidak ditemukan,{" "}
                <a href="#experiments">kembali ke daftar</a>.
              </p>
            )
          ) : route === "overview" || route === "experiments" ? (
            <OverviewPage
              route={route}
              jobs={jobs}
              resources={resources}
              navigate={navigate}
            />
          ) : route === "resources" ? (
            <ResourcePage resources={resources} running={running} />
          ) : route === "library" ? (
            <LibraryPage />
          ) : route === "guide" ? (
            <GuidePage />
          ) : (
            <SettingsPage schema={schema} updates={updates} />
          )}
        </motion.main>
        <footer className="app-footer">
          <span>ChemFlow 3.0.0</span>
          <span>Preparasi · Docking · Kemometrik</span>
          <a
            href="#library"
            onClick={(e) => {
              e.preventDefault();
              navigate("library");
            }}
          >
            Materi & sitasi
          </a>
        </footer>
      </div>
      <BottomNav
        route={route}
        navigate={navigate}
        onLogout={logout}
        connected={connected}
      />
    </div>
  );
}
export default function App() {
  const [authenticated, setAuthenticated] = useState<boolean | null>(null);
  useEffect(() => {
    api<{ csrf: string }>("/session")
      .then((s) => {
        setCsrf(s.csrf);
        setAuthenticated(true);
      })
      .catch(() => setAuthenticated(false));
    const expired = () => {
      setCsrf("");
      setAuthenticated(false);
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  return authenticated === null ? (
    <main className="loading-page" role="status">
      Menghubungkan ke ChemFlow…
    </main>
  ) : authenticated ? (
    <Workspace onLogout={() => setAuthenticated(false)} />
  ) : (
    <Login onLogin={() => setAuthenticated(true)} />
  );
}
