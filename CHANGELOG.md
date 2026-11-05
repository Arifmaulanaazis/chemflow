# Riwayat Perubahan

## Belum dirilis

- Preprint baru (bahasa Inggris) di `paper/chemflow_preprint.pdf`; bibliografi ber-DOI diverifikasi ke Crossref. Preprint lama dihapus.

## 3.1.0

- Validasi RMSD redocking aktif secara bawaan (`run_rmsd_validation=True`, `rmsd_backend="auto"`, `rmsd_overlay=True`).
- Referensi RMSD kini berasal dari koordinat kristal ligan native, bukan dari ligan hasil embedding SMILES. Pemetaan atom berat memperhitungkan simetri dan konektivitas.
- Backend `auto` memakai BIOVIA Discovery Studio di Windows untuk menghitung RMSD dan mengekspor gambar overlay. Jika BIOVIA tidak tersedia atau gagal, perhitungan beralih ke RDKit dan alasannya dicatat; overlay tidak dibuat.
- Overlay memakai warna sian untuk native kristal dan oranye untuk pose hasil docking, keduanya dalam koordinat reseptor tanpa superposisi.
- Workbook memisahkan RMSD minimum seluruh pose (`rmsd_angstrom`) dari RMSD pose berafinitas terbaik (`rmsd_affinity_best_angstrom`).
- Opsi baru: `--rmsd-backend {auto,rdkit}` dan `--no-rmsd-overlay`.
- Embedding 3D ligan mencoba `enforceChirality=False` sebelum fallback lain bila embedding dengan chirality gagal.

## 3.0.0

- WebUI (React, TypeScript, Vite) dengan backend FastAPI. CLI dan library Python tidak berubah.
- Autentikasi kata sandi operator, sesi HttpOnly, CSRF, pemeriksaan Origin/Host, dan batas ukuran unggahan. Bawaannya hanya localhost.
- Antrean job persisten dengan log, tahap proses, pembatalan, dan resume.
- Wizard empat langkah; ligan dan reseptor dapat disusun langsung di browser. Konfirmasi SMILES dan pemilihan ligan native muncul sebagai formulir.
- Viewer 3D (NGL) untuk reseptor, pose, ligan native, dan gridbox; pratinjau tabel dan grafik hasil; pembaca materi PDF.
- Pembaruan otomatis dari rilis GitHub stabil ke runtime terisolasi yang terverifikasi, dengan restart hanya saat antrean kosong.
- Versi minimum Python menjadi 3.10; dependensi opsional `web`.

## 2.1.0

- `run --rmsd-only`: validasi redocking native tanpa input ligan uji, ADMET, atau analitik skrining.
- Semua pose dari seluruh replikat dievaluasi; pose dengan RMSD minimum dipilih.
- `--rmsd-merge-mode` dan `--rmsd-interaction-mode` (`best`/`all`) bekerja terpisah dari merge docking utama. Hasil berada di `rmsd/`.
- `interactions --rmsd` mengekspor interaksi untuk kompleks validasi.
- Resolver OpenBabel bersama untuk pipeline dan `init`: argumen, preferensi tersimpan, `PATH`, lalu lokasi instalasi umum.

## 2.0.0

- Paket analisis GC-MS (`chemflow gcms`): penyelarasan, deteksi puncak, PCA, HCA, PLS-DA, volcano plot, skrining alergen.
- PCA bergaya jurnal dengan elips kepercayaan 95%.
- Similaritas interaksi otomatis setelah ekspor BIOVIA, dengan penguncian input selama otomasi GUI.
