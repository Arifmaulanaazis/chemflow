import { Cpu, MemoryStick, HardDrive } from "../atoms/Icons";
import type { Resources } from "../../lib/types";
import { bytes } from "../../lib/api";

export function ResourceStrip({ value }: { value: Resources | null }) {
  if (!value)
    return (
      <div className="resource-strip">Menghubungkan pemantauan mesin…</div>
    );
  return (
    <div className="resource-strip">
      {[
        {
          icon: Cpu,
          label: "CPU",
          value: value.cpu,
          detail: `${value.cores} core`,
        },
        {
          icon: MemoryStick,
          label: "Memori",
          value: value.ram_percent,
          detail: `${bytes(value.ram_used)} / ${bytes(value.ram_total)}`,
        },
        {
          icon: HardDrive,
          label: "Penyimpanan",
          value: value.disk_percent,
          detail: `${bytes(value.disk_free)} tersedia`,
        },
      ].map((r) => (
        <div className="resource" key={r.label}>
          <r.icon size={19} aria-hidden="true" />
          <div>
            <div className="resource-heading">
              <span>{r.label}</span>
              <strong>{r.value.toFixed(0)}%</strong>
            </div>
            <meter
              aria-label={`${r.label} digunakan`}
              min={0}
              max={100}
              value={r.value}
            />
            <small>{r.detail}</small>
          </div>
        </div>
      ))}
    </div>
  );
}
