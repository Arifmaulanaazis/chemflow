import Disclosure from "../components/atoms/Disclosure";
import { motion } from "motion/react";
import Select from "../components/atoms/Select";
import { useEffect, useRef, useState } from "react";
import {
  Play,
  ChevronRight,
  ArrowLeft,
  Table2,
} from "../components/atoms/Icons";
import { Button, Notice } from "../components/atoms";
import { api } from "../lib/api";
import type { Job, Option, Schema, Upload } from "../lib/types";
import OptionField, { labels } from "./OptionField";
import ReceptorBuilder from "./ReceptorBuilder";
import LigandBuilder from "./LigandBuilder";
import { workflows, stepNames, copy, notes } from "../lib/workflows";
import WizardSteps from "../components/molecules/WizardSteps";
import ParameterPanel from "./ParameterPanel";
import ExperimentReview from "./ExperimentReview";
const draftKey = "chemflow-wizard-v2";
function readDraft() {
  try {
    return JSON.parse(sessionStorage.getItem(draftKey) || "null") || {};
  } catch {
    return {};
  }
}
export default function JobComposer({
  schema,
  jobs,
  preset,
  onCreated,
  onBack,
}: {
  schema: Schema;
  preset?: { command: string; source: string };
  jobs: Job[];
  onCreated: (id: string) => void;
  onBack: () => void;
}) {
  const [draft] = useState(readDraft);
  const [command, setCommand] = useState<string>(
      preset?.command ||
        (schema.commands[draft.command] ? draft.command : "run"),
    ),
    [name, setName] = useState<string>(
      preset
        ? `Lanjutan ${jobs.find((j) => j.id === preset.source)?.name || "run"}`.slice(
            0,
            120,
          )
        : draft.name || "",
    ),
    [source, setSource] = useState<string>(
      preset?.source || draft.source || "",
    ),
    [options, setOptions] = useState<Record<string, unknown>>(
      preset ? {} : draft.options || {},
    ),
    [uploads, setUploads] = useState<Upload[]>([]),
    [step, setStep] = useState(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [pendingOperations, setPendingOperations] = useState(0);
  const [maxStep, setMaxStep] = useState(0);
  const errorBox = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error) {
      errorBox.current?.focus({ preventScroll: true });
      errorBox.current?.scrollIntoView({ block: "center" });
    }
  }, [error]);
  const inputBusy = (value: boolean) =>
    setPendingOperations((n) => Math.max(0, n + (value ? 1 : -1)));
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    api<Upload[]>("/uploads")
      .then(setUploads)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    try {
      sessionStorage.setItem(
        draftKey,
        JSON.stringify({ command, name, source, options }),
      );
    } catch {
      /* Mode privasi browser dapat menonaktifkan penyimpanan. */
    }
  }, [command, name, source, options]);
  const opts = schema.commands[command] || [],
    files = opts.filter((o) => o.kind === "file"),
    settings = opts.filter((o) => o.kind !== "file");
  const current = workflows.find((w) => w.id === command)!;
  const sourceNeeded = [
    "resume",
    "similarity",
    "interactions",
    "gcms",
  ].includes(command);
  const normalized = () =>
    Object.fromEntries(
      Object.entries(options).map(([key, value]) => {
        const o = opts.find((x) => x.name === key);
        return [
          key,
          o?.multiple && o.kind !== "file" && typeof value === "string"
            ? value.trim().split(/\s+/).filter(Boolean)
            : value,
        ];
      }),
    );
  const upload = async (file: File, purpose: string) => {
    if (file.size > schema.max_upload_mb * 1024 ** 2)
      throw Error(`Maksimum ${schema.max_upload_mb} MB per berkas.`);
    setPendingOperations((n) => n + 1);
    try {
      const saved = await api<Upload>(
        `/uploads?filename=${encodeURIComponent(file.name)}&purpose=${encodeURIComponent(purpose)}`,
        { method: "POST", body: file },
      );
      setUploads((v) => [...v.filter((u) => u.id !== saved.id), saved]);
      return saved;
    } finally {
      setPendingOperations((n) => n - 1);
    }
  };
  const saved = (key: string) => (u: Upload) => {
    setUploads((v) => [...v.filter((file) => file.id !== u.id), { ...u, purpose: key }]);
    setOptions((v) => ({ ...v, [key]: u.id }));
    setError("");
  };
  const field = (o: Option) => (
    <OptionField
      key={o.name}
      option={o}
      value={options[o.name]}
      onChange={(v) => setOptions((old) => ({ ...old, [o.name]: v }))}
      uploads={uploads}
      sourceRun={source}
      onUpload={(file) => upload(file, o.name)}
    />
  );
  const validate = () => {
    if (step === 1) {
      if (sourceNeeded && command !== "gcms" && !source)
        return "Pilih run sumber untuk melanjutkan.";
      if (command === "run" && !options.receptors)
        return "Pilih atau buat workbook reseptor terlebih dahulu.";
      if (command === "run" && !options.rmsd_only && !options.ligands)
        return "Pilih atau tulis ligan terlebih dahulu. Untuk redocking native saja, aktifkan Validasi RMSD saja.";
      if (
        command === "gcms" &&
        !source &&
        !(Array.isArray(options.data) && options.data.length)
      )
        return "Unggah data GC-MS atau pilih run sumber.";
      for (const o of files)
        if (o.required && !options[o.name])
          return `Lengkapi ${labels[o.name] || o.label}.`;
    }
    if (step === 2) {
      for (const o of settings) {
        const value = normalized()[o.name];
        if (value == null || value === "") continue;
        const values = Array.isArray(value) ? value : [value];
        if (o.count && values.length !== o.count)
          return `${labels[o.name] || o.label}: isi ${o.count} nilai.`;
        if (
          o.kind === "number" &&
          values.some((v) => !Number.isFinite(Number(v)))
        )
          return `${labels[o.name] || o.label}: gunakan angka yang valid.`;
      }
    }
    return "";
  };
  const move = (next: number) => {
    if (next > step) {
      const message = validate();
      if (message) {
        setError(message);
        return;
      }
    }
    setError("");
    setStep(next);
    setMaxStep((old) => Math.max(old, next));
    window.scrollTo({ top: 0 });
    requestAnimationFrame(() => heading.current?.focus());
  };
  const display = (o: Option) => {
    const value = options[o.name];
    if (o.kind === "tool")
      return (
        o.tool_choices?.find((t) => t.id === value)?.label || "Deteksi otomatis"
      );
    if (o.kind === "file") {
      const ids = Array.isArray(value) ? value : [value];
      return ids
        .map(
          (id) =>
            uploads.find((u) => u.id === id)?.name ||
            String(id || "Belum dipilih"),
        )
        .join(", ");
    }
    if (value === true) return "Aktif";
    if (value === false) return "Nonaktif";
    return Array.isArray(value)
      ? value.join(", ")
      : String(value ?? o.default ?? "Otomatis");
  };
  const changes = opts.filter(
    (o) =>
      options[o.name] !== undefined &&
      options[o.name] !== "" &&
      (!Array.isArray(options[o.name]) ||
        (options[o.name] as unknown[]).length),
  );
  return (
    <div className="composer">
      <button className="text-button" onClick={onBack}>
        <ArrowLeft size={16} aria-hidden="true" />
        Ruang kerja
      </button>
      <div className="page-heading">
        <div>
          <h1>Eksperimen baru</h1>
          <p>Pilih alur, siapkan input, lalu atur parameter.</p>
        </div>
        <span className="draft-label">Draf tersimpan di tab ini</span>
      </div>
      <div className="wizard-layout">
        <WizardSteps step={step} maxStep={maxStep} move={move} />

        <form
          className="wizard-body"
          onSubmit={async (e) => {
            e.preventDefault();
            if (step < 3) {
              move(step + 1);
              return;
            }
            setBusy(true);
            setError("");
            try {
              const result = await api<{ id: string }>("/jobs", {
                method: "POST",
                body: JSON.stringify({
                  command,
                  name,
                  source_run: source || null,
                  options: normalized(),
                }),
              });
              sessionStorage.removeItem(draftKey);
              onCreated(result.id);
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          <motion.section
            key={step}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            className="wizard-surface"
            aria-labelledby="wizard-heading"
          >
            <div className="step-caption">
              Langkah {step + 1} dari 4<span>{current.name}</span>
            </div>
            <h2 id="wizard-heading" tabIndex={-1} ref={heading}>
              {copy[step]}
            </h2>
            <p className="step-description">{notes[step]}</p>
            {error && (
              <div ref={errorBox} tabIndex={-1}>
                <Notice>{error}</Notice>
              </div>
            )}
            {step === 0 && (
              <>
                <div className="workflow-options">
                  {workflows.map((w) => (
                    <button
                      type="button"
                      key={w.id}
                      disabled={w.id === "interactions" && !schema.biovia}
                      aria-pressed={command === w.id}
                      className={`workflow-choice ${command === w.id ? "chosen" : ""}`}
                      onClick={() => {
                        if (w.id !== command) {
                          setCommand(w.id);
                          setMaxStep(0);
                          setOptions({});
                          setSource("");
                          setError("");
                        }
                      }}
                    >
                      <w.icon size={24} aria-hidden="true" />
                      <span>
                        <strong>{w.name}</strong>
                        <small>{w.detail}</small>
                        {w.id === "interactions" && !schema.biovia && (
                          <small>Memerlukan server Windows</small>
                        )}
                      </span>
                      <span className="choice-radio" aria-hidden="true" />
                    </button>
                  ))}
                </div>
                <div className="field experiment-name">
                  <label htmlFor="run-name">Nama eksperimen</label>
                  <input
                    id="run-name"
                    maxLength={120}
                    placeholder="Contoh: Skrining inhibitor protease"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                  />
                  <small>Opsional. Nama alur dipakai bila dikosongkan.</small>
                </div>
              </>
            )}
            {step === 1 && (
              <>
                <div className="form-grid">
                  {sourceNeeded && (
                    <div className="field wide-field">
                      <label htmlFor="source-run">
                        Run sumber {command === "gcms" ? "(opsional)" : "*"}
                      </label>
                      <Select
                        id="source-run"
                        value={source}
                        onChange={(e) => {
                          setSource(e.target.value);
                          setOptions((old) => ({
                            ...old,
                            interactions_dir: undefined,
                          }));
                        }}
                      >
                        <option value="">
                          {command === "gcms" ? "Buat run baru" : "Pilih run"}
                        </option>
                        {jobs
                          .filter(
                            (j) => !["running", "queued"].includes(j.status),
                          )
                          .map((j) => (
                            <option key={j.id} value={j.id}>
                              {j.name} ({j.status})
                            </option>
                          ))}
                      </Select>
                    </div>
                  )}
                </div>
                {command === "run" && (
                  <div className="input-mode-note">
                    Mulai dari data yang Anda punya. Kedua cara input
                    menghasilkan workbook yang sama untuk pipeline.
                  </div>
                )}
                {command === "run" &&
                  opts.find((o) => o.name === "rmsd_only") && (
                    <div className="rmsd-choice">
                      {field(opts.find((o) => o.name === "rmsd_only")!)}
                    </div>
                  )}
                {files
                  .filter(
                    (o) =>
                      command !== "run" ||
                      (["ligands", "receptors"].includes(o.name) &&
                        !(o.name === "ligands" && options.rmsd_only)),
                  )
                  .map((o) => (
                    <section className="input-section" key={o.name}>
                      {field(o)}
                      {o.name === "ligands" && !options.rmsd_only && (
                        <LigandBuilder
                          onSaved={saved("ligands")}
                          onBusy={inputBusy}
                        />
                      )}{" "}
                      {o.name === "receptors" && (
                        <ReceptorBuilder
                          onSaved={saved("receptors")}
                          onBusy={inputBusy}
                        />
                      )}
                    </section>
                  ))}
                {command === "run" && (
                  <Disclosure className="optional-inputs">
                    <summary>Data tambahan: ADMET & GC-MS (opsional)</summary>
                    <p>
                      Gunakan hasil ADMET yang sudah tersedia atau sertakan
                      analisis GC-MS pada eksperimen ini.
                    </p>
                    {files
                      .filter((o) => !["ligands", "receptors"].includes(o.name))
                      .map((o) => (
                        <section className="input-section" key={o.name}>
                          {field(o)}
                        </section>
                      ))}
                  </Disclosure>
                )}
                {!files.length && !sourceNeeded && (
                  <div className="ready-state">
                    <Table2 size={40} aria-hidden="true" />
                    <h3>Tidak perlu berkas input</h3>
                    <p>
                      Alur ini membuat contoh Excel ligan dan reseptor.
                      Lanjutkan untuk mengatur formatnya.
                    </p>
                  </div>
                )}
                {command === "run" && (
                  <p className="form-note">
                    Gridbox yang belum lengkap dan SMILES yang gagal ditemukan
                    akan diminta melalui form saat job berjalan.
                  </p>
                )}
              </>
            )}
            {step === 2 && (
              <ParameterPanel key={command} settings={settings} field={field} />
            )}
            {step === 3 && (
              <ExperimentReview
                current={current}
                name={name}
                source={source}
                jobs={jobs}
                changes={changes}
                display={display}
                move={move}
              />
            )}
          </motion.section>
          <div className="wizard-actions">
            <Button
              type="button"
              variant="secondary"
              onClick={() => (step ? move(step - 1) : onBack())}
              disabled={busy || pendingOperations > 0}
            >
              <ArrowLeft size={16} aria-hidden="true" />
              {step ? "Sebelumnya" : "Batal"}
            </Button>
            <span role="status">
              {pendingOperations > 0 ? "Menyiapkan input…" : stepNames[step]}
            </span>
            <Button type="submit" disabled={busy || pendingOperations > 0}>
              {step === 3 ? <Play size={17} aria-hidden="true" /> : null}
              {busy
                ? "Menambahkan…"
                : step === 3
                  ? "Jalankan eksperimen"
                  : "Lanjutkan"}
              {step < 3 && <ChevronRight size={17} aria-hidden="true" />}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
