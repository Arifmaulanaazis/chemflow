import { Activity } from "../components/atoms/Icons";
import { ResourceStrip } from "../components/molecules/ResourceStrip";
import { bytes, date } from "../lib/api";
import type { Resources } from "../lib/types";
export default function ResourcePage({
  resources,
  running,
}: {
  resources: Resources | null;
  running: number;
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Mesin & sumber daya</h1>
          <p>Pembacaan langsung dari mesin yang menjalankan perhitungan.</p>
        </div>
        <Activity size={32} aria-hidden="true" />
      </div>
      <ResourceStrip value={resources} />
      <section className="panel">
        <h2>Kapasitas workspace</h2>
        <dl className="settings-list">
          <div>
            <dt>Sistem operasi</dt>
            <dd>{resources?.platform || "Memuat…"}</dd>
          </div>
          <div>
            <dt>Core logis</dt>
            <dd>{resources?.cores ?? "—"}</dd>
          </div>
          <div>
            <dt>Memori terpasang</dt>
            <dd>{resources ? bytes(resources.ram_total) : "—"}</dd>
          </div>
          <div>
            <dt>Ruang penyimpanan tersedia</dt>
            <dd>{resources ? bytes(resources.disk_free) : "—"}</dd>
          </div>
          <div>
            <dt>Antrean</dt>
            <dd>{running} job · 1 worker</dd>
          </div>
          <div>
            <dt>Pembaruan terakhir</dt>
            <dd>{resources ? date(resources.time) : "—"}</dd>
          </div>
        </dl>
        <p className="subtle">
          CPU, RAM, dan disk adalah pemakaian seluruh mesin, termasuk aplikasi
          lain. Streaming setiap 2 detik; polling 5 detik jika koneksi terputus.
        </p>
      </section>
    </>
  );
}
