import { Settings } from "../components/atoms/Icons";
import type { Schema, Update } from "../lib/types";
export default function SettingsPage({
  schema,
  updates,
}: {
  schema: Schema | null;
  updates: Update | null;
}) {
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Akses & pembaruan</h1>
          <p>
            Pembaruan stabil dipasang otomatis saat server tidak menjalankan
            job.
          </p>
        </div>
        <Settings size={32} aria-hidden="true" />
      </div>
      <section className="panel">
        <h2>Pembaruan otomatis</h2>
        <p>
          {updates?.automatic?.message ||
            "Versi stabil diperiksa otomatis. Runtime baru disiapkan terpisah dan diaktifkan setelah verifikasi berhasil."}
        </p>
        <p className="subtle">
          Job aktif tidak diputus. Source lokal yang memiliki perubahan membuat
          pembaruan ditunda; sesi login perlu masuk kembali setelah server
          beralih versi.
        </p>
      </section>
      <section className="panel">
        <h2>Source code ChemFlow</h2>
        <dl className="settings-list">
          <div>
            <dt>Versi terpasang</dt>
            <dd>{schema?.version || "3.0.0"}</dd>
          </div>
          <div>
            <dt>Status GitHub</dt>
            <dd>
              {updates?.status === "available"
                ? `Versi ${updates.latest} tersedia`
                : updates?.status === "current"
                  ? "Versi terpasang sudah terbaru"
                  : updates?.status === "unavailable"
                    ? "Pemeriksaan belum tersedia"
                    : "Memeriksa…"}
            </dd>
          </div>
          {updates?.source_status && (
            <div>
              <dt>Source branch main</dt>
              <dd>
                {updates.source_status === "current"
                  ? "Commit sama dengan GitHub"
                  : updates.source_status === "different"
                    ? "Commit lokal berbeda dari GitHub; tinjau perubahan"
                    : "Belum dapat diperiksa"}
              </dd>
            </div>
          )}
        </dl>
        <p>
          {updates?.message ||
            "Release GitHub diperiksa otomatis saat startup dan setiap 6 jam. Pembaruan runtime dipasang otomatis saat antrean kosong."}
        </p>
        <a
          className="button secondary"
          href="https://github.com/Arifmaulanaazis/chemflow/releases"
          target="_blank"
          rel="noreferrer"
        >
          Buka release GitHub
        </a>
      </section>
      <section className="panel">
        <h2>Keamanan ruang kerja</h2>
        <p>
          Login satu operator dengan cookie HttpOnly dan SameSite, masa sesi 8
          jam, perlindungan CSRF, serta pembatasan host. Perangkat yang masuk
          berbagi akses ke job dan berkas workspace ini.
        </p>
        <p>
          Akses remote mengikuti konfigurasi operator. Simpan kata sandi dalam
          CHEMFLOW_WEB_PASSWORD di server. Untuk tunnel publik gunakan HTTPS,
          cookie Secure, pembatasan host, dan kebijakan identitas Cloudflare
          Access.
        </p>
        <p className="subtle">
          WebUI hanya memasang release resmi melalui updater terisolasi. Tidak
          ada eksekusi shell bebas dari browser.
        </p>
      </section>
    </>
  );
}
