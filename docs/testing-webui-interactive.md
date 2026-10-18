# Verifikasi penyempurnaan interaktif 3.0.0

Pengujian aktual pada Windows, 17 Oktober 2026. Chrome dijalankan pada viewport
desktop 1440×1000 dan emulasi iPhone 13, dengan WebGL SwiftShader. Server tes
loopback memakai workspace sementara, autentikasi nyata dan updater jaringan
dinonaktifkan. CLI ilmiah tetap diuji dengan suite regresi repository.

| Pemeriksaan | Hasil |
| --- | --- |
| Suite Python penuh | 915 lulus, 1 dilewati |
| Pengujian lanjutan lifecycle/update/sitasi | 31 lulus |
| Pengujian ulang updater dengan venv tanpa dependensi warisan | 17 lulus |
| Komponen Vitest | 13 lulus |
| Skenario browser desktop/mobile | 14 lulus |
| Pemeriksaan tambahan pembaca PDF/mobile setelah materi diperbarui | 2 lulus |
| TypeScript + Vite production build | Lulus |
| npm audit | 0 kerentanan terlapor |
| Compileall dan git diff --check | Lulus |

Suite penuh dijalankan sebelum perbaikan penutupan SSE saat update dan format
nama author BibTeX. Pengujian lanjutan 31 tes memverifikasi modul tersebut setelah
perubahan terakhir. Satu skip merupakan kondisi platform/fitur pada suite lama.

## Cakupan interaksi dan visual

- Logo menggunakan `chemflow.png` asli pada login dan shell.
- Molekul berulang berubah transform, dapat dijeda, dan bounding rect tetap di
  dalam hero. Screenshot mobile diperiksa untuk clipping dan navbar bawah.
- Dropdown custom diuji keyboard, nilai terpilih, opsi disabled, Escape dan
  multiple selection. Checkbox, dialog dan disclosure mempertahankan semantik.
- PDF asli 56 halaman dirender oleh PDF.js lokal; navigasi keyboard sampai
  halaman 56 memeriksa teks updater baru. Sitasi dan unduhan BibTeX memerlukan
  autentikasi. Endpoint PDF/PPT dan penolakan format/path tidak valid diuji.
- Viewer reseptor memakai data RCSB **1HSG nyata**, fixture tersimpan dengan
  provenance. Native MK1_B902 dikenali dari PDB. Protein, native dan box tampil
  dalam canvas NGL. Mengubah center/size memeriksa delapan sudut serta perubahan
  piksel WebGL; pemilihan native/manual mengubah state dan koordinat.
- Geometri unit memeriksa delapan sudut unik, dua belas sisi dan penanda pusat,
  termasuk ukuran negatif/nonfinite yang ditolak. Ini menguji geometri yang
  benar-benar dipakai oleh kedua viewer.
- Grafik memakai CSV fixture yang secara eksplisit sintetis. Tooltip angka,
  pilihan seri, mode garis dan ekspor SVG diuji tanpa mengganti data kosong ke nol.
- Axe melaporkan nol pelanggaran pada halaman yang diuji. Skenario lama mencakup
  autentikasi, CSRF, job CLI nyata, upload, checkpoint, navigasi dan reduced motion.

## Updater

Fixture release wheel 9.9.9 dipasang dengan pip ke venv baru, diimpor, diverifikasi
dan dijalankan sungguhan. Pointer aktivasi diperiksa; versi checkout tetap 3.0.0.
Tidak ada release eksternal yang dipasang pada environment pengguna.

Tes mencakup cache/backoff, penolakan downgrade/prerelease/path versi berbahaya,
URL release resmi, checksum, traversal ZIP/backslash/symlink, batas pointer,
penghapusan runtime parsial dan pelestarian pointer lama saat gagal. Lifecycle
WebUI menguji antrean kosong, blok enqueue saat maintenance, restart setelah
verifikasi, pemulihan maintenance saat gagal, dan penutupan stream SSE agar
restart tidak menunggu koneksi realtime tanpa batas. Login valid antarperangkat
tidak menghabiskan kuota kata sandi salah; percobaan salah tetap dibatasi.

