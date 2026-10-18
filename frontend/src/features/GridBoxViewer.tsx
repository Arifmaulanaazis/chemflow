import { useEffect, useRef, useState } from "react";
import { loadNgl } from "../lib/ngl";
import { gridShape, boxVertices } from "../lib/gridbox";
import { Button, Notice } from "../components/atoms";
import { Scan, MousePointer2 } from "../components/atoms/Icons";
export interface NativeChoice {
  label: string;
  selection?: string;
  center: number[];
  size: number[];
}
export default function GridBoxViewer({
  code,
  native,
  coordinates,
  onCenter,
}: {
  code: string;
  native?: NativeChoice;
  coordinates: number[];
  onCenter: (xyz: number[]) => void;
}) {
  const element = useRef<HTMLDivElement>(null),
    stage = useRef<any>(null),
    structure = useRef<any>(null),
    box = useRef<any>(null),
    focus = useRef(false);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [picked, setPicked] = useState<{ xyz: number[]; name: string } | null>(
      null,
    ),
    [ready, setReady] = useState(0),
    [showReceptor, setShowReceptor] = useState(true);
  useEffect(() => {
    let disposed = false;
    let local: any;
    let observer: ResizeObserver;
    const abort = new AbortController();
    setLoading(true);
    setError("");
    setPicked(null);
    (async () => {
      try {
        const NGL = await loadNgl();
        if (disposed) return;
        local = new NGL.Stage(element.current!, {
          backgroundColor: "#163344",
          tooltip: false,
        });
        stage.current = local;
        observer = new ResizeObserver(() => local.handleResize());
        observer.observe(element.current!);
        const response = await fetch(`/api/receptors/${code}/structure`, {
          signal: abort.signal,
        });
        if (!response.ok) throw Error("Struktur reseptor tidak dapat dimuat.");
        const blob = await response.blob();
        if (disposed) return;
        const component = await local.loadFile(blob, {
          ext: "pdb",
          defaultRepresentation: false,
        });
        if (disposed) return;
        structure.current = component;
        component.addRepresentation("cartoon", {
          name: "protein",
          sele: "polymer",
          color: "#8dbdc6",
          opacity: 0.85,
        });
        component.addRepresentation("line", {
          name: "context",
          sele: "polymer",
          color: "#8dbdc6",
          opacity: 0.18,
        });
        component.addRepresentation("ball+stick", {
          name: "hetero",
          sele: "hetero and not water",
          colorScheme: "element",
          opacity: 0.45,
        });
        local.signals.clicked.add((event: any) => {
          const a = event?.atom;
          if (a)
            setPicked({
              xyz: [a.x, a.y, a.z],
              name: `${a.resname} ${a.resno} ${a.chainname || ""} / ${a.atomname}`,
            });
        });
        component.autoView();
        setLoading(false);
        setReady((n) => n + 1);
      } catch (e) {
        if (!disposed && (e as Error).name !== "AbortError") {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    })();
    return () => {
      disposed = true;
      abort.abort();
      observer?.disconnect();
      local?.dispose();
      stage.current = null;
      structure.current = null;
      box.current = null;
    };
  }, [code]);
  useEffect(() => {
    const c = structure.current;
    if (!c) return;
    c.removeAllRepresentations();
    c.addRepresentation("cartoon", {
      sele: "polymer",
      color: "#8dbdc6",
      opacity: 0.85,
      visible: showReceptor,
    });
    c.addRepresentation("line", {
      sele: "polymer",
      color: "#8dbdc6",
      opacity: 0.18,
      visible: showReceptor,
    });
    c.addRepresentation("ball+stick", {
      sele: "hetero and not water",
      colorScheme: "element",
      opacity: 0.45,
    });
    if (native?.selection)
      c.addRepresentation("ball+stick", {
        sele: native.selection,
        color: "#ffbe4d",
        radiusScale: 1.35,
        aspectRatio: 1.8,
      });
    focus.current = !!native;
  }, [native?.label, ready, showReceptor]);
  useEffect(() => {
    const local = stage.current;
    if (!local || loading) return;
    let cancelled = false;
    loadNgl().then((NGL) => {
      if (cancelled || stage.current !== local) return;
      if (box.current) {
        local.removeComponent(box.current);
        box.current = null;
      }
      const shape = gridShape(NGL, coordinates, "Target docking");
      if (!shape) return;
      box.current = local.addComponentFromObject(shape);
      box.current.addRepresentation("buffer");
      if (focus.current) {
        box.current.autoView(450);
        focus.current = false;
      }
    });
    return () => {
      cancelled = true;
    };
  }, [coordinates, loading, ready, native?.label]);
  return (
    <section
      className="target-viewer"
      aria-label="Pratinjau reseptor dan gridbox"
    >
      <div className="section-heading">
        <div>
          <h3>Target docking {code}</h3>
          <p>
            Ligan native berwarna emas. Gridbox hijau mengikuti nilai input.
          </p>
        </div>
        <span className="native-tag">
          {native?.label || "Koordinat manual"}
        </span>
      </div>
      {error && <Notice>{error}</Notice>}
      <div
        className="target-canvas"
        ref={element}
        data-box-vertices={JSON.stringify(boxVertices(coordinates))}
        data-native={native?.label || "manual"}
        aria-label={`Struktur reseptor ${code} dan kotak target`}
      />
      {loading && (
        <p role="status" className="viewer-loading">
          Memuat reseptor dan ligan native…
        </p>
      )}
      <div className="viewer-toolbar">
        <Button
          type="button"
          variant="secondary"
          onClick={() => box.current?.autoView(450)}
          disabled={loading}
        >
          <Scan size={16} aria-hidden="true" />
          Fokus situs
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => stage.current?.autoView(450)}
          disabled={loading}
        >
          Seluruh reseptor
        </Button>
        <label>
          <input
            type="checkbox"
            checked={showReceptor}
            onChange={(e) => setShowReceptor(e.target.checked)}
          />
          Reseptor
        </label>
      </div>
      <div className="picked-target">
        <MousePointer2 size={16} aria-hidden="true" />
        {picked ? (
          <>
            <span>
              {picked.name}: {picked.xyz.map((n) => n.toFixed(2)).join(", ")} Å
            </span>
            <Button
              type="button"
              variant="secondary"
              onClick={() => onCenter(picked.xyz)}
            >
              Jadikan pusat kotak
            </Button>
          </>
        ) : (
          <span>
            Klik atom untuk memilih pusat; putar dengan drag dan zoom dengan
            pinch/scroll.
          </span>
        )}
      </div>
      <div className="box-readout" aria-live="polite">
        <span>
          Pusat{" "}
          {coordinates
            .slice(0, 3)
            .map((v) => v.toFixed(2))
            .join(", ")}{" "}
          Å
        </span>
        <span>
          Ukuran{" "}
          {coordinates
            .slice(3)
            .map((v) => v.toFixed(2))
            .join(" × ")}{" "}
          Å
        </span>
      </div>
    </section>
  );
}
