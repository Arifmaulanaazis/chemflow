# Pembaruan workshop ChemFlow 3.0.0

Verifikasi lokal pada 18 Oktober 2026, Windows. Halaman 5, 7 dan 32 pada
PPTX/PDF diperbarui, termasuk salinan dalam `chemflow/resources` untuk WebUI.

| Pemeriksaan | Hasil |
| --- | --- |
| Sumber Python dalam `chemflow/**/*.py` | 16.934 baris, 88 berkas |
| Sumber WebUI dalam `frontend/src` (TS, TSX, CSS) | 10.244 baris, 47 berkas |
| Total sumber aplikasi | 27.178 baris, 135 berkas |
| Aset WebUI produksi dalam `chemflow/web/static` | 8.033.353 byte (7,66 MiB), 45 berkas |
| Pengumpulan pytest | 921 kasus dalam 64 berkas |
| Eksekusi pytest lengkap | 920 lulus, 1 dilewati, 126,64 detik |
| React / Vitest | 18 lulus dalam 4 berkas |
| TypeScript dan Vite produksi | Lulus |

Baris sumber dihitung dengan `splitlines()`, termasuk komentar dan baris kosong.
Tes, skrip pengembangan, `node_modules` dan hasil build tidak masuk hitungan
sumber aplikasi. Ukuran aset produksi dihitung terpisah dan menyertakan dependensi
yang dibundel, bukan ukuran wheel, lingkungan Python atau instalasi lengkap.

Grafik halaman 32 memakai jumlah **kasus terkumpul**, termasuk satu kasus yang
dilewati saat eksekusi. Berkas `tests/web/test_api.py` menyumbang 29 kasus, sudah
tercakup pada total Python; angka API tidak dijumlahkan ulang. Tes React dihitung
terpisah. Browser E2E tidak dijalankan ulang untuk perubahan dokumen ini.

Arsitektur halaman 7 mengikuti `docs/webui-architecture.md`: React/TypeScript
berkomunikasi dengan FastAPI, worker serial menyimpan job pada SQLite dan
menjalankan child CLI, kemudian CLI memakai modul ilmiah yang sama dengan library.

## Reproduksi

```powershell
python -m pytest -q --basetemp=.cache/pytest-docs-v3 --tb=short > .cache/release/docs-python-tests.log
cd frontend
npm run test > ../.cache/release/docs-frontend-tests.log
npm run build > ../.cache/release/docs-frontend-build.log
cd ..
python scripts/update_v3_workshop.py --python-log .cache/release/docs-python-tests.log --frontend-log .cache/release/docs-frontend-tests.log
```

Builder menulis draft pada `.cache/workshop-v3`. Validasi draft sebelum menyalin
ke dokumen utama dan resource paket. Grafik baru menggunakan data literal hasil
pengumpulan pytest; workbook Excel grafik dimaterialisasi saat finalisasi PPTX.
Halaman lain mempertahankan bagian OpenXML aslinya. PDF memakai render yang sama
dengan slide pengganti dan lapisan teks pencarian; 53 halaman lain diperiksa
memiliki hasil render identik dengan dokumen sebelumnya.
