# Pengujian ChemFlow 3.0.0

Catatan: ini adalah baseline rilis sebelum refaktor UX. Desain, wizard, interaksi
API dan hasil browser terbaru tercatat pada [pengujian refaktor WebUI](testing-webui-refactor.md).

Eksekusi lokal pada 17 Oktober 2026 (Asia/Bangkok), Windows, Python 3.14.6,
Node.js 22.21.0. Browser memakai Chrome headless dengan emulasi desktop
1440 x 1000 dan iPhone 13 390 x 844, termasuk WebGL software untuk NGL.

## Hasil aktual

| Pemeriksaan | Hasil |
|---|---|
| Suite utama Python, termasuk regresi CLI/ilmiah dan integrasi API | **871 lulus, 1 dilewati**, 872 kasus |
| Tambahan konfigurasi server/proxy/password dan keamanan resume | **5 lulus** |
| Integrasi API terbaru, dijalankan ulang terpisah | **25 lulus, 1 dilewati**; sudah tercakup pada suite utama |
| Regresi resume setelah penambahan TLS/noninteractive | **23 lulus**; mencakup pengujian lama yang juga ada di suite utama |
| Komponen React/Vitest | **5 lulus** |
| Playwright desktop + mobile | **4 lulus**, 0 gagal, 0 flaky |
| TypeScript dan build produksi Vite | **Lulus** |
| Build wheel dan pemeriksaan bundling SPA/NGL/lisensi | **Lulus** |
| PPTX: integritas paket, import ulang, grafik native/workbook | **Lulus**, 56 slide |
| PDF: jumlah halaman dan inspeksi render | **56 halaman**, materi asli + enam halaman baru |

Total unik Python yang diuji lintas suite utama dan tambahan adalah **876 lulus,
1 dilewati**. Hasil pengulangan API/resume tidak dijumlahkan lagi. Lima tes server
baru dijalankan terpisah setelah suite utama dikumpulkan. Satu tes pembuatan
symlink dilewati karena memerlukan izin Windows; penolakan traversal path tetap
diuji. CI Linux/macOS akan memeriksa jalur symlink bila sistem mengizinkan.

Laporan lokal yang dapat ditelusuri berada pada `.cache/tests-python.xml`,
`.cache/tests-api.xml`, `.cache/tests-server.xml`, `.cache/browser-results.json`,
`.cache/package-verification.json`, dan `.cache/release/validation-r2.json`.
Folder `.cache` adalah artefak pengujian lokal dan tidak masuk Git.

## Apa yang diverifikasi

API: autentikasi wajib, cookie HttpOnly/SameSite, expiry/logout, CSRF, origin/host,
rate limit login, batas unggahan dan pembersihan unggahan gagal, penolakan input
path/argumen berbahaya, SQLite/job queue, cancel, pemulihan status interrupted,
lock workspace lintas proses, impor CLI tanpa mengubah sumber, pembatasan folder
impor agar tidak menyalin dirinya sendiri, penghentian proses beserta child,
preview tabel/worksheet, unduhan, resource monitor, dan cache/error GitHub.

Job `init --skip-check` benar-benar menjalankan child CLI, membuat tiga workbook,
memunculkan log, lalu diuji preview/unduhannya. Tes server memastikan host dan
proxy eksplisit serta menolak wildcard/password pendek. Resume dari konfigurasi
lama diuji agar prompt terminal mati dan verifikasi TLS ADMET aktif.

Browser: login, SSE terhubung, navigasi, form, antrean/job nyata, log, preview
workbook, unduhan, error unggahan, penyusunan workbook reseptor, NGL yang benar-
benar menggambar canvas, pergantian representasi, kontak geometrik dan gridbox.
Tidak ada galat JavaScript dalam empat skenario yang lulus. Axe memeriksa ruang
kerja dan halaman hasil tanpa pelanggaran terdeteksi dalam cakupan skenario itu.
Mobile diuji untuk overflow halaman dan interaksi sentuh; tabel tetap dapat
digulir di dalam kontainernya.

Perbaikan yang ditemukan oleh browser test meliputi kontras label workbench,
header kosong dari sel Excel gabungan, fokus keyboard pada log/tabel, serta
containing block untuk label pembaca layar agar tidak memperlebar viewport
mobile dan menggeser koordinat sentuhan.

## Menjalankan ulang

```sh
python -m pip install -e ".[web,test]"
python -m pytest -q
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Pada lingkungan Windows terisolasi yang membatasi penghentian child server oleh
Playwright, jalankan server tes pada terminal terpisah:

```sh
python scripts/test_web_server.py
```

Lalu dari `frontend/` pada terminal PowerShell lain:

```powershell
$env:CHEMFLOW_E2E_EXTERNAL='1'
$env:CHEMFLOW_TEST_BROWSER='C:/Program Files/Google/Chrome/Application/chrome.exe'
npm run test:e2e
```

Hentikan server tes setelah selesai. Server ini hanya listen loopback, memakai
fixture sintetis dan kata sandi khusus tes; jangan gunakan untuk produksi.
`CHEMFLOW_TEST_BROWSER` opsional jika Chromium Playwright sudah tersedia.
CI otomatis memakai server tes yang dikelola Playwright dan Chromium terpasang.

## Batas bukti

- Matriks GitHub Actions Windows/macOS/Linux (Python 3.11/3.12) sudah disiapkan;
  tidak dijalankan dari sesi lokal ini. Hasil lokal bukan bukti eksekusi OS lain.
- Tunnel Cloudflare, Nginx, Docker, firewall dan identitas organisasi belum
  dideploy dalam pengujian ini. Contohnya disediakan untuk operator.
- BIOVIA desktop/lisensi dan docking penuh dengan Vina/OpenBabel eksternal belum
  diuji ulang secara end-to-end melalui browser. Regresi modul ilmiah lama tetap
  dijalankan; viewer memakai struktur sintetis, bukan hasil penelitian baru.
- Axe/emulasi mobile bukan sertifikasi aksesibilitas atau pengujian semua browser,
  pembaca layar, GPU dan perangkat fisik.
- PDF mempertahankan halaman vektor workshop asli; halaman WebUI baru memakai
  render PPTX yang sama dengan lapisan teks pencarian. Validator tata letak PPTX
  mencatat dua peringatan tabel pada materi lama; render PDF lama dipertahankan.

Penyempurnaan viewer, materi, animasi, sitasi dan updater otomatis diuji terpisah
pada [laporan interaktif terbaru](testing-webui-interactive.md).
