import { useMemo, useRef, useState } from "react";
import { motion } from "motion/react";
import Select from "../components/atoms/Select";
import { Button } from "../components/atoms";
function numeric(value: unknown) {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (
    typeof value === "string" &&
    /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(value.trim())
  )
    return Number(value);
  return null;
}
export default function ScientificChart({
  rows,
  source,
}: {
  rows: unknown[][];
  source: string;
}) {
  const header = (rows[0] || []).map((v, i) => String(v || `Kolom ${i + 1}`));
  const columns = header
    .map((label, index) => ({ label, index }))
    .filter(
      (c) =>
        rows.slice(1).filter((row) => numeric(row[c.index]) !== null).length >=
        2,
    );
  const [chosen, setChosen] = useState<number | null>(null),
    [labels, setLabels] = useState(0),
    [kind, setKind] = useState("bar"),
    [start, setStart] = useState(0),
    [count, setCount] = useState(30),
    [active, setActive] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const column = columns.find((c) => c.index === chosen) || columns[0];
  const points = useMemo(
    () =>
      column
        ? rows.slice(1).flatMap((row, i) => {
            const y = numeric(row[column.index]);
            return y === null
              ? []
              : [{ label: String(row[labels] ?? i + 1), value: y, row: i + 1 }];
          })
        : [],
    [rows, column?.index, labels],
  );
  if (!columns.length)
    return (
      <div className="ready-state">
        <h3>Belum ada seri angka yang dapat digambar</h3>
        <p>
          Pilih worksheet dengan minimal dua baris data numerik. Tabel asli
          tetap tersedia.
        </p>
      </div>
    );
  const shown = points.slice(start, start + count),
    minimum = Math.min(0, ...shown.map((p) => p.value)),
    maximum = Math.max(0, ...shown.map((p) => p.value)),
    range = maximum - minimum || 1,
    y = (value: number) => 270 - ((value - minimum) / range) * 230,
    step = 700 / Math.max(1, shown.length),
    x = (i: number) => 65 + i * step + step / 2,
    base = y(0);
  const selected = active === null ? null : shown[active];
  const format = (v: number) =>
    Math.abs(v) >= 1e6 || (Math.abs(v) > 0 && Math.abs(v) < 0.001)
      ? v.toExponential(2)
      : v.toLocaleString("id-ID", { maximumFractionDigits: 3 });
  return (
    <div className="scientific-chart">
      <div className="chart-controls">
        <label>
          Seri numerik
          <Select
            aria-label="Seri grafik"
            value={column.index}
            onChange={(e) => {
              setChosen(Number(e.target.value));
              setActive(null);
              setStart(0);
            }}
          >
            {columns.map((c) => (
              <option key={c.index} value={c.index}>
                {c.label}
              </option>
            ))}
          </Select>
        </label>
        <label>
          Label sumbu X
          <Select
            aria-label="Label sumbu X"
            value={labels}
            onChange={(e) => setLabels(Number(e.target.value))}
          >
            {header.map((h, i) => (
              <option key={i} value={i}>
                {h}
              </option>
            ))}
          </Select>
        </label>
        <label>
          Visualisasi
          <Select
            aria-label="Jenis grafik"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="bar">Batang</option>
            <option value="line">Garis</option>
          </Select>
        </label>
      </div>
      <div
        className="chart-viewport"
        tabIndex={0}
        role="region"
        aria-label="Grafik yang dapat digulir"
      >
        <svg
          ref={svg}
          viewBox="0 0 800 325"
          role="group"
          aria-label={`Grafik ${column.label} dari ${source}`}
          className="live-chart"
        >
          <title>{column.label}</title>
          {Array.from({ length: 5 }, (_, i) => {
            const value = minimum + (range * i) / 4;
            return (
              <g key={i}>
                <line
                  x1="62"
                  x2="770"
                  y1={y(value)}
                  y2={y(value)}
                  stroke="#dce6ec"
                />
                <text x="54" y={y(value) + 4} textAnchor="end">
                  {format(value)}
                </text>
              </g>
            );
          })}
          <line x1="62" x2="770" y1={base} y2={base} stroke="#7592a3" />
          {kind === "line" && (
            <motion.path
              d={shown
                .map((p, i) => `${i ? "L" : "M"}${x(i)},${y(p.value)}`)
                .join(" ")}
              stroke="#2459c4"
              strokeWidth="2.5"
              fill="none"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 0.45 }}
            />
          )}
          {shown.map((p, i) => (
            <g
              key={`${p.row}-${column.index}`}
              role="button"
              tabIndex={0}
              aria-label={`${p.label}: ${format(p.value)}`}
              onFocus={() => setActive(i)}
              onPointerEnter={() => setActive(i)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") setActive(i);
              }}
            >
              {kind === "bar" ? (
                <motion.rect
                  x={x(i) - Math.max(2, step * 0.65) / 2}
                  width={Math.max(2, step * 0.65)}
                  rx="3"
                  initial={{ y: base, height: 0 }}
                  animate={{
                    y: Math.min(y(p.value), base),
                    height: Math.max(1, Math.abs(y(p.value) - base)),
                  }}
                  fill={active === i ? "#176e65" : "#3371c4"}
                />
              ) : (
                <circle
                  cx={x(i)}
                  cy={y(p.value)}
                  r={active === i ? 6 : 3.5}
                  fill={active === i ? "#176e65" : "#2459c4"}
                />
              )}
              <rect
                x={x(i) - step / 2}
                y="30"
                width={step}
                height="245"
                fill="transparent"
              />
              {i % Math.max(1, Math.ceil(shown.length / 8)) === 0 && (
                <text x={x(i)} y="295" textAnchor="middle">
                  {p.label.length > 14 ? p.label.slice(0, 12) + "…" : p.label}
                </text>
              )}
            </g>
          ))}
        </svg>
      </div>
      <div className="chart-tooltip" aria-live="polite">
        {selected ? (
          <>
            <strong>{selected.label}</strong>
            <span>
              {column.label}: {format(selected.value)}
            </span>
          </>
        ) : (
          <span>
            Sentuh batang/titik, arahkan pointer, atau fokus dengan Tab untuk
            membaca nilainya.
          </span>
        )}
      </div>
      <div className="chart-pagination">
        <Button
          variant="secondary"
          disabled={start === 0}
          onClick={() => {
            setStart((v) => Math.max(0, v - count));
            setActive(null);
          }}
        >
          Sebelumnya
        </Button>
        <span>
          Baris {start + 1}–{Math.min(start + count, points.length)} dari{" "}
          {points.length}
        </span>
        <Button
          variant="secondary"
          disabled={start + count >= points.length}
          onClick={() => {
            setStart((v) => v + count);
            setActive(null);
          }}
        >
          Berikutnya
        </Button>
        <Button
          variant="ghost"
          onClick={() => {
            if (!svg.current) return;
            const blob = new Blob(
              [new XMLSerializer().serializeToString(svg.current)],
              { type: "image/svg+xml" },
            );
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "chemflow-chart.svg";
            a.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
          }}
        >
          Unduh SVG
        </Button>
      </div>
      <p className="chart-provenance">
        Sumber: {source}. Grafik membaca nilai preview workbook, tanpa
        menghitung ulang hasil ilmiah. Data kosong dilewati; unduh workbook
        untuk seluruh data.
      </p>
    </div>
  );
}
