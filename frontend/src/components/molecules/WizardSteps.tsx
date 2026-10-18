import { ShieldCheck } from "../atoms/Icons";
import { stepNames } from "../../lib/workflows";
export default function WizardSteps({
  step,
  maxStep,
  move,
}: {
  step: number;
  maxStep: number;
  move: (step: number) => void;
}) {
  return (
    <aside className="wizard-rail" aria-label="Kemajuan eksperimen">
      <nav aria-label="Langkah eksperimen">
        <ol>
          {stepNames.map((label, i) => (
            <li
              key={label}
              className={i === step ? "active" : i < step ? "complete" : ""}
            >
              <button
                type="button"
                disabled={i > maxStep}
                aria-current={i === step ? "step" : undefined}
                onClick={() => move(i)}
              >
                <span>{i < step ? "✓" : i + 1}</span>
                <div>
                  {label}
                  <small>
                    {
                      [
                        "Pilih tujuan",
                        "Ligan, reseptor, atau data",
                        "Parameter & keluaran",
                        "Periksa ringkasan",
                      ][i]
                    }
                  </small>
                </div>
              </button>
            </li>
          ))}
        </ol>
      </nav>
      <div className="wizard-tip">
        <ShieldCheck size={22} aria-hidden="true" />
        <strong>Selama proses berjalan</strong>
        <p>
          Input yang dibutuhkan saat proses berjalan akan muncul di browser.
          Hasil tersimpan di server.
        </p>
      </div>
    </aside>
  );
}
