<p align="center">
  <img src="../chemflow.png" alt="Logo chemflow: labu Erlenmeyer dengan dua simpul molekul" width="120">
</p>

<h1 align="center">Dokumentasi chemflow</h1>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.10 atau lebih baru" src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="../LICENSE"><img alt="Lisensi MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="../pyproject.toml"><img alt="Versi 3.0.0" src="https://img.shields.io/badge/version-3.0.0-3C71E8"></a>
  <img alt="Platform Windows, macOS, dan Linux" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey">
  <img alt="Docking dengan AutoDock Vina" src="https://img.shields.io/badge/docking-AutoDock%20Vina-8E70EB">
  <img alt="Kemoinformatika dengan RDKit" src="https://img.shields.io/badge/cheminformatics-RDKit-8E70EB">
  <img alt="Konversi format dengan Open Babel" src="https://img.shields.io/badge/converter-Open%20Babel-8E70EB">
</p>

Untuk instalasi, cara pakai, dan panduan langkah-demi-langkah (termasuk
untuk pengguna yang belum pernah memakai terminal), lihat
[`README.md`](../README.md) di root repo. Halaman di folder ini adalah
referensi teknis lanjutan: diagram alur algoritma tiap tahap pipeline,
ditulis sebagai Mermaid flowchart (render otomatis di GitHub, GitLab, dan
kebanyakan editor Markdown).

- [Catatan rilis dan pengujian 2.1.0](release-2.1.0.md)
- [Alur Utama Pipeline (termasuk Resume dan checkpoint)](pipeline-overview.md)
- [Preparasi Ligan](ligand-preparation.md)
- [Preparasi Reseptor](receptor-preparation.md)
- [Konfigurasi Reseptor Interaktif](receptor-config.md)
- [Docking (Resolusi Vina & Matriks)](docking.md)
- [Validasi RMSD Redocking dan Ligan Native](rmsd-validation.md)
- [Merge Kompleks & Analitik (PCA gaya jurnal, HCA, Heatmap, Grafik per Grup, Pemotongan Grafik)](merge-and-analytics.md)
- [Ekspor Interaksi Otomatis dari BIOVIA (termasuk penguncian input)](biovia-interactions.md)
- [Analisis Similaritas Interaksi](similarity-analysis.md)
- [Analisis GC-MS (opsional)](gcms-analysis.md)
- [Pemakaian sebagai Library](library-usage.md)

## Tentang

chemflow merangkai seluruh alur skrining virtual (preparasi, ADMET, docking
AutoDock Vina, validasi RMSD, analitik) dalam satu perintah, dengan analisis GC-MS opsional. Dikembangkan oleh
Arif Maulana Azis dan dirilis dengan lisensi MIT. Ringkasan proyek, versi,
dan tautan repositori ada di bagian [Tentang](../README.md#tentang) pada
`README.md`.


## WebUI 3.0.0

- [Instalasi, penggunaan, LAN dan Cloudflare Tunnel](webui.md)
- [Arsitektur modular, API, sesi, antrean dan keamanan](webui-architecture.md)
- [Sistem desain dan komponen atomic](design/webui.md)
- [Catatan rilis 3.0.0](release-3.0.0.md)
- [Pengujian dan batas validasi](testing-3.0.0.md)

- [Inventaris sumber dan keputusan integrasi 3.0.0](source-review-3.0.0.md)

- [Refaktor UX dan pengujian terbaru](testing-webui-refactor.md)

- [Interaksi, viewer, materi, sitasi dan updater otomatis](webui.md#materi-sitasi-dan-grafik)
- [Pengujian penyempurnaan interaktif](testing-webui-interactive.md)
- [Pengujian browser nyata (docking, GC-MS, BIOVIA, ponsel)](testing-webui-browser-nyata.md)
