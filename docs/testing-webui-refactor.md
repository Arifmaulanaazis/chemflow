# Pengujian refaktor WebUI

Verifikasi lokal 17 Oktober 2026, Windows/Python 3.14/Node 22/Chrome headless.
Laporan ini menggantikan bukti UI sebelumnya untuk desain dan alur kerja terbaru.

| Pemeriksaan revisi ini | Hasil |
|---|---|
| API, keamanan, worker, interaksi browser, argumen, CLI, PubChem, gridbox, resume dan receptor-config | **139 lulus, 1 dilewati** |
| React/Vitest: login, wizard, error/draf, resume, SMILES, gridbox, numeric vector | **10 lulus** |
| Playwright desktop + mobile | **8 lulus**, tanpa retry |
| TypeScript dan build Vite produksi | Lulus |
| Wheel dan kesamaan seluruh file web/aset dengan source | Lulus |

Tes symlink dilewati karena izin Windows. Suite Python penuh sebelumnya
tercatat terpisah pada [laporan rilis](testing-3.0.0.md); 139 kasus di atas
merupakan suite fokus revisi ini, bukan penjumlahan dengan suite lama.

## Cakupan nyata

- Job CLI `init --skip-check` benar-benar membuat workbook, lalu log, tabel dan
  unduhannya diperiksa melalui browser. Viewer NGL benar-benar menggambar canvas
  WebGL dari fixture PDB; representasi, kontak dan gridbox diuji.
- Wizard diuji untuk validasi input, data ligan/reseptor yang dibuat melalui API,
  parameter CLI yang dicari, pilihan format, ringkasan, kembali ke langkah yang
  sudah dibuka, serta draf yang bertahan setelah navigasi.
- GC-MS diuji melalui unggah CSV, rentang angka, dan review. Uji browser ini tidak
  menjalankan analisis ilmiah GC-MS penuh; regresi CLI tetap diuji pada Python.
- Bridge SMILES/native/gridbox diuji dua arah melalui API dan fungsi prompt
  ilmiah. Satu tes memakai worker dan child Python nyata yang menunggu jawaban,
  menerima SMILES lewat API, lalu selesai. Password server tidak masuk env child.
- Jawaban SMILES tidak valid, ukuran/koordinat tidak valid, CSRF salah, jawaban
  ulang, permintaan job berhenti, dan ID executable palsu ditolak.
- Workbook ligan dibaca kembali menggunakan pembaca CLI; formula-like text tetap
  bertipe teks dalam Excel. Semua opsi argparse ilmiah dipetakan ke schema.
- Pilihan executable hanya menerima ID dari PATH/registrasi operator. Daftar versi
  Vina memakai manager lama dan cache yang diuji tanpa akses jaringan nyata.
- Browser: desktop 1440x1000, iPhone 13 390x844, serta pemeriksaan 375x812,
  tablet 768x1024 dan landscape 844x390. Navbar berada dalam viewport dan halaman
  tidak melebar horizontal. Menu dialog/Escape, reduced motion, tab log/hasil,
  Axe pada home/review/hasil/menu, serta galat JavaScript diperiksa.

Bukti lokal (diabaikan Git): `.cache/refactor-python-final.xml`,
`.cache/refactor-python-final.log`, `.cache/refactor-unit.log`,
`.cache/refactor-browser-final.log`, `.cache/browser-results.json`,
`.cache/refactor-build.log`, `.cache/refactor-wheel.log`,
`.cache/refactor-package-verification.json`.
Screenshot yang dapat ditinjau berada di `docs/assets/` dan memakai fixture
sintetis, bukan hasil penelitian.

## Mengulang pengujian

```sh
python -m pip install -e ".[web,test]"
python -m pytest tests/web tests/test_cli.py tests/test_pubchem_client.py tests/test_grid_box.py tests/test_resume.py tests/test_receptor_config.py -q
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Untuk mode server tes eksternal di Windows, ikuti [panduan pengujian
rilis](testing-3.0.0.md#menjalankan-ulang). Server tes hanya untuk loopback.

Pengujian lokal ini tidak menjalankan CI macOS/Linux, perangkat fisik, deploy
Cloudflare/Nginx/Docker, atau docking Vina/OpenBabel/BIOVIA penuh melalui browser.
Konfigurasi lintas OS dan batas ilmiah/operasional tetap berlaku.

Penyempurnaan viewer, materi, animasi, sitasi dan updater otomatis diuji terpisah
pada [laporan interaktif terbaru](testing-webui-interactive.md).
