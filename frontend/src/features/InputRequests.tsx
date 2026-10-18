import Select from "../components/atoms/Select";
import { useEffect, useState } from "react";
import { Button, Notice } from "../components/atoms";
import { api } from "../lib/api";
export interface InputRequest {
  id: string;
  kind: "smiles" | "gridbox";
  title: string;
  compound?: string;
  pdb_code?: string;
  default_size?: number[];
  choices?: {
    label: string;
    atoms: number;
    center: number[];
    size: number[];
  }[];
}
function Reply({
  request: r,
  jobId,
  onDone,
}: {
  request: InputRequest;
  jobId: string;
  onDone: () => void;
}) {
  const first = r.choices?.[0];
  const [native, setNative] = useState(first?.label || "manual"),
    [center, setCenter] = useState<(number | string)[]>(
      first?.center || [0, 0, 0],
    ),
    [size, setSize] = useState<(number | string)[]>(
      first?.size || r.default_size || [20, 20, 20],
    ),
    [smiles, setSmiles] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const send = async (skip = false) => {
    setBusy(true);
    setError("");
    try {
      await api(`/jobs/${jobId}/inputs/${r.id}`, {
        method: "POST",
        body: JSON.stringify(
          r.kind === "smiles"
            ? { smiles: skip ? "" : smiles }
            : { native, center: center.map(Number), size: size.map(Number) },
        ),
      });
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="input-request" aria-labelledby={`request-${r.id}`}>
      <span className="pending-kicker">Proses menunggu jawaban Anda</span>
      <h2 id={`request-${r.id}`}>{r.title}</h2>
      <p>
        {r.kind === "smiles"
          ? "PubChem belum menemukan struktur senyawa ini. Isi SMILES yang valid untuk melanjutkan, atau lewati senyawa ini."
          : "Pilih ligan native atau tentukan pusat dan ukuran kotak docking. Nilai dapat disesuaikan sebelum dikirim."}
      </p>
      {error && <Notice>{error}</Notice>}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        {r.kind === "smiles" ? (
          <label className="field">
            SMILES untuk {r.compound}
            <textarea
              value={smiles}
              maxLength={10000}
              required
              placeholder="Contoh: CCO"
              onChange={(e) => setSmiles(e.target.value)}
            />
          </label>
        ) : (
          <>
            <div className="field">
              <label htmlFor={`native-${r.id}`}>Ligan native</label>
              <Select
                id={`native-${r.id}`}
                value={native}
                onChange={(e) => {
                  setNative(e.target.value);
                  const l = r.choices?.find((c) => c.label === e.target.value);
                  if (l) {
                    setCenter(l.center);
                    setSize(l.size);
                  }
                }}
              >
                <option value="manual">Koordinat manual</option>
                {r.choices?.map((c) => (
                  <option key={c.label} value={c.label}>
                    {c.label} ({c.atoms} atom)
                  </option>
                ))}
              </Select>
            </div>
            <div className="gridbox-fields">
              {[
                "Center X",
                "Center Y",
                "Center Z",
                "Size X",
                "Size Y",
                "Size Z",
              ].map((label, i) => (
                <label key={label}>
                  {label} (Å)
                  <input
                    type="number"
                    step="any"
                    min={i > 2 ? 0.001 : undefined}
                    max={i > 2 ? 200 : 99999}
                    required
                    value={i < 3 ? center[i] : size[i - 3]}
                    onChange={(e) => {
                      const change = (v: (string | number)[]) =>
                        v.map((x, k) => (k === i % 3 ? e.target.value : x));
                      if (i < 3) setCenter(change);
                      else setSize(change);
                    }}
                  />
                </label>
              ))}
            </div>
          </>
        )}
        <div className="builder-actions">
          {r.kind === "smiles" && (
            <Button
              type="button"
              variant="secondary"
              disabled={busy}
              onClick={() => void send(true)}
            >
              Lewati senyawa ini
            </Button>
          )}
          <Button type="submit" disabled={busy}>
            {busy ? "Mengirim…" : "Kirim & lanjutkan proses"}
          </Button>
        </div>
      </form>
    </section>
  );
}
export default function InputRequests({
  jobId,
  running,
}: {
  jobId: string;
  running: boolean;
}) {
  const [pending, setPending] = useState<InputRequest[]>([]),
    [error, setError] = useState("");
  useEffect(() => {
    if (!running) {
      setPending([]);
      setError("");
      return;
    }
    setPending([]);
    setError("");
    let disposed = false;
    const refresh = () =>
      api<InputRequest[]>(`/jobs/${jobId}/inputs`)
        .then((v) => {
          if (!disposed) {
            setPending(v);
            setError("");
          }
        })
        .catch((e) => {
          if (!disposed) setError(e.message);
        });
    void refresh();
    const timer = setInterval(refresh, 2000);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [jobId, running]);
  return (
    <>
      {error && <Notice>{error}</Notice>}
      {pending.length > 0 && (
        <p className="sr-only" role="status">
          Eksperimen membutuhkan input. Form tersedia di bawah ini.
        </p>
      )}
      {pending.map((r) => (
        <Reply
          key={r.id}
          request={r}
          jobId={jobId}
          onDone={() => setPending((v) => v.filter((x) => x.id !== r.id))}
        />
      ))}
    </>
  );
}
