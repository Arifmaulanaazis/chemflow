import Disclosure from "../components/atoms/Disclosure";
import { lazy, Suspense } from "react";
const GridBoxViewer = lazy(() => import("./GridBoxViewer"));
import Select from "../components/atoms/Select";
import { useState } from "react";
import { Plus, Search, Trash2 } from "../components/atoms/Icons";
import { api } from "../lib/api";
import { Button, Notice } from "../components/atoms";
import type { Upload } from "../lib/types";
interface Native {
  label: string;
  selection?: string;
  chain: string;
  residue: string;
  atoms: number;
  center: number[];
  size: number[];
}
interface Row {
  pdb_code: string;
  center: number[];
  size: number[];
  native_ligand: string;
}
export default function ReceptorBuilder({
  onSaved,
  onBusy,
}: {
  onSaved: (u: Upload) => void;
  onBusy?: (busy: boolean) => void;
}) {
  const [code, setCode] = useState(""),
    [natives, setNatives] = useState<Native[]>([]),
    [values, setValues] = useState([0, 0, 0, 20, 20, 20]),
    [native, setNative] = useState("manual"),
    [rows, setRows] = useState<Row[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [loaded, setLoaded] = useState(false);
  return (
    <Disclosure className="receptor-builder">
      <summary>Buat workbook reseptor di browser</summary>
      <p className="form-note">
        Masukkan kode PDB, pilih ligan native untuk mengisi koordinat otomatis,
        atau tentukan gridbox secara manual. Tambahkan beberapa situs bila
        diperlukan.
      </p>
      {error && <Notice>{error}</Notice>}
      <div className="receptor-search">
        <div className="field">
          <label htmlFor="pdb-code">Kode PDB</label>
          <input
            id="pdb-code"
            value={code}
            maxLength={4}
            placeholder="1HSG"
            onChange={(e) => {
              setCode(e.target.value.toUpperCase());
              setLoaded(false);
              setNatives([]);
              setNative("manual");
            }}
          />
        </div>
        <Button
          type="button"
          variant="secondary"
          disabled={busy || !/^[0-9][A-Z0-9]{3}$/.test(code)}
          onClick={async () => {
            setBusy(true);
            onBusy?.(true);
            setError("");
            try {
              const r = await api<{ ligands: Native[] }>(`/receptors/${code}`);
              setNatives(r.ligands);
              setLoaded(true);
              if (r.ligands.length) {
                const l = r.ligands[0];
                setNative(l.label);
                setValues([...l.center, ...l.size]);
              }
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
              onBusy?.(false);
            }
          }}
        >
          <Search size={16} aria-hidden="true" />
          {busy ? "Mengambil…" : "Cari ligan native"}
        </Button>
      </div>
      {loaded && (
        <div className="field">
          <label htmlFor="native-ligand">Ligan native</label>
          <Select
            id="native-ligand"
            value={native}
            onChange={(e) => {
              setNative(e.target.value);
              const l = natives.find((n) => n.label === e.target.value);
              if (l) setValues([...l.center, ...l.size]);
            }}
          >
            <option value="manual">Koordinat manual</option>
            {natives.map((n) => (
              <option key={n.label} value={n.label}>
                {n.label} · {n.atoms} atom · rantai {n.chain}
              </option>
            ))}
          </Select>
          {natives.length === 0 && (
            <small>
              Tidak ada native terdeteksi. Tentukan pusat dan ukuran secara
              manual.
            </small>
          )}
        </div>
      )}
      {loaded && (
        <Suspense fallback={<p role="status">Menyiapkan viewer gridbox…</p>}>
          <GridBoxViewer
            code={code}
            native={natives.find((n) => n.label === native)}
            coordinates={values}
            onCenter={(xyz) => {
              setNative("manual");
              setValues((old) => [...xyz, ...old.slice(3)]);
            }}
          />
        </Suspense>
      )}
      <div className="gridbox-fields">
        {["Center X", "Center Y", "Center Z", "Size X", "Size Y", "Size Z"].map(
          (label, i) => (
            <label key={label} htmlFor={`receptor-${i}`}>
              {label} (Å)
              <input
                id={`receptor-${i}`}
                type="number"
                step="any"
                value={values[i]}
                onChange={(e) =>
                  setValues((v) =>
                    v.map((n, k) => (k === i ? Number(e.target.value) : n)),
                  )
                }
              />
            </label>
          ),
        )}
      </div>
      <Button
        type="button"
        variant="secondary"
        onClick={() => {
          if (
            !/^[0-9][A-Z0-9]{3}$/.test(code) ||
            !values.every(Number.isFinite) ||
            values.slice(3).some((v) => v <= 0 || v > 200)
          ) {
            setError(
              "Masukkan kode PDB valid dan ukuran kotak > 0 hingga 200 Å.",
            );
            return;
          }
          setRows((r) => [
            ...r,
            {
              pdb_code: code,
              center: values.slice(0, 3),
              size: values.slice(3),
              native_ligand: native,
            },
          ]);
          setError("");
        }}
      >
        <Plus size={16} aria-hidden="true" />
        Tambahkan situs
      </Button>
      {rows.length > 0 && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>PDB / native</th>
                  <th>Pusat (Å)</th>
                  <th>Ukuran (Å)</th>
                  <th>Aksi</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>
                      {r.pdb_code} / {r.native_ligand}
                    </td>
                    <td>{r.center.join(", ")}</td>
                    <td>{r.size.join(", ")}</td>
                    <td>
                      <button
                        className="text-button"
                        type="button"
                        aria-label={`Hapus situs ${i + 1}`}
                        onClick={() =>
                          setRows((v) => v.filter((_, k) => k !== i))
                        }
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Button
            type="button"
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              onBusy?.(true);
              try {
                const upload = await api<Upload>("/receptors", {
                  method: "POST",
                  body: JSON.stringify({ rows }),
                });
                onSaved(upload);
                setRows([]);
                setError("");
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
                onBusy?.(false);
              }
            }}
          >
            Gunakan workbook {rows.length} situs
          </Button>
        </>
      )}
    </Disclosure>
  );
}
