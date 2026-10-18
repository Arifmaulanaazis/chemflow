# Pengujian browser nyata WebUI 3.0.0

Pengujian ini menjalankan seluruh alur lewat klik dan isian di Chromium (Playwright),
bukan hanya uji unit. Server dijalankan dengan `python -m chemflow web` pada workspace
sementara, memakai jaringan sungguhan (RCSB, PubChem, ADMETLab3, GitHub) serta Vina 1.2.7,
Open Babel, dan BIOVIA Discovery Studio 2021 yang terpasang di mesin uji (Windows 10).
Tanggal: 18 Oktober 2026.

| Alur | Langkah di browser | Hasil |
|---|---|---|
| Login | Masuk dengan kata sandi workspace | Berhasil; sesi terbentuk |
| Docking (screening) | Unggah `ligan.xlsx`; buat workbook reseptor 1HSG di browser (cari native, gridbox, NGL); atur exhaustiveness/pose/seed; tinjau; jalankan | Selesai, exit 0. PubChem 5/5, ADMET 5/5, 6 docking sukses (native −10,58 kcal/mol), 113 berkas |
| Hasil | Penampil NGL kompleks (kontak dan gridbox), pratinjau workbook, grafik interaktif, unduh XLSX dan SVG, 51 plot | Seluruhnya tampil dan terunduh |
| Template input | Jalankan alur Template input | 3 workbook contoh dibuat |
| Input runtime | Ligan dari builder tanpa SMILES, reseptor tanpa gridbox | Form SMILES muncul (SMILES invalid ditolak, valid diterima), lalu form gridbox native; job selesai |
| Validasi RMSD | Centang Validasi RMSD saja | Selesai, `hasil_rmsd.xlsx` dibuat |
| Batal | Tombol Hentikan, konfirmasi | Status Dibatalkan; tidak ada proses Vina/Open Babel yatim |
| Lanjutkan checkpoint | Lanjutkan run yang dibatalkan | Selesai; BIOVIA terdeteksi dan menjalankan ekspor interaksi serta similaritas otomatis |
| Similaritas dan interaksi mandiri | Alur Similaritas interaksi dan Ekspor interaksi BIOVIA | Keduanya selesai, exit 0 |
| GC-MS | Unggah 6 berkas kromatogram sintetis, pilih sebagai data | Selesai; 26 artefak (PCA, HCA, PLS-DA, LDA, kemiripan) |
| Materi | Pembaca PDF 56 halaman, sitasi BibTeX | Tampil |
| Pengaturan, mesin, panduan | Buka tiap halaman | CPU/RAM/disk langsung, status versi GitHub tampil |
| Ponsel 390 px | Beranda, wizard, hasil, menu Lainnya | Tanpa gulir horizontal; navbar bawah berfungsi |
| Keamanan sesi | Keluar, dua belas percobaan sandi salah | Pesan galat jelas; pembatasan laju aktif setelah 10 percobaan |
| Restart server | Hentikan dan jalankan ulang server | 7 job tetap tersimpan; sesi lama dibatalkan |

## Temuan dan perbaikan

- **Diperbaiki.** Alur GC-MS gagal dengan exit code 2 (`unrecognized arguments: --no-progress`)
  karena server menambahkan `--no-progress` ke semua perintah, padahal subperintah `gcms`
  tidak memilikinya. `chemflow/web/schema.py` kini menambahkannya hanya bila parser
  perintah tersebut mendefinisikannya. Uji regresi
  `test_generated_argv_is_accepted_by_cli_parser` memastikan argv bentukan server lolos
  parser CLI asli untuk setiap perintah WebUI.
- **Catatan.** Tombol Fit pada penampil kompleks memperbesar ke ligan sehingga pita protein
  terpotong bidang dekat kamera; Reset menampilkan seluruh struktur. Gridbox pada penampil
  hasil bernilai awal 0,0,0 dan diisi manual, tidak mengikuti kotak docking run.
- **Batas.** Daftar berkas unggahan yang sama muncul pada tiap pilihan berkas, sehingga
  nama yang sama dapat tampil berulang. ADMETLab3 sempat membalas HTTP 429; pipeline
  mencoba ulang otomatis dan berhasil.
