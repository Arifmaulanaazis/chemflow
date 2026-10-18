# Verifikasi perbaikan 3.0.0

Dijalankan lokal pada 18 Oktober 2026.

| Pemeriksaan | Hasil |
| --- | --- |
| Suite Python lengkap | 920 lulus, 1 dilewati |
| API setelah pengurutan unggahan diperbarui | 28 lulus, 1 dilewati |
| Frontend | 18 lulus |
| Browser desktop dan ponsel: status proses dan viewer | 4 lulus |
| Viewer setelah rotasi dengan representasi cartoon | 2 lulus |
| TypeScript dan build produksi | Lulus |

Perintah:

```powershell
python -m pytest -q --basetemp=.cache/pytest-full-release --tb=short
python -m pytest tests/web/test_api.py -q --basetemp=.cache/pytest-upload-final --tb=short
cd frontend
npm run test
npm run build
npx playwright test --grep 'upload validation|navbar and progress' --reporter=line
```

`CHEMFLOW_TEST_BROWSER` menunjuk Chromium lokal bila path bawaan Playwright tidak tersedia.

Regresi mencakup koordinat per reseptor dan situs, checkpoint run sumber saat resume,
kompleks RMSD, path di luar workspace, metadata unggahan setelah muat ulang,
filter format/jenis input, nama berulang dan pilihan aktif, radar dua parameter
per ligan/grup, kamera pada viewport sempit, serta progres berjalan/menunggu/selesai.

Progress bar berjalan tanpa persentase karena pipeline saat ini hanya melaporkan
tahap, bukan persentase pekerjaan. Nilai 100 ditampilkan setelah job berhasil.
Tanpa checkpoint gridbox, kontrol dinonaktifkan; koordinat tidak diganti dengan nol.
Unggahan lama tanpa metadata tetap tersedia menurut formatnya.

Browser menggunakan protein fixture lokal, bukan docking baru melalui Vina/BIOVIA.
Screenshot desktop dan ponsel diperiksa untuk memastikan pita protein masuk layar,
koordinat terisi, serta badge dan progress bar terbaca tanpa overflow horizontal.
