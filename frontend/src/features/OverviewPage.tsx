import MolecularSketch from "../components/molecules/MolecularSketch";
import { useState } from "react";
import {
  Plus,
  Search,
  ChevronRight,
  FlaskConical,
  Atom,
  Clock,
} from "../components/atoms/Icons";
import { Button, Badge, Empty } from "../components/atoms";
import { ResourceStrip } from "../components/molecules/ResourceStrip";
import { active, date } from "../lib/api";
import type { Job, Resources } from "../lib/types";
const commandNames: Record<string, string> = {
  run: "Screening",
  init: "Template input",
  gcms: "GC-MS",
  similarity: "Similaritas",
  interactions: "Interaksi",
  resume: "Lanjutan",
};
export default function OverviewPage({
  route,
  jobs,
  resources,
  navigate,
}: {
  route: string;
  jobs: Job[];
  resources: Resources | null;
  navigate: (to: string) => void;
}) {
  const [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all");
  const running = jobs.filter(active).length;
  const shown = jobs
    .filter(
      (j) =>
        `${j.name} ${j.command}`.toLowerCase().includes(query.toLowerCase()) &&
        (filter === "all" ||
          (filter === "active"
            ? active(j)
            : filter === "attention"
              ? j.pending_input || ["failed", "interrupted"].includes(j.status)
              : j.status === "succeeded")),
    )
    .slice(0, route === "overview" ? 6 : 500);
  return (
    <>
      <div className={`page-heading ${route==="overview"?"overview-heading":""}`}>
        <div>
          <h1>{route === "overview" ? "Ruang kerja" : "Eksperimen Anda"}</h1>
          <p>
            {route === "overview"
              ? "Selamat datang di laboratorium komputasi Anda."
              : "Semua perhitungan dan hasil, tersimpan di satu tempat."}
          </p>
        </div>
        {route !== "overview" && (
          <Button onClick={() => navigate("new")}>
            <Plus size={18} aria-hidden="true" />
            Eksperimen baru
          </Button>
        )}
      </div>
      {route === "overview" && (
        <>
          <section className="discovery-hero">
            <div className="discovery-copy">
              <span className="lab-label">
                <Atom size={18} aria-hidden="true" />
                Molecular workspace
              </span>
              <h2>
                Dari molekul
                <br />
                menuju temuan.
              </h2>
              <p>
                <span className="desktop-copy">Siapkan bahan, rancang perhitungan, dan jelajahi hasil. Kami memandu setiap langkah eksperimen Anda.</span>
                <span className="mobile-copy">Siapkan bahan. Jalankan perhitungan. Jelajahi hasil.</span>
              </p>
              <div className="hero-actions">
                <Button onClick={() => navigate("new")}>
                  <Plus size={18} aria-hidden="true" />
                  Eksperimen baru
                </Button>
                <a
                  href="#guide"
                  onClick={(e) => {
                    e.preventDefault();
                    navigate("guide");
                  }}
                >
                  Pelajari alurnya
                  <ChevronRight size={16} aria-hidden="true" />
                </a>
              </div>
            </div>
            <div className="discovery-visual">
              <MolecularSketch />
            </div>
          </section>
          <ResourceStrip value={resources} />
        </>
      )}
      <section className="panel experiments-panel">
        <div className="section-heading">
          <div>
            <h2>
              {route === "overview"
                ? "Lanjutkan penelusuran Anda"
                : "Semua eksperimen"}
            </h2>
            <p className="subtle">
              {running} aktif ·{" "}
              {jobs.filter((j) => j.status === "succeeded").length} selesai ·{" "}
              {jobs.length} total
            </p>
          </div>
          <label className="search-field">
            <Search size={17} aria-hidden="true" />
            <input
              aria-label="Cari eksperimen"
              placeholder="Cari eksperimen…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        <div className="experiment-filters" aria-label="Filter eksperimen">
          {[
            ["all", "Semua"],
            ["active", "Berjalan"],
            ["attention", "Perlu perhatian"],
            ["done", "Selesai"],
          ].map(([id, label]) => (
            <button
              key={id}
              aria-pressed={filter === id}
              onClick={() => setFilter(id)}
            >
              {label}
              {id === "active" && running > 0 && <span>{running}</span>}
            </button>
          ))}
        </div>
        {jobs.length === 0 ? (
          <Empty
            icon={<FlaskConical size={36} />}
            title="Mulai dengan eksperimen pertama"
            action={
              <Button variant="secondary" onClick={() => navigate("new")}>
                Konfigurasi pipeline
                <ChevronRight size={16} aria-hidden="true" />
              </Button>
            }
          >
            Pilih tujuan, siapkan bahan, lalu ikuti panduan eksperimen.
          </Empty>
        ) : !shown.length ? (
          <Empty
            icon={<Search size={30} />}
            title="Belum ada eksperimen yang cocok"
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setQuery("");
                  setFilter("all");
                }}
              >
                Tampilkan semua
              </Button>
            }
          >
            Coba kata kunci atau filter yang berbeda.
          </Empty>
        ) : (
          <ul className="experiment-list">
            {shown.map((j) => (
              <li key={j.id}>
                <span className={`experiment-symbol ${j.status}`}>
                  <FlaskConical size={21} aria-hidden="true" />
                </span>
                <a
                  className="experiment-title"
                  href={`#run/${j.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(`run/${j.id}`);
                  }}
                >
                  <strong>{j.name}</strong>
                  <small>
                    {j.pending_input
                      ? "Menunggu jawaban Anda"
                      : j.stage || commandNames[j.command] || j.command}
                  </small>
                </a>
                <span className="experiment-kind">
                  {commandNames[j.command] || j.command}
                </span>
                <span className="experiment-state">
                  {j.pending_input ? (
                    <span className="input-needed">Perlu input</span>
                  ) : (
                    <Badge status={j.status} />
                  )}
                </span>
                <span className="experiment-date">
                  <Clock size={14} aria-hidden="true" />
                  {date(j.created)}
                </span>
                <a
                  className="row-open"
                  aria-label={`Buka ${j.name}`}
                  href={`#run/${j.id}`}
                >
                  <ChevronRight size={18} aria-hidden="true" />
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
