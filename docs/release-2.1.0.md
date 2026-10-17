# chemflow 2.1.0

## Perubahan

- `run --rmsd-only`: preparasi reseptor/native, redocking dan RMSD tanpa input ligan uji,
  ADMET, atau analitik screening. `--ligands` diabaikan pada mode ini.
- Evaluasi semua pose dari seluruh replikat sukses. Pilih RMSD minimum dan catat
  mode, replikat, seed, afinitas, metode, serta penanda `selected_best`.
- `--rmsd-merge-mode best/all` dan `--rmsd-interaction-mode best/all` independen
  dari merge docking utama. Kompleks dan laporan berada di `rmsd/`.
- `interactions --rmsd` mengekspor set interaksi validasi yang disiapkan saat run.
  Manifest membatasi set aktif; kompleks lama buatan program dibersihkan jika
  tidak lagi dipilih. File lain tetap dipertahankan.
- Resolver Open Babel bersama untuk pipeline dan `init`: override, preferensi
  tersimpan, PATH, lalu lokasi instalasi umum. Path tersimpan per pengguna;
  cache kedaluwarsa/rusak diabaikan, override invalid tetap ditolak.
- README dan referensi RMSD diperbarui. PPT/PDF memuat 50 slide/halaman;
  angka demonstrasi dan benchmark lama diberi konteks arsip.

## Validasi pada 17 Oktober 2026

Pengujian terfokus:

- 121 tes fitur/regresi CLI, native, converter, system check, exporter interaksi,
  dan PDBQT lulus pada putaran fitur awal.
- 40 tes alur RMSD dan integrasi interaksi lulus, termasuk perhitungan RMSD asli
  tanpa superposisi serta penanganan kegagalan backend BIOVIA.
- 9 tes RMSD lulus setelah penambahan pembersihan hasil lama (`all` ke `best`).
- 6 tes pembaca PDBQT lulus, termasuk pelestarian nomor mode setelah model kosong.
  Putaran pengujian saling tumpang tindih; angka tersebut bukan jumlah tes unik.

Uji integrasi tool asli memakai Python 3.14, Open Babel 3.2.1 dan AutoDock Vina
1.2.7. Struktur PDB dan templat komponen berasal dari cache proyek sehingga tidak
membutuhkan jaringan. Exhaustiveness 1 dipakai untuk smoke test, bukan sebagai
rekomendasi protokol penelitian.

1. Resolver menemukan Open Babel di lingkungan conda di luar PATH dan berhasil
   menjalankan `obabel -V`; run berikutnya memakai preferensi tersimpan.
2. RMSD-only pada 1HCK/native ATP: dua replikat, tiga pose total. Laporan memuat
   RMSD 2.746, 2.559, dan 8.310 Angstrom. Terpilih replikat 2/mode 1 (2.559),
   menghasilkan satu kompleks merge `best` dan tiga kandidat interaksi `all`.
   Input `--ligands nonexistent-ignored.xlsx` berhasil diabaikan. Tidak ada
   workbook screening atau grafik analitik yang dibuat.
3. Resume memakai ulang satu reseptor, satu ligan native, dan dua run native dari
   checkpoint tanpa menjalankan Vina kembali.
4. Pipeline penuh (etanol dan reseptor 1HCK) dengan `--run-rmsd-validation`,
   merge docking `best`, merge RMSD `all`, dan interaksi RMSD `best` selesai
   dengan kode 0. Workbook serta kompleks utama dan RMSD tetap terpisah.

Ekspor GUI BIOVIA langsung tidak dijalankan; alur ekspor, routing folder, seleksi
pose, penanganan kegagalan, dan resume ekspor diuji lewat backend pengujian.

Pemeriksaan dokumen: halaman PDF dirender dan bagian yang berubah diperiksa
secara visual; jumlah slide/halaman, opsi baru, dan footer versi 2.1.0 diperiksa.
PowerPoint GUI tidak tersedia di sesi ini. PDF mempertahankan halaman/artwork
lama dan memperbarui teks yang berubah serta tiga halaman panduan baru.

Perintah regresi lengkap (folder sementara di dalam workspace):

```bash
python -m pytest --basetemp .cache/pytest-release -q --disable-warnings --tb=short
```


Hasil regresi lengkap: **841 passed** dalam 1816.74 detik (30 menit 16 detik),
tanpa kegagalan. Lima kasus ditambahkan setelah putaran lengkap mulai dikoleksi;
kelimanya lulus dalam putaran terfokus (empat kasus RMSD dan satu model PDBQT
kosong). Inventaris akhir berisi **846 kasus tes unik**. Seluruh perubahan akhir
pada seleksi/cleanup RMSD juga diverifikasi ulang melalui 9 tes RMSD yang lulus.

`git diff --check` dan kompilasi modul Python lulus. Skrip pembaruan presentasi
dijalankan ulang dan menghasilkan 50 slide dengan isi teks identik, tanpa label
duplikat. PDF akhir juga memiliki 50 halaman.
