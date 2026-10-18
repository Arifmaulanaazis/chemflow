import ScientificChart from "./ScientificChart";
import Select from "../components/atoms/Select";
import { lazy, Suspense, useEffect, useState } from "react";
import {
  Download,
  File,
  FolderOpen,
  Search,
  Atom,
  ChartNoAxesCombined,
  Table2,
  RefreshCw,
} from "../components/atoms/Icons";
import { Button, Empty, Notice } from "../components/atoms";
import { api, bytes, fileUrl } from "../lib/api";
import type { Artifact, Preview } from "../lib/types";
const MoleculeViewer = lazy(() => import("./MoleculeViewer"));
const molecular = [".pdb", ".pdbqt", ".sdf", ".mol", ".mol2"];
const images = [".png", ".jpg", ".jpeg", ".webp"];
export default function ArtifactBrowser({ jobId }: { jobId: string }) {
  const [view, setView] = useState("table");
  const [files, setFiles] = useState<Artifact[]>([]),
    [selected, setSelected] = useState<Artifact | null>(null),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all"),
    [error, setError] = useState(""),
    [data, setData] = useState<Preview | null>(null),
    [sheet, setSheet] = useState(""),
    [loading, setLoading] = useState(false);
  useEffect(() => {
    let disposed = false;
    const refresh = () =>
      api<Artifact[]>(`/jobs/${jobId}/artifacts`)
        .then((f) => {
          if (!disposed) {
            setFiles(f);
            setSelected((old) =>
              old ? f.find((x) => x.path === old.path) || null : null,
            );
            setError("");
          }
        })
        .catch((e) => {
          if (!disposed) setError(e.message);
        });
    setSelected(null);
    setFiles([]);
    void refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [jobId]);
  useEffect(() => {
    setSheet("");
  }, [selected?.path]);
  useEffect(() => {
    let disposed = false;
    setData(null);
    if (
      !selected ||
      molecular.includes(selected.extension) ||
      images.includes(selected.extension)
    )
      return;
    setLoading(true);
    api<Preview>(
      `/jobs/${jobId}/preview?path=${encodeURIComponent(selected.path)}${sheet ? "&sheet=" + encodeURIComponent(sheet) : ""}`,
    )
      .then((d) => {
        if (!disposed) {
          setData(d);
          setError("");
        }
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      })
      .finally(() => {
        if (!disposed) setLoading(false);
      });
    return () => {
      disposed = true;
    };
  }, [jobId, selected?.path, selected?.modified, sheet]);
  const shown = files.filter(
    (f) =>
      f.path.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "molecules" && molecular.includes(f.extension)) ||
        (filter === "plots" &&
          [...images, ".svg", ".pdf"].includes(f.extension)) ||
        (filter === "tables" &&
          [".xlsx", ".csv", ".tsv", ".xls"].includes(f.extension))),
  );
  return (
    <section className="panel artifacts-panel">
      <div className="section-heading">
        <div>
          <h2>Hasil & berkas</h2>
          <p className="subtle">
            {files.length} berkas · diperbarui setiap 5 detik · maks. 5.000
            berkas
          </p>
        </div>
        <FolderOpen size={23} aria-hidden="true" />
      </div>
      {error && <Notice>{error}</Notice>}
      <div className="artifact-layout">
        <div className="file-browser">
          <label className="search-field">
            <Search size={16} aria-hidden="true" />
            <input
              aria-label="Cari berkas"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Cari nama berkas…"
            />
          </label>
          <div className="file-filters" aria-label="Jenis berkas">
            {[
              ["all", "Semua"],
              ["molecules", "Molekul"],
              ["plots", "Plot"],
              ["tables", "Tabel"],
            ].map(([value, label]) => (
              <button
                key={value}
                className={filter === value ? "selected" : ""}
                aria-pressed={filter === value}
                onClick={() => setFilter(value)}
              >
                {label}
              </button>
            ))}
          </div>
          <div className="file-list">
            {shown.length === 0 ? (
              <p className="file-empty">
                {files.length
                  ? "Tidak ada berkas yang cocok."
                  : "Berkas akan muncul saat pipeline menghasilkan output."}
              </p>
            ) : (
              shown.map((f) => (
                <button
                  className={`file-row ${selected?.path === f.path ? "selected" : ""}`}
                  key={f.path}
                  onClick={() => {
                    setSelected(f);
                    setError("");
                  }}
                >
                  {molecular.includes(f.extension) ? (
                    <Atom size={18} aria-hidden="true" />
                  ) : images.includes(f.extension) ? (
                    <ChartNoAxesCombined size={18} aria-hidden="true" />
                  ) : [".xlsx", ".csv"].includes(f.extension) ? (
                    <Table2 size={18} aria-hidden="true" />
                  ) : (
                    <File size={18} aria-hidden="true" />
                  )}
                  <span>
                    <strong>{f.path.split("/").pop()}</strong>
                    <small>
                      {f.path.includes("/")
                        ? f.path.slice(0, f.path.lastIndexOf("/")) + " · "
                        : ""}
                      {bytes(f.size)}
                    </small>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
        <div className="artifact-preview">
          {!selected ? (
            <Empty icon={<Atom size={40} />} title="Pilih berkas hasil">
              Pilih struktur untuk preview 3D, plot untuk gambar, atau workbook
              untuk tabel dan interaksi.
            </Empty>
          ) : (
            <>
              <div className="preview-heading">
                <span title={selected.path}>{selected.path}</span>
                <a
                  className="button secondary"
                  href={fileUrl(jobId, selected.path)}
                  download
                >
                  <Download size={16} aria-hidden="true" />
                  Unduh
                </a>
              </div>
              {molecular.includes(selected.extension) ? (
                selected.size > 20 * 1024 ** 2 ? (
                  <p>
                    Struktur melebihi 20 MB. Unduh untuk membuka secara lokal.
                  </p>
                ) : (
                  <Suspense fallback={<p role="status">Memuat viewer 3D…</p>}>
                    <MoleculeViewer jobId={jobId} file={selected} />
                  </Suspense>
                )
              ) : images.includes(selected.extension) ? (
                <img
                  className="plot-preview"
                  src={fileUrl(jobId, selected.path, false)}
                  alt={`Plot ${selected.path}`}
                />
              ) : loading ? (
                <p role="status">Memuat preview…</p>
              ) : data?.kind === "table" ? (
                <>
                  {data.sheets && (
                    <label className="sheet-picker">
                      Worksheet
                      <Select
                        value={sheet || data.sheet}
                        onChange={(e) => setSheet(e.target.value)}
                      >
                        {data.sheets.map((s) => (
                          <option key={s}>{s}</option>
                        ))}
                      </Select>
                    </label>
                  )}
                  <div
                    className="preview-mode"
                    role="group"
                    aria-label="Tampilan data"
                  >
                    <button
                      type="button"
                      aria-pressed={view === "table"}
                      onClick={() => setView("table")}
                    >
                      Tabel
                    </button>
                    <button
                      type="button"
                      aria-pressed={view === "chart"}
                      onClick={() => setView("chart")}
                    >
                      Grafik interaktif
                    </button>
                  </div>
                  {view === "chart" && (
                    <ScientificChart
                      rows={data.rows || []}
                      source={`${selected.path} / ${data.sheet || ""}`}
                    />
                  )}
                  <div
                    hidden={view !== "table"}
                    className="table-scroll"
                    role="region"
                    tabIndex={0}
                    aria-label="Tabel hasil yang dapat digulir"
                  >
                    <table>
                      <caption className="sr-only">Isi {selected.path}</caption>
                      <tbody>
                        {data.rows?.map((row, i) => (
                          <tr key={i}>
                            {row.map((v, k) =>
                              i === 0 ? (
                                <th key={k} scope="col">
                                  {String(v ?? "").trim() || `Kolom ${k + 1}`}
                                </th>
                              ) : (
                                <td key={k}>{String(v ?? "")}</td>
                              ),
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.truncated && (
                    <p className="subtle">
                      Preview dibatasi 200 baris data dan 60 kolom. Unduh untuk
                      data lengkap.
                    </p>
                  )}
                </>
              ) : data?.kind === "text" ? (
                <pre
                  className="text-preview"
                  role="region"
                  tabIndex={0}
                  aria-label="Preview teks yang dapat digulir"
                >
                  {data.text}
                  {data.truncated
                    ? "\n… Preview dipotong. Unduh berkas untuk seluruh isi."
                    : ""}
                </pre>
              ) : (
                <Empty
                  icon={<Download size={30} />}
                  title="Berkas siap diunduh"
                >
                  Format ini dibuka melalui aplikasi lokal. Untuk plot, pilih
                  keluaran PNG pipeline.
                </Empty>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
