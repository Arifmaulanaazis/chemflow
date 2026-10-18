import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import worker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { Button, Notice } from "../components/atoms";
import Select from "../components/atoms/Select";
GlobalWorkerOptions.workerSrc = worker;
export default function PdfReader() {
  const container = useRef<HTMLDivElement>(null),
    canvas = useRef<HTMLCanvasElement>(null);
  const [document, setDocument] = useState<any>(null),
    [page, setPage] = useState(1),
    [zoom, setZoom] = useState(1),
    [width, setWidth] = useState(800),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [text, setText] = useState("");
  useEffect(() => {
    const task = getDocument({
      url: "/api/library/guide/file",
      withCredentials: true,
      wasmUrl: "/vendor/pdfjs/wasm/",
      standardFontDataUrl: "/vendor/pdfjs/standard_fonts/",
    });
    let disposed = false;
    task.promise
      .then((pdf) => {
        if (!disposed) setDocument(pdf);
      })
      .catch((e) => {
        if (!disposed) {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => {
      disposed = true;
      void task.destroy();
    };
  }, []);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(250, entries[0].contentRect.width - 28)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!document || !canvas.current) return;
    let disposed = false;
    let render: any;
    setLoading(true);
    setError("");
    (async () => {
      try {
        const p = await document.getPage(page);
        if (disposed) return;
        const base = p.getViewport({ scale: 1 }),
          viewport = p.getViewport({
            scale: Math.max(0.3, width / base.width) * zoom,
          });
        const target = canvas.current!;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        target.width = Math.floor(viewport.width * ratio);
        target.height = Math.floor(viewport.height * ratio);
        target.style.width = viewport.width + "px";
        target.style.height = viewport.height + "px";
        render = p.render({
          canvas: target,
          canvasContext: target.getContext("2d"),
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        await render.promise;
        const content = await p.getTextContent();
        if (!disposed) {
          setText(content.items.map((i: any) => i.str || "").join(" "));
          setLoading(false);
        }
      } catch (e) {
        if (!disposed && (e as Error).name !== "RenderingCancelledException") {
          setError((e as Error).message);
          setLoading(false);
        }
      }
    })();
    return () => {
      disposed = true;
      render?.cancel();
    };
  }, [document, page, zoom, width]);
  return (
    <section className="pdf-reader" aria-label="Pembaca PDF ChemFlow">
      <div className="pdf-toolbar">
        <Button
          variant="secondary"
          disabled={!document || page <= 1}
          onClick={() => setPage((v) => v - 1)}
        >
          Sebelumnya
        </Button>
        <label>
          Halaman
          <Select
            aria-label="Halaman materi"
            value={page}
            disabled={!document}
            onChange={(e) => setPage(Number(e.target.value))}
          >
            {Array.from({ length: document?.numPages || 1 }, (_, i) => (
              <option key={i} value={i + 1}>
                {i + 1} / {document?.numPages || "…"}
              </option>
            ))}
          </Select>
        </label>
        <Button
          variant="secondary"
          disabled={!document || page >= document.numPages}
          onClick={() => setPage((v) => v + 1)}
        >
          Berikutnya
        </Button>
        <div className="pdf-zoom">
          <Button
            variant="ghost"
            aria-label="Perkecil materi"
            disabled={zoom <= 0.6}
            onClick={() => setZoom((v) => Math.max(0.6, v - 0.2))}
          >
            −
          </Button>
          <Button variant="ghost" onClick={() => setZoom(1)}>
            {Math.round(zoom * 100)}%
          </Button>
          <Button
            variant="ghost"
            aria-label="Perbesar materi"
            disabled={zoom >= 2.4}
            onClick={() => setZoom((v) => Math.min(2.4, v + 0.2))}
          >
            +
          </Button>
        </div>
      </div>
      {error && <Notice>{error}</Notice>}
      <div
        className="pdf-scroll"
        ref={container}
        tabIndex={0}
        role="region"
        aria-label="Halaman PDF yang dapat digulir"
      >
        <canvas
          ref={canvas}
          aria-label={`Materi ChemFlow halaman ${page}`}
          role="img"
        />
        {loading && <p role="status">Merender halaman materi…</p>}
      </div>
      <p className="sr-only" aria-live="polite">
        Halaman {page}. {text}
      </p>
      <p className="pdf-note">
        Baca langsung di browser; gunakan tombol zoom dan geser halaman bila
        diperbesar. PDF serta PowerPoint lengkap dapat diunduh.
      </p>
    </section>
  );
}
