import { useEffect, useState } from "react";
import {
  Terminal,
  Square,
  Clock,
  ArrowLeft,
  RefreshCw,
} from "../components/atoms/Icons";
import { Button, Badge, Notice } from "../components/atoms";
import { api, active, date } from "../lib/api";
import type { Job } from "../lib/types";
import ArtifactBrowser from "./ArtifactBrowser";
import InputRequests from "./InputRequests";
export default function RunWorkspace({
  job,
  onBack,
  onResume,
}: {
  job: Job;
  onBack: () => void;
  onResume: (id: string) => void;
}) {
  const [tab, setTab] = useState("results");
  const [logs, setLogs] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [confirm, setConfirm] = useState(false),
    [follow, setFollow] = useState(true);
  useEffect(() => {
    let disposed = false;
    const refresh = () =>
      api<{ text: string }>(`/jobs/${job.id}/logs`)
        .then((d) => {
          if (!disposed) setLogs(d.text);
        })
        .catch((e) => {
          if (!disposed) setError(e.message);
        });
    setLogs("");
    void refresh();
    const timer = setInterval(refresh, 2000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [job.id]);
  useEffect(() => {
    if (follow) {
      const el = document.getElementById("run-log");
      if (el) el.scrollTop = el.scrollHeight;
    }
  }, [logs, follow]);
  return (
    <>
      <button className="text-button" onClick={onBack}>
        <ArrowLeft size={16} aria-hidden="true" />
        Semua eksperimen
      </button>
      <div className="page-heading">
        <div>
          <div className="title-line">
            <h1>{job.name}</h1>
            <Badge status={job.status} />
          </div>
          <p>
            {job.command} · {date(job.created)} ·{" "}
            {job.stage || "Tahap belum tersedia"}
          </p>
        </div>
        {active(job) ? (
          <Button variant="danger" onClick={() => setConfirm(true)}>
            <Square size={15} aria-hidden="true" />
            Hentikan
          </Button>
        ) : job.command === "run" || job.command === "resume" ? (
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => onResume(job.id)}
          >
            <RefreshCw size={16} aria-hidden="true" />
            Lanjutkan checkpoint
          </Button>
        ) : null}
      </div>
      {error && <Notice>{error}</Notice>}
      {confirm && (
        <div className="confirm-stop" role="alert">
          <span>
            Hentikan job ini? Hasil yang sudah ditulis tetap tersimpan. Pose
            yang sedang dihitung perlu dijalankan ulang.
          </span>
          <Button variant="secondary" onClick={() => setConfirm(false)}>
            Kembali
          </Button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await api(`/jobs/${job.id}/cancel`, {
                  method: "POST",
                });
                setConfirm(false);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            Ya, hentikan
          </Button>
        </div>
      )}
      <div className="run-meta">
        <span>
          <Clock size={16} aria-hidden="true" />
          {job.started ? "Mulai " + date(job.started) : "Menunggu giliran"}
        </span>
        <span>
          {job.exit_code !== null
            ? `Exit code ${job.exit_code}`
            : "Output tersimpan otomatis"}
        </span>
        <code>{job.id.slice(0, 12)}</code>
      </div>
      <InputRequests jobId={job.id} running={job.status === "running"} />
      <div className="run-progress" aria-live="polite">
        <Clock size={25} aria-hidden="true" />
        <div>
          <strong>
            {job.pending_input
              ? "Menunggu input dari Anda"
              : job.status === "succeeded"
                ? "Perhitungan selesai"
                : job.status === "running"
                  ? "Eksperimen sedang diproses"
                  : job.status === "queued"
                    ? "Eksperimen dalam antrean"
                    : "Proses berhenti"}
          </strong>
          <p>
            {job.stage ||
              "Berkas dan aktivitas akan diperbarui selama proses berjalan."}
          </p>
          {(active(job) || job.status === "succeeded") && (
            <div className={`run-progress-track ${job.status} ${job.pending_input ? "waiting" : ""}`}
              role="progressbar" aria-label="Progres eksperimen" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={job.status === "succeeded" ? 100 : undefined}
              aria-valuetext={job.pending_input ? "Menunggu input" : job.status === "queued" ? "Dalam antrean" : job.status === "succeeded" ? "Selesai" : job.stage || "Sedang diproses"}>
              <span />
            </div>
          )}
        </div>
      </div>
      <div className="run-tabs" role="tablist" aria-label="Tampilan eksperimen">
        <button
          id="results-tab"
          role="tab"
          aria-selected={tab === "results"}
          aria-controls="results-panel"
          tabIndex={tab === "results" ? 0 : -1}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
              setTab("activity");
              document.getElementById("activity-tab")?.focus();
            }
          }}
          onClick={() => setTab("results")}
        >
          Hasil & berkas
        </button>
        <button
          id="activity-tab"
          role="tab"
          aria-selected={tab === "activity"}
          aria-controls="activity-panel"
          tabIndex={tab === "activity" ? 0 : -1}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
              setTab("results");
              document.getElementById("results-tab")?.focus();
            }
          }}
          onClick={() => setTab("activity")}
        >
          Aktivitas & log
        </button>
      </div>
      <div
        id="results-panel"
        role="tabpanel"
        aria-labelledby="results-tab"
        hidden={tab !== "results"}
      >
        <ArtifactBrowser jobId={job.id} />
      </div>
      <div
        id="activity-panel"
        role="tabpanel"
        aria-labelledby="activity-tab"
        hidden={tab !== "activity"}
      >
        <section className="panel log-panel">
          <div className="section-heading">
            <h2>
              <Terminal size={19} aria-hidden="true" />
              Log pipeline
            </h2>
            <label>
              <input
                type="checkbox"
                checked={follow}
                onChange={(e) => setFollow(e.target.checked)}
              />
              Ikuti log
            </label>
          </div>
          <pre
            id="run-log"
            role="region"
            tabIndex={0}
            aria-label="Log pipeline"
          >
            {logs || "Menunggu output proses…"}
          </pre>
          <small className="subtle">
            Diperbarui setiap 2 detik · 64 KB terakhir · status selesai tidak
            menjamin semua pasangan docking berhasil; tinjau log dan tabel
            hasil.
          </small>
        </section>
      </div>
    </>
  );
}
