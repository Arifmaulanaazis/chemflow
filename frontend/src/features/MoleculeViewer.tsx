import { gridShape } from "../lib/gridbox";
import Select from "../components/atoms/Select";
import { loadNgl } from "../lib/ngl";
import { useEffect, useRef, useState } from "react";
import { RotateCcw, Scan, Eye, MousePointer2 } from "../components/atoms/Icons";
import { Button, Notice } from "../components/atoms";
import { fileUrl } from "../lib/api";
import type { Artifact } from "../lib/types";
export default function MoleculeViewer({
  jobId,
  file,
}: {
  jobId: string;
  file: Artifact;
}) {
  const container = useRef<HTMLDivElement>(null),
    stage = useRef<any>(null),
    component = useRef<any>(null),
    grid = useRef<any>(null);
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [picked, setPicked] = useState(
      "Klik atom untuk melihat residu dan koordinat.",
    ),
    [contacts, setContacts] = useState(false),
    [representation, setRepresentation] = useState("cartoon"),
    [model, setModel] = useState(0),
    [modelCount, setModelCount] = useState(1),
    [box, setBox] = useState(false),
    [coordinates, setCoordinates] = useState([0, 0, 0, 20, 20, 20]);
  useEffect(() => {
    let cancelled = false;
    let observer: ResizeObserver | undefined;
    let local: any;
    setLoading(true);
    setError("");
    setPicked("Klik atom untuk melihat residu dan koordinat.");
    setContacts(false);
    setModel(0);
    (async () => {
      try {
        const NGL = await loadNgl();
        if (cancelled) return;
        local = new NGL.Stage(container.current!, {
          backgroundColor: "#152b3c",
          tooltip: false,
        });
        stage.current = local;
        observer = new ResizeObserver(() => local.handleResize());
        observer.observe(container.current!);
        const response = await fetch(fileUrl(jobId, file.path, false));
        if (!response.ok)
          throw new Error(
            "Struktur tidak dapat dimuat. Masuk kembali atau unduh berkas.",
          );
        const blob = await response.blob();
        if (cancelled) return;
        const ext = file.extension.slice(1);
        const c = await local.loadFile(blob, {
          ext: ext === "pdbqt" ? "pdb" : ext,
          defaultRepresentation: false,
        });
        if (cancelled) return;
        component.current = c;
        setModelCount(c.structure.modelStore.count || 1);
        c.addRepresentation("cartoon", {
          sele: "polymer",
          colorScheme: "chainname",
          quality: "medium",
        });
        c.addRepresentation("ball+stick", {
          sele: "hetero and not water",
          colorScheme: "element",
          aspectRatio: 1.5,
        });
        c.addRepresentation("contact", {
          sele: "not water",
          filterSele: "hetero",
          visible: false,
          hydrogenBond: true,
          hydrophobic: true,
        });
        c.autoView();
        local.signals.clicked.add((p: any) => {
          if (p?.atom) {
            const a = p.atom;
            setPicked(
              `${a.resname} ${a.resno} · rantai ${a.chainname || "—"} · ${a.atomname} | x ${a.x.toFixed(3)}, y ${a.y.toFixed(3)}, z ${a.z.toFixed(3)} Å`,
            );
          }
        });
        setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
      observer?.disconnect();
      local?.dispose();
      component.current = null;
      stage.current = null;
      grid.current = null;
    };
  }, [jobId, file.path, file.extension]);
  useEffect(() => {
    if (!component.current) return;
    component.current.removeAllRepresentations();
    component.current.addRepresentation(representation, {
      sele: representation === "cartoon" ? "polymer" : "not water",
      colorScheme: representation === "cartoon" ? "chainname" : "element",
    });
    if (representation === "cartoon")
      component.current.addRepresentation("ball+stick", {
        sele: "hetero and not water",
        colorScheme: "element",
      });
    component.current.addRepresentation("contact", {
      sele: "not water",
      filterSele: "hetero",
      visible: contacts,
    });
    component.current.setSelection(`/${model}`);
  }, [representation, contacts, model, loading]);
  useEffect(() => {
    let cancelled = false;
    const current = stage.current;
    if (!current || loading) return;
    if (grid.current) {
      current.removeComponent(grid.current);
      grid.current = null;
    }
    if (!box) return;
    loadNgl().then((NGL) => {
      if (cancelled) return;
      const shape = gridShape(NGL, coordinates);
      if (!shape) return;
      grid.current = current.addComponentFromObject(shape);
      grid.current.addRepresentation("buffer");
    });
    return () => {
      cancelled = true;
    };
  }, [box, coordinates, loading]);
  return (
    <div className="molecule-viewer">
      <div className="viewer-toolbar">
        <label>
          Representasi
          <Select
            aria-label="Representasi molekul"
            value={representation}
            onChange={(e) => setRepresentation(e.target.value)}
          >
            <option value="cartoon">Cartoon + ligan</option>
            <option value="ball+stick">Ball & stick</option>
            <option value="surface">Permukaan</option>
            <option value="line">Garis</option>
          </Select>
        </label>
        {modelCount > 1 && (
          <label>
            Pose / model
            <Select
              aria-label="Pose molekul"
              value={model}
              onChange={(e) => setModel(Number(e.target.value))}
            >
              {Array.from({ length: modelCount }, (_, i) => (
                <option key={i} value={i}>
                  {i + 1}
                </option>
              ))}
            </Select>
          </label>
        )}
        <Button variant="secondary" onClick={() => stage.current?.autoView()}>
          <Scan size={16} aria-hidden="true" />
          Fit
        </Button>
        <Button
          variant="secondary"
          onClick={() => {
            setModel(0);
            stage.current?.animationControls.rotate([0, 0, 0, 1], 500);
            stage.current?.autoView();
          }}
        >
          <RotateCcw size={16} aria-hidden="true" />
          Reset
        </Button>
      </div>
      {error && (
        <Notice>
          Viewer 3D: {error}. Gunakan browser dengan WebGL aktif atau unduh
          berkas.
        </Notice>
      )}
      <div
        className="molecule-canvas"
        ref={container}
        aria-label={`Viewer 3D ${file.path}`}
      />
      {loading && (
        <div role="status" className="viewer-loading">
          Memuat struktur molekul…
        </div>
      )}
      <div className="viewer-caption">
        <MousePointer2 size={15} aria-hidden="true" />
        <span>{picked}</span>
      </div>
      <div className="viewer-options">
        <label>
          <input
            type="checkbox"
            checked={contacts}
            onChange={(e) => setContacts(e.target.checked)}
          />
          Kontak geometrik NGL
        </label>
        <label>
          <input
            type="checkbox"
            checked={box}
            onChange={(e) => setBox(e.target.checked)}
          />
          Gridbox
        </label>
      </div>
      {box && (
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
                min={i > 2 ? 0.1 : undefined}
                value={coordinates[i]}
                onChange={(e) =>
                  setCoordinates((v) =>
                    v.map((n, k) => (k === i ? Number(e.target.value) : n)),
                  )
                }
              />
            </label>
          ))}
        </div>
      )}
      <p className="viewer-note">
        Putar dengan drag; zoom dengan scroll atau pinch. Kontak NGL adalah
        perkiraan geometri, terpisah dari tabel interaksi BIOVIA. PDBQT
        ditampilkan sebagai koordinat PDB.
      </p>
    </div>
  );
}
