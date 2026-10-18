import { ShieldCheck } from "../components/atoms/Icons";
import type { Option, Job } from "../lib/types";
import { workflows } from "../lib/workflows";
import { labels } from "./OptionField";
export default function ExperimentReview({
  current,
  name,
  source,
  jobs,
  changes,
  display,
  move,
}: {
  current: (typeof workflows)[number];
  name: string;
  source: string;
  jobs: Job[];
  changes: Option[];
  display: (o: Option) => string;
  move: (n: number) => void;
}) {
  return (
    <>
      <div className="review-title">
        <current.icon size={28} aria-hidden="true" />
        <div>
          <strong>{name.trim() || current.name}</strong>
          <p>{current.name}</p>
        </div>
      </div>
      {source && (
        <p className="source-summary">
          Run sumber:{" "}
          <strong>{jobs.find((j) => j.id === source)?.name || source}</strong>
        </p>
      )}
      <div className="review-heading">
        <h3>Input & pengaturan pilihan</h3>
        <button type="button" className="text-button" onClick={() => move(1)}>
          Ubah input
        </button>
      </div>
      {changes.length ? (
        <dl className="review-list">
          {changes.map((o) => (
            <div key={o.name}>
              <dt>
                {labels[o.name] || o.label}
                <code>{o.flag}</code>
              </dt>
              <dd>{display(o)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="review-default">
          Menggunakan pengaturan bawaan CLI untuk alur ini.
        </p>
      )}
      <div className="review-assurance">
        <ShieldCheck size={22} aria-hidden="true" />
        <p>
          Satu eksperimen diproses pada satu waktu. Anda dapat memantau,
          menjawab input, dan menghentikan proses dari halaman eksperimen.
        </p>
      </div>
      <button type="button" className="text-button" onClick={() => move(2)}>
        Tinjau parameter lainnya
      </button>
    </>
  );
}
