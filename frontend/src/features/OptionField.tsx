import { inputExtensions, inputUploads } from "../lib/uploads";
import Select from "../components/atoms/Select";
import { useEffect, useState } from "react";
import { UploadCloud } from "../components/atoms/Icons";
import { api, bytes } from "../lib/api";
import type { Option, Upload } from "../lib/types";
export const labels: Record<string, string> = {
  vina_executable: "Instalasi Vina di server",
  openbabel_path: "Instalasi OpenBabel di server",
  biovia_exe: "Instalasi BIOVIA di server",
  ligands: "Workbook ligan",
  receptors: "Workbook reseptor",
  ligand_name_col: "Kolom nama senyawa",
  ligand_smiles_col: "Kolom SMILES",
  ligand_group_col: "Kolom kelompok ligan",
  receptor_pdb_col: "Kolom kode PDB",
  default_box_size: "Ukuran gridbox bawaan (Å)",
  box_padding: "Ruang tambahan gridbox (Å)",
  no_interactive_gridbox: "Gunakan hanya gridbox dalam workbook",
  force_field: "Metode minimisasi energi",
  minimize_max_iters: "Batas iterasi minimisasi",
  no_2d_image: "Lewati gambar struktur 2D",
  keep_waters: "Pertahankan molekul air",
  keep_hetero_ligands: "Pertahankan ligan HETATM",
  no_keep_metals: "Hapus ion logam",
  kollman_fallback: "Muatan pengganti Kollman",
  vina_version: "Versi AutoDock Vina",
  exhaustiveness: "Kedalaman pencarian",
  num_modes: "Pose per replikat",
  energy_range: "Rentang energi (kcal/mol)",
  seed: "Benih angka acak",
  n_replicates: "Jumlah replikat",
  merge_mode: "Pose yang digabung",
  no_native: "Kecualikan ligan native dari analitik",
  run_rmsd_validation: "Sertakan validasi RMSD",
  rmsd_backend: "Metode RMSD",
  rmsd_overlay: "Visualisasi RMSD dari BIOVIA",
  rmsd_only: "Validasi RMSD saja",
  rmsd_merge_mode: "Pose native untuk merge RMSD",
  rmsd_interaction_mode: "Pose native untuk interaksi RMSD",
  rmsd_threshold_good: "Batas RMSD baik (Å)",
  rmsd_threshold_acceptable: "Batas RMSD diterima (Å)",
  similarity: "Interaksi BIOVIA & similaritas",
  biovia_timeout: "Waktu tunggu BIOVIA (detik)",
  no_lock_input: "Biarkan mouse dan keyboard server aktif",
  no_admet: "Lewati ADMET",
  admet_file: "Hasil ADMET yang sudah tersedia",
  admet_batch_size: "Jumlah senyawa per batch ADMET",
  no_pubchem_fetch: "Lewati pencarian PubChem",
  no_pubchem_interactive_fallback:
    "Lewati senyawa bila pencarian PubChem gagal",
  no_charts: "Lewati grafik batang dan radar",
  no_pca: "Lewati analisis PCA",
  no_hca: "Lewati analisis HCA",
  no_heatmap: "Lewati heatmap",
  dpi: "Resolusi grafik (DPI)",
  figure_formats: "Format ekspor grafik",
  plot_max_rows: "Maksimum baris per grafik",
  plot_max_cols: "Maksimum kolom per heatmap",
  gcms: "Data GC-MS tambahan",
  gcms_groups: "Kelompok sampel GC-MS",
  gcms_library: "Pustaka GC-MS",
  verbose: "Log rinci",
  log_level: "Tingkat pencatatan log",
  format: "Format template ligan",
  skip_check: "Lewati pemeriksaan dependensi",
  rmsd: "Gunakan kompleks validasi RMSD",
  interactions_dir: "Folder interaksi pada run sumber",
  interaction_suffix: "Akhiran nama berkas interaksi",
  receptor: "Filter nama reseptor",
  force: "Ekspor ulang semua hasil",
  result_filename: "Nama workbook hasil",
  no_plots: "Lewati pembuatan grafik",
  data: "Data GC-MS",
  groups: "Tabel kelompok sampel",
  library: "Pustaka senyawa",
  alkanes: "Referensi n-alkana",
  label_by: "Label kelompok pada grafik",
  rt_unit: "Satuan waktu retensi",
  rt_range: "Rentang waktu retensi (awal akhir)",
  no_baseline: "Lewati koreksi baseline",
  smooth_window: "Jendela penghalusan sinyal",
  no_align: "Lewati penyelarasan waktu retensi",
  max_shift: "Pergeseran waktu maksimum",
  min_snr: "Rasio sinyal terhadap derau minimum",
  min_prominence: "Prominensi puncak minimum",
  peak_tolerance: "Toleransi penggabungan puncak",
  min_presence: "Kehadiran fitur minimum",
  feature_mode: "Cara membentuk fitur",
  bin_width: "Lebar bin waktu retensi",
  normalization: "Normalisasi intensitas",
  transform: "Transformasi data",
  scaling: "Penskalaan data",
  permutations: "Jumlah permutasi",
  rt_tolerance: "Toleransi waktu retensi",
  ri_tolerance: "Toleransi indeks retensi",
  top_features: "Jumlah fitur utama",
};
export default function OptionField({
  option: o,
  value,
  onChange,
  uploads,
  onUpload,
  sourceRun,
}: {
  option: Option;
  value: unknown;
  onChange: (v: unknown) => void;
  uploads: Upload[];
  sourceRun?: string;
  onUpload: (f: File) => Promise<Upload>;
}) {
  const [versions, setVersions] = useState<
    { version: string; label: string }[]
  >([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [folders, setFolders] = useState<string[]>([]);
  useEffect(() => {
    if (o.name !== "interactions_dir" || !sourceRun) {
      setFolders([]);
      return;
    }
    let disposed = false;
    api<{ path: string }[]>(`/jobs/${sourceRun}/artifacts`)
      .then((files) => {
        if (!disposed) {
          const dirs = new Set<string>(["."]);
          files.forEach((f) => {
            const parts = f.path.split("/");
            parts.pop();
            while (parts.length) {
              dirs.add(parts.join("/"));
              parts.pop();
            }
          });
          setFolders([...dirs].sort());
        }
      })
      .catch((e) => {
        if (!disposed) setError(e.message);
      });
    return () => {
      disposed = true;
    };
  }, [o.name, sourceRun]);
  const id = `option-${o.name}`;
  const label = labels[o.name] || o.label;
  if (o.kind === "tool")
    return (
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <Select
          id={id}
          value={String(value || "")}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Deteksi otomatis di server</option>
          {o.tool_choices?.map((t) => (
            <option key={t.id} value={t.id}>
              {t.label}
            </option>
          ))}
        </Select>
        <small>{o.help}</small>
        <small>
          Instalasi khusus didaftarkan operator pada server. Berkas unggahan
          tidak dapat dijalankan sebagai program.
        </small>
      </div>
    );
  if (o.name === "interactions_dir")
    return (
      <div className="field">
        <label htmlFor={id}>{label}</label>
        <Select
          id={id}
          value={String(value || "")}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">Folder interaksi bawaan run</option>
          {folders.map((folder) => (
            <option key={folder} value={`run:${sourceRun}:${folder}`}>
              {folder === "." ? "Akar hasil run" : folder}
            </option>
          ))}
        </Select>
        <small>{o.help}</small>
        {error && (
          <small role="alert" className="field-error">
            {error}
          </small>
        )}
      </div>
    );
  if (o.kind === "boolean" && o.name !== "similarity")
    return (
      <label className="check-field">
        <input
          id={id}
          type="checkbox"
          checked={value === true}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>
          {label}
          <small>{o.help}</small>
        </span>
      </label>
    );
  if (o.choices && o.multiple)
    return (
      <fieldset className="choice-field">
        <legend>{label}</legend>
        <p>{o.help}</p>
        <div className="chip-options">
          {o.choices.map((c) => (
            <label key={c}>
              <input
                type="checkbox"
                checked={(Array.isArray(value)
                  ? value
                  : Array.isArray(o.default)
                    ? o.default
                    : []
                ).includes(c)}
                onChange={(e) => {
                  const current = Array.isArray(value)
                    ? value
                    : Array.isArray(o.default)
                      ? o.default
                      : [];
                  onChange(
                    e.target.checked
                      ? [...current, c]
                      : current.filter((x) => x !== c),
                  );
                }}
              />
              {c}
            </label>
          ))}
        </div>
      </fieldset>
    );
  return (
    <div className="field">
      <label htmlFor={id}>
        {label}
        {o.required && <span className="required"> *</span>}
      </label>
      {o.kind === "file" ? (
        <>
          <Select
            id={id}
            value={
              o.multiple
                ? Array.isArray(value)
                  ? value.map(String)
                  : []
                : String(value || "")
            }
            multiple={o.multiple}
            onChange={(e) =>
              onChange(
                o.multiple
                  ? Array.from(e.target.selectedOptions).map((x) => x.value)
                  : e.target.value,
              )
            }
          >
            {!o.multiple && (
              <option value="">Pilih berkas yang diunggah</option>
            )}
            {inputUploads(uploads, o.name, value).map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} ({bytes(f.size)})
              </option>
            ))}
          </Select>
          <label className="upload-control">
            <UploadCloud size={17} aria-hidden="true" />
            {busy ? "Mengunggah…" : "Unggah berkas"}
            <input
              aria-label={`Unggah ${label}`}
              type="file"
              accept={inputExtensions(o.name).map((ext) => `.${ext}`).join(",")}
              disabled={busy}
              multiple={o.multiple}
              onChange={async (e) => {
                const files = Array.from(e.target.files || []);
                setBusy(true);
                setError("");
                try {
                  const uploaded = [];
                  for (const file of files) uploaded.push(await onUpload(file));
                  onChange(
                    o.multiple
                      ? [
                          ...(Array.isArray(value) ? value : []),
                          ...uploaded.map((x) => x.id),
                        ]
                      : uploaded[0]?.id,
                  );
                } catch (err) {
                  setError((err as Error).message);
                } finally {
                  setBusy(false);
                  e.target.value = "";
                }
              }}
            />
          </label>
          {error && (
            <small role="alert" className="field-error">
              {error}
            </small>
          )}
        </>
      ) : o.name === "similarity" ? (
        <Select
          id={id}
          value={value === undefined ? "auto" : String(value)}
          onChange={(e) =>
            onChange(
              e.target.value === "auto" ? undefined : e.target.value === "true",
            )
          }
        >
          <option value="auto">Otomatis bila BIOVIA tersedia</option>
          <option value="true">Aktifkan BIOVIA + similaritas</option>
          <option value="false">Nonaktifkan</option>
        </Select>
      ) : o.choices && !o.multiple ? (
        <Select
          id={id}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">
            Bawaan{o.default != null ? `: ${o.default}` : ""}
          </option>
          {o.choices.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      ) : (
        <input
          id={id}
          type={o.kind === "number" && !o.multiple ? "number" : "text"}
          step={o.kind === "number" ? "any" : undefined}
          value={Array.isArray(value) ? value.join(" ") : String(value ?? "")}
          placeholder={
            o.default != null
              ? String(
                  Array.isArray(o.default) ? o.default.join(" ") : o.default,
                )
              : undefined
          }
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {o.name === "vina_version" && (
        <div className="vina-picker">
          <button
            type="button"
            className="text-button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setError("");
              try {
                setVersions(await api("/vina-versions"));
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Memeriksa versi…" : "Lihat versi Vina yang kompatibel"}
          </button>
          {versions.length > 0 && (
            <Select
              aria-label="Versi Vina kompatibel"
              value={String(value || "")}
              onChange={(e) => onChange(e.target.value)}
            >
              <option value="">Terbaru yang kompatibel</option>
              {versions.map((v) => (
                <option key={v.label} value={v.version}>
                  {v.label}
                </option>
              ))}
            </Select>
          )}
          {error && (
            <small className="field-error" role="alert">
              {error}
            </small>
          )}
        </div>
      )}
      {o.help && <small>{o.help}</small>}
      {o.multiple && o.kind !== "file" && (
        <small>
          Pisahkan nilai dengan spasi
          {o.count ? `; ${o.count} nilai` : ""}.
        </small>
      )}
    </div>
  );
}