## Distribusi dan materi

Wheel dibangun dari source dan aset production yang sama. Semua modul Python,
aset static bersarang, PDF dan PPTX dibandingkan byte-per-byte dengan workspace;
file hash lama dari build sebelumnya tidak disertakan.
Smoke test pemasangan wheel melalui target terpisah juga mengimpor paket yang
terpasang dan memeriksa SPA, autentikasi, PDF/PPT serta versi BibTeX. Target tes
`--no-deps` memakai dependensi host yang sudah tersedia; updater produksi membuat
venv bersih dan memasang dependensi release ke dalamnya.

PPTX 56 slide lolos pemeriksaan struktur, import Artifact Tool, lima chart native
dan konsistensi workbook/cache. Enam slide appendix dirender dan diperiksa
visual. PDF 56 halaman mempertahankan workshop asli dan memakai render appendix
yang sama beserta lapisan teks pencarian. Dua peringatan geometri tabel lama
pada slide 30/37 tetap tercatat dalam validator, sebagaimana laporan sebelumnya.

## Menjalankan ulang

```sh
CHEMFLOW_SKIP_UPDATE=1 python -m pytest -q --basetemp=.cache/pytest-local
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Pada PowerShell tetapkan `$env:CHEMFLOW_SKIP_UPDATE='1'` sebelum menjalankan
pytest. CI juga menonaktifkan bootstrap jaringan; unit updater memakai fixture
sendiri. Konfigurasi browser ada di `frontend/playwright.config.ts`.

Artefak visual: [mobile](assets/webui-mobile.png),
[gridbox nyata](assets/webui-gridbox.png),
[pembaca materi](assets/webui-library-mobile.png),
[grafik fixture](assets/webui-chart.png).

macOS/Linux disiapkan dalam matriks CI, belum dieksekusi secara fisik pada sesi
Windows ini. Pengujian tidak mengklaim docking penuh dengan executable eksternal,
perangkat mobile fisik, semua GPU/browser, deployment tunnel atau aktivasi release
GitHub produksi. Nilai fixture dan visualisasi bukan hasil penelitian baru.


## Revisi hero: ilustrasi awal dalam ruang 3D

Ilustrasi awal dipertahankan: dua belas simpul berwarna, rangka heksagonal dan dua
kurva orbital. Model ball-and-stick dibatalkan sesuai koreksi pengguna. Three.js
menempatkan elemen ilustrasi dalam ruang 3D, dengan kemiringan multi-sumbu,
parallax, orbital bergerak dan kontrol OrbitControls. Tombol jeda dihapus.

Pemeriksaan browser desktop/mobile menguji canvas WebGL2, perubahan piksel saat
animasi berjalan, drag mouse, keyboard rotate/zoom/reset, bounding rect di dalam
hero, serta drag dan pinch melalui event sentuh Chromium pada mode mobile.
Kehilangan konteks WebGL menampilkan fallback tanpa merusak workspace; navigasi
kembali membuat tepat satu canvas baru. Empat pemeriksaan terarah ini lulus;
13 tes komponen lulus. Screenshot desktop/mobile diperiksa langsung.

Setelah revisi hero, suite browser lengkap dijalankan ulang: **16 lulus** pada
desktop/mobile. Build TypeScript/Vite dan npm audit juga lulus (0 kerentanan
terlapor). Tidak ada perubahan perhitungan ilmiah atau backend pada revisi ini.

Revisi partikel orbital: empat tes browser terarah desktop/mobile lulus,
termasuk animasi WebGL, kontrol, hilangnya petunjuk visual, fallback dan remount.
Build TypeScript/Vite lulus. Empat partikel mengikuti parent garis orbital,
dengan geometri/material bersama yang dibersihkan saat scene ditutup.
