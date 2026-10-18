import Disclosure from "../components/atoms/Disclosure";
import { useState } from "react";
import { Button, Notice } from "../components/atoms";
import { Plus, Trash2 } from "../components/atoms/Icons";
import { api } from "../lib/api";
import type { Upload } from "../lib/types";
type Row = { name: string; smiles: string; group: string };
export default function LigandBuilder({
  onSaved,
  onBusy,
}: {
  onSaved: (u: Upload) => void;
  onBusy?: (busy: boolean) => void;
}) {
  const [rows, setRows] = useState<Row[]>([
    { name: "", smiles: "", group: "" },
  ]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const update = (i: number, key: keyof Row, value: string) =>
    setRows((old) => old.map((r, k) => (k === i ? { ...r, [key]: value } : r)));
  return (
    <Disclosure className="input-builder">
      <summary>Tulis ligan langsung di browser</summary>
      <p>
        Tambahkan nama, SMILES, dan kelompok sampel. SMILES boleh kosong untuk
        pencarian PubChem; bila pencarian gagal, Anda dapat mengisinya saat
        proses berjalan.
      </p>
      {error && <Notice>{error}</Notice>}
      <div className="ligand-rows">
        {rows.map((row, i) => (
          <fieldset className="ligand-row" key={i}>
            <legend>Senyawa {i + 1}</legend>
            <div className="form-grid">
              <label>
                Nama senyawa
                <input
                  aria-label={`Nama senyawa ${i + 1}`}
                  value={row.name}
                  maxLength={300}
                  onChange={(e) => update(i, "name", e.target.value)}
                  placeholder="Contoh: Quercetin"
                />
              </label>
              <label>
                Kelompok
                <input
                  aria-label={`Kelompok senyawa ${i + 1}`}
                  value={row.group}
                  maxLength={200}
                  onChange={(e) => update(i, "group", e.target.value)}
                  placeholder="Contoh: Ekstrak daun"
                />
              </label>
              <label className="wide-field">
                SMILES (opsional)
                <input
                  aria-label={`SMILES senyawa ${i + 1}`}
                  value={row.smiles}
                  onChange={(e) => update(i, "smiles", e.target.value)}
                  placeholder="Isi struktur atau biarkan PubChem mencari"
                />
              </label>
            </div>
            {rows.length > 1 && (
              <Button
                type="button"
                variant="ghost"
                aria-label={`Hapus senyawa ${i + 1}`}
                onClick={() => setRows((old) => old.filter((_, k) => k !== i))}
              >
                <Trash2 size={16} aria-hidden="true" />
                Hapus
              </Button>
            )}
          </fieldset>
        ))}
      </div>
      <div className="builder-actions">
        <Button
          type="button"
          variant="secondary"
          disabled={rows.length >= 1000}
          onClick={() =>
            setRows((old) => [...old, { name: "", smiles: "", group: "" }])
          }
        >
          <Plus size={16} aria-hidden="true" />
          Tambah senyawa
        </Button>
        <Button
          type="button"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            onBusy?.(true);
            setError("");
            try {
              const u = await api<Upload>("/ligands", {
                method: "POST",
                body: JSON.stringify({ rows }),
              });
              onSaved(u);
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
              onBusy?.(false);
            }
          }}
        >
          {busy ? "Menyimpan…" : `Gunakan ${rows.length} senyawa`}
        </Button>
      </div>
    </Disclosure>
  );
}
