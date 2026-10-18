<p align="center">
  <img src="chemflow.png" alt="Logo chemflow: labu Erlenmeyer dengan dua simpul molekul" width="160">
</p>

<h1 align="center">chemflow</h1>

<p align="center">
  <strong>Platform Otomasi Skrining Virtual Senyawa Obat, Kemometrik, &amp; Analitik Molekuler</strong><br>
  Dari dua file Excel (senyawa &amp; reseptor) hingga preparasi struktur, prediksi ADMET, molecular docking AutoDock Vina, validasi RMSD, similaritas interaksi, dan grafik siap publikasi.
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.10 atau lebih baru" src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="Lisensi MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="pyproject.toml"><img alt="Versi 3.0.0" src="https://img.shields.io/badge/version-3.0.0-3C71E8"></a>
  <img alt="Platform Windows, macOS, dan Linux" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey">
  <img alt="Docking dengan AutoDock Vina" src="https://img.shields.io/badge/docking-AutoDock%20Vina-8E70EB">
  <img alt="Kemoinformatika dengan RDKit" src="https://img.shields.io/badge/cheminformatics-RDKit-8E70EB">
  <img alt="Konversi format dengan Open Babel" src="https://img.shields.io/badge/converter-Open%20Babel-8E70EB">
  <a href="docs/README.md"><img alt="Dokumentasi teknis" src="https://img.shields.io/badge/docs-referensi%20teknis-3C71E8"></a>
</p>

<p align="center">
  <a href="#ruang-kerja-webui-baru-di-v300">Preview WebUI</a> ·
  <a href="#video-tutorial">Video Tutorial</a> ·
  <a href="#fitur-utama">Fitur Utama</a> ·
  <a href="#2-instalasi">Instalasi</a> ·
  <a href="#5-menjalankan-pipeline">Menjalankan Pipeline</a> ·
  <a href="#7-membaca-hasil">Membaca Hasil</a> ·
  <a href="#10-jika-terjadi-error">Troubleshooting</a> ·
  <a href="docs/README.md">Dokumentasi Teknis</a>
</p>

---

## Ringkasan

**chemflow** menyediakan antarmuka **WebUI modern**, **baris perintah (CLI)**, dan **library Python** untuk menjalankan alur skrining virtual senyawa obat secara otomatis. Cukup siapkan dua file Excel (daftar senyawa uji dan daftar protein target), lalu **chemflow** akan:

1. Menyiapkan struktur 3D ligan (RDKit + OpenBabel) dan membersihkan reseptor protein (hidrogen polar + muatan Kollman).
2. Menghitung sifat fisikokimia (*Lipinski Rule of Five*) dan memprediksi profil **ADMET** (via ADMETLab 3.0 atau file CSV/Excel).
3. Menjalankan *molecular docking* otomatis menggunakan **AutoDock Vina** (mendukung multi-reseptor, multi-situs, dan replikasi) beserta redocking **ligan native** & **validasi RMSD**.
4. Menggabungkan kompleks protein–ligan, mengekspor interaksi 2D/Non-bond via **BIOVIA Discovery Studio** (opsional, Windows), serta menghasilkan laporan Excel terformat dan grafik 300 dpi siap publikasi (bar, radar, heatmap terklaster, PCA 2D/3D, dan dendrogram HCA).

> **Tidak perlu keahlian coding.** Panduan ini disusun langkah demi langkah sehingga dapat diikuti baik oleh pengguna baru yang belum terbiasa memakai terminal maupun pengguna lanjutan.

| Informasi | Keterangan |
| :--- | :--- |
| **Nama & Versi** | `chemflow` v3.0.0 |
| **Antarmuka** | WebUI (`python -m chemflow web`), CLI (`chemflow` / `python -m chemflow`), dan Library Python |
| ** Lingkungan** | Python 3.10+ (Node.js 22 LTS hanya bila membangun ulang bundel frontend WebUI) |
| **Komponen Inti** | RDKit, OpenBabel, AutoDock Vina, ADMETLab 3.0 |
| **Materi Ringkas** | Slide Presentasi ([`chemflow.pptx`](chemflow.pptx)) · Dokumen Materi ([`chemflow.pdf`](chemflow.pdf)) |
| **Lisensi & Penulis** | [MIT License](LICENSE) · Arif Maulana Azis ([@Arifmaulanaazis](https://github.com/Arifmaulanaazis)) |

---

## Ruang Kerja WebUI (Baru di v3.0.0)

Versi **3.0.0** menghadirkan **WebUI modular** yang responsif untuk desktop dan perangkat mobile, mendampingi antarmuka CLI yang tetap dipertahankan sepenuhnya.

![Preview animasi ChemFlow WebUI: login, overview, wizard, hasil, viewer 3D dan materi PDF](docs/assets/webui-preview.gif)

<p align="center">
  <a href="docs/assets/webui-preview-poster.png">Poster Statis</a> ·
  <a href="docs/webui-preview.md">Urutan Demo &amp; Cara Merekam Ulang</a> ·
  <a href="docs/assets/webui-desktop.png">Tampilan Desktop</a> ·
  <a href="docs/assets/webui-mobile.png">Tampilan Mobile</a> ·
  <a href="docs/assets/webui-molecule.png">Viewer Molekuler 3D</a> ·
  <a href="docs/assets/webui-wizard.png">Wizard Konfigurasi</a>
</p>

### Keunggulan Ruang Kerja WebUI
- **Wizard 4 Langkah & Input Langsung**: Unggah atau susun daftar ligan/reseptor langsung dari browser, mendukung desktop dan mobile.
- **Prompt Interaktif di Browser**: Saat pipeline membutuhkan konfirmasi SMILES (fallback PubChem) atau pemilihan ligan native untuk *gridbox*, formulir interaktif muncul langsung di WebUI.
- **Pemantauan Real-Time**: Manajemen antrean eksperimen, *checkpoint/resume*, *live log*, serta metrik penggunaan CPU, RAM, dan penyimpanan.
- **Eksplorasi Hasil & Viewer 3D NGL**: Pratinjau struktur PDB, pose docking, ligan native, dan *gridbox* interaktif yang mengikuti koordinat XYZ; pratinjau tabel numerik dengan grafik interaktif (ekspor SVG); serta pembaca materi PDF/PPT/BibTeX bawaan.
- **Pembaruan Rilis Otomatis**: CLI dan WebUI dapat memeriksa serta memasang rilis stabil GitHub pada *runtime* terpisah yang terverifikasi (menunggu antrean kosong sebelum *restart*).

### Menjalankan WebUI
```sh
python -m pip install -e ".[web]"
cd frontend
npm ci
npm run build
cd ..
python -m chemflow web
```

1. Buka `http://127.0.0.1:8000` di browser.
2. Masuk menggunakan kata sandi acak yang tercetak di terminal, atau atur variabel lingkungan `CHEMFLOW_WEB_PASSWORD` (minimal 12 karakter).
3. **Akses LAN**: `python -m chemflow web --host 0.0.0.0 --allowed-host 192.168.1.20`
4. **Akses Tunnel HTTPS**: Gunakan domain eksplisit, opsi `--secure-cookie`, dan kebijakan *Cloudflare Access*.

> **Dokumentasi WebUI & Rilis 3.0.0:**
> [Panduan WebUI, LAN & Tunnel](docs/webui.md) ·
> [Arsitektur & Keamanan](docs/webui-architecture.md) ·
> [Catatan Rilis 3.0.0](docs/release-3.0.0.md) ·
> [Pengujian Rilis 3.0.0](docs/testing-3.0.0.md) ·
> [Pengujian Refaktor WebUI](docs/testing-webui-refactor.md)

---

## Video Tutorial

<div align="center">
  <a href="https://www.youtube.com/watch?v=QM-KQ9XpmWk" target="_blank" rel="noopener noreferrer">
    <img src="https://img.youtube.com/vi/QM-KQ9XpmWk/maxresdefault.jpg" alt="Video tutorial chemflow" width="720">
  </a>
  <p>
    <a href="https://www.youtube.com/watch?v=QM-KQ9XpmWk" target="_blank" rel="noopener noreferrer"><strong>▶ Putar Video Tutorial chemflow di YouTube</strong></a>
  </p>
</div>

---

## Fitur Utama

### 1. Preparasi Struktur & Konfigurasi Otomatis
- **Preparasi Ligan**: Input SMILES (atau nama senyawa yang dicari otomatis di PubChem) diproses oleh RDKit (netralisasi, penambahan H, minimisasi energi MMFF94/UFF, muatan Gasteiger, dan gambar struktur 2D), lalu dikonversi ke `.pdbqt` melalui OpenBabel.
- **Preparasi Reseptor**: Struktur PDB diunduh dari RCSB, dibersihkan dari molekul air dan ligan non-protein (residu termodifikasi pada rantai protein tetap dipertahankan lewat deteksi *backbone* struktural), kemudian ditambahkan hidrogen polar dan muatan Kollman.
- **Konfigurasi Gridbox Interaktif (`receptor-config`)**: Cukup masukkan kode PDB, pilih ligan native dari daftar yang terdeteksi, dan koordinat pusat serta ukuran *gridbox* dihitung secara otomatis.

### 2. Molecular Docking, Ligan Native, & Validasi RMSD
- **AutoDock Vina Otomatis**: Biner AutoDock Vina diunduh otomatis sesuai sistem operasi dan arsitektur mesin tanpa perlu mengatur `PATH`. Mendukung banyak reseptor, banyak situs ikat (*multi-site*), serta replikasi dengan perhitungan rata-rata dan simpangan baku $\Delta G$.
- **Pembanding Ligan Native**: Ligan kokristal diekstrak dari struktur PDB, di-*redock* dengan parameter yang sama seperti ligan uji, dan disertakan ke seluruh analitik sebagai grup **Native**.
- **Validasi RMSD (Terpadu atau Mandiri `--rmsd-only`)**: Menghitung RMSD seluruh pose hasil *redocking* ligan native terhadap posisi kristal aslinya tanpa superposisi (kriteria valid $\le 2,0\text{ \AA}$).
- **Penggabungan Kompleks (`merge`)**: Menggabungkan pose hasil docking dengan reseptor bersih menjadi file `.pdb` kompleks siap visualisasi (`--merge-mode best` atau `all`).

### 3. Sifat Fisikokimia, ADMET, & Analitik Kemometrik
- **Fisikokimia & ADMET**: Perhitungan *Lipinski Rule of Five* dan profil ADMET lengkap dari ADMETLab 3.0 (otomatis maupun dari file `--admet-file`) dengan pewarnaan sel Excel hijau/kuning/merah sesuai ambang batas ilmiah.
- **Grafik Siap Publikasi (300 dpi, PNG/SVG/PDF)**: Peringkat afinitas, radar gabungan, radar & distribusi klasifikasi per kategori ADMET, heatmap afinitas & fisikokimia terklaster, **PCA 2D/3D** bergaya jurnal (dengan elips kepercayaan 95%), **dendrogram HCA**, serta grafik perbandingan antar-grup.
- **Pemotongan Grafik Otomatis (*Paging*)**: Dataset berukuran besar otomatis dibagi menjadi beberapa halaman (`_part01of03`, dst.) dengan skala sumbu dan warna yang konsisten.

### 4. Ekstensi & Keandalan Pipeline
- **Checkpoint & Resume (`chemflow resume`)**: Setiap tahapan disimpan ke `_state/`. Jika terminal tertutup, terkena `Ctrl+C`, atau komputer mati, eksekusi dapat dilanjutkan dari titik terakhir tanpa mengulang tahapan yang sudah selesai.
- **Otomasi Interaksi BIOVIA & Similaritas (Windows)**: Mengekspor diagram interaksi 2D dan tabel *Non-bond* secara otomatis melalui GUI BIOVIA Discovery Studio, lalu menghitung indeks similaritas interaksi terhadap ligan native (metode Pratama et al., 2021).
- **Kemometrik GC-MS Opsional (`chemflow gcms`)**: Penyelarasan kromatogram, deteksi puncak, PCA, HCA, PLS-DA (skor VIP & uji permutasi), volcano plot (koreksi FDR), dan skrining alergen wewangian.

---

## Daftar Isi Panduan

1. [Yang Perlu Disiapkan](#1-yang-perlu-disiapkan)
2. [Instalasi](#2-instalasi)
3. [Uji Coba Pertama](#3-uji-coba-pertama)
4. [Menyiapkan Data Input (Excel)](#4-menyiapkan-data)
   - [4.1 Excel Senyawa (Ligan)](#41-excel-senyawa-ligan)
   - [4.2 Excel Protein (Reseptor) & Gridbox](#42-excel-protein-reseptor)
5. [Menjalankan Pipeline](#5-menjalankan-pipeline)
   - [5.1 Melanjutkan Run yang Terhenti (`resume`)](#51-melanjutkan-run-yang-terhenti-resume)
   - [5.2 Ligan Native sebagai Pembanding](#52-ligan-native-sebagai-pembanding)
   - [5.3 Validasi RMSD Mandiri (`--rmsd-only`)](#53-validasi-rmsd-mandiri---rmsd-only)
6. [ADMET: Otomatis atau dari File](#6-admet-otomatis-atau-dari-file)
7. [Membaca Hasil & Struktur Folder](#7-membaca-hasil)
8. [Analisis Similaritas Interaksi (BIOVIA)](#8-analisis-similaritas-interaksi)
9. [Analisis GC-MS (Opsional)](#9-analisis-gc-ms-opsional)
10. [Jika Terjadi Error (Troubleshooting)](#10-jika-terjadi-error)
11. [Untuk Pengguna Lanjutan (Opsi CLI, Library Python, & Referensi)](#11-untuk-pengguna-lanjutan)

---

## 1. Yang Perlu Disiapkan

| Kebutuhan | Kegunaan | Wajib? |
| :--- | :--- | :---: |
| **Koneksi Internet** | Mengunduh struktur PDB (RCSB), mencari SMILES (PubChem), mengunduh AutoDock Vina (GitHub), dan mengakses ADMETLab 3.0. | **Ya** |
| **Python 3.10+** | Menjalankan **chemflow** (CLI, WebUI, maupun library). | **Ya** |
| **OpenBabel** | Konversi struktur kimia ke format `.pdbqt`. Satu-satunya aplikasi eksternal yang dipasang manual. | **Ya** |
| **Aplikasi Spreadsheet** | Microsoft Excel, LibreOffice Calc, atau Google Sheets untuk mengisi daftar ligan dan reseptor. | **Ya** |
| **BIOVIA Discovery Studio** | *(Khusus Windows)* Ekspor otomatis diagram interaksi 2D & tabel *Non-bond* untuk analisis similaritas. Edisi *Visualizer* gratis sudah cukup. | Tidak |

> **Catatan:** Anda **tidak perlu** menginstal AutoDock Vina secara manual. **chemflow** akan mengunduh biner yang sesuai dengan OS/arsitektur komputer Anda secara otomatis.

---

## 2. Instalasi

Langkah di bawah menggunakan contoh pada Windows. Untuk macOS dan Linux, urutannya sama (cukup sesuaikan cara instalasi Python dan OpenBabel).

### 2.1 Pasang Python
1. Unduh installer Python 3.10+ dari [python.org/downloads](https://www.python.org/downloads/).
2. Pada layar pertama installer, **centang `Add python.exe to PATH`**, lalu klik **Install Now**.
3. Buka **Command Prompt** (`Win + R`, ketik `cmd`, tekan Enter) dan pastikan Python terdeteksi:
   ```bash
   python --version
   ```

### 2.2 Pasang chemflow dan Dependency
Ekstrak folder **chemflow** (atau jalankan `git clone`), masuk ke direktori proyek, lalu pasang paketnya:
```bash
cd D:\lokasi\chemflow
pip install -r requirements.txt
pip install -e .
```
*(Tambahkan `pip install -e ".[web]"` bila ingin menggunakan fitur WebUI).*

### 2.3 Pasang OpenBabel
Pilih **salah satu** dari dua metode berikut:

- **Cara A — Melalui Miniconda (Direkomendasikan):**
  1. Pasang [Miniconda](https://docs.conda.io/en/latest/miniconda.html).
  2. Buka **Anaconda Prompt** lalu jalankan:
     ```bash
     conda create -n chemflow_tools -c conda-forge openbabel -y
     conda run -n chemflow_tools where obabel
     ```
  3. Catat path `obabel.exe` yang muncul untuk diberikan satu kali lewat opsi `--openbabel-path` pada saat menjalankan **chemflow**.

- **Cara B — Melalui Installer Resmi:**
  Unduh installer dari [openbabel.org](https://openbabel.org), jalankan instalasi, lalu buka Command Prompt baru dan uji dengan `obabel -V`.

> **Deteksi & Penyimpanan Lokasi OpenBabel Otomatis:**
> **chemflow** mencari `obabel` secara berurutan melalui: argumen `--openbabel-path`, preferensi tersimpan, variabel `PATH`, lokasi instalasi umum Windows (`Program Files`/registry), environment Conda, hingga paket Python OpenBabel. Begitu ditemukan, lokasinya disimpan otomatis di `%LOCALAPPDATA%/chemflow/openbabel.json` (Windows) atau `~/.config/chemflow/openbabel.json` (Linux/macOS) sehingga tidak perlu diketik ulang pada eksekusi berikutnya.

### 2.4 Cek Kesiapan Sistem (`init`)
```bash
python -m chemflow init --output contoh/
```
Perintah ini membuat file template Excel contoh sekaligus memeriksa kelengkapan library Python, lokasi OpenBabel, ketersediaan AutoDock Vina, dan koneksi ke layanan online.

---

## 3. Uji Coba Pertama

Gunakan file template yang baru dibuat pada langkah `2.4` untuk melakukan uji coba:

```bash
python -m chemflow run --ligands contoh/ligan_contoh_tidy.xlsx --receptors contoh/reseptor_contoh.xlsx --output hasil_pertama/ --openbabel-path "C:/path/ke/obabel.exe"
```

- Setelah `--openbabel-path` berhasil disimpan pada run pertama, opsi tersebut tidak perlu ditulis lagi di run selanjutnya.
- Apabila ada baris reseptor pada Excel yang belum memiliki koordinat *gridbox*, **chemflow** akan menampilkan daftar ligan native yang ditemukan pada PDB tersebut dan meminta Anda memilih salah satunya sebagai titik pusat docking.
- Tambahkan `--no-interactive-gridbox` bila ingin menjalankan pipeline tanpa prompt interaktif (koordinat *gridbox* harus sudah terisi di Excel).

---

## 4. Menyiapkan Data

### 4.1 Excel Senyawa (Ligan)

Tersedia dua format tabel yang dikenali secara otomatis:

#### A. Format *Tidy* (Direkomendasikan)
| Kolom | Wajib? | Keterangan |
| :--- | :---: | :--- |
| `name` | **Ya** | Nama senyawa. Nama folder dan file akan diturunkan secara aman dari kolom ini. |
| `smiles` | Tidak | Struktur SMILES senyawa. Jika dikosongkan, **chemflow** akan mencarinya otomatis di PubChem berdasarkan `name`. |
| `group` | Tidak | Label kelompok/sumber senyawa (mis. `Obat_Sintetis`, `Senyawa_Alami`). Analisis PCA dan HCA memerlukan minimal 2 kelompok berbeda. |

Contoh format *Tidy*:

| name | smiles | group |
| :--- | :--- | :--- |
| Aspirin | `CC(=O)OC1=CC=CC=C1C(=O)O` | Obat_Sintetis |
| Kuersetin | | Senyawa_Alami |

#### B. Format *Wide* (Alternatif Multi-Kolom)
Digunakan bila tabel tidak memiliki kolom `smiles`. Setiap nama kolom dianggap sebagai nama kelompok (`group`), dan setiap sel di bawahnya berisi nama senyawa yang akan dicari otomatis di PubChem:

| Tanaman_X | Tanaman_Y |
| :--- | :--- |
| Quercetin | Curcumin |
| Kaempferol | Demethoxycurcumin |

> **Tip:** Bila suatu nama senyawa tidak ditemukan di PubChem, **chemflow** akan menawarkan input SMILES manual atau melewati senyawa tersebut. Gunakan `--no-pubchem-interactive-fallback` jika ingin langsung melewati senyawa yang gagal tanpa prompt.

<details>
<summary><strong>Aturan Penamaan File Otomatis dari Nama Senyawa (Klik untuk detail)</strong></summary>

Nama kimia sering kali memuat karakter yang tidak diizinkan pada sistem berkas Windows. Oleh karena itu, **chemflow** secara otomatis membuat nama berkas yang aman dan unik:
- Karakter terlarang (`< > : " / \ | ? *`), spasi, dan tanda kurung diubah menjadi garis bawah (`_`). Titik atau garis di ujung nama dihapus.
- Huruf beraksen dinormalisasi ke huruf dasar (`Café` $\rightarrow$ `Cafe`) dan huruf Yunani ditulis namanya (`α-Tocopherol` $\rightarrow$ `alpha-Tocopherol`).
- Nama cadangan perangkat Windows (`CON`, `NUL`, `AUX`, `COM1`–`COM9`, `LPT1`–`LPT9`) diberi akhiran garis bawah.
- Aksara non-Latin (mis. karakter Mandarin) diubah menjadi `unnamed_<hash>`.
- Nama yang menjadi kembar setelah dirapikan (termasuk perbedaan huruf besar/kecil seperti `Aspirin` dan `ASPIRIN`) diberi akhiran `_2`, `_3`, dst.
- Panjang nama dibatasi maksimal 60 karakter (atau menyesuaikan kedalaman direktori output) agar tidak melebihi batas 260 karakter Windows.
- Pemetaan lengkap antara nama asli dan `nama_file` dapat dilihat pada sheet **`Ringkasan Ligan`** di `hasil_chemflow.xlsx`.
</details>

---

### 4.2 Excel Protein (Reseptor)

| Kolom | Wajib? | Keterangan |
| :--- | :---: | :--- |
| `pdb_code` | **Ya** | Kode 4 karakter struktur protein dari [RCSB PDB](https://www.rcsb.org) (contoh: `6LU7`, `6X3Z`). |
| `center_x`, `center_y`, `center_z` | Tidak | Koordinat titik pusat kotak docking (*gridbox*) dalam satuan Ångström ($\text{\AA}$). |
| `size_x`, `size_y`, `size_z` | Tidak | Dimensi ukuran *gridbox* ($\text{\AA}$). Jika dikosongkan, dihitung otomatis dari ukuran ligan native. |

- **Penentuan Ukuran Gridbox Otomatis**: Dihitung sebagai kubus dari rentang terpanjang ligan native ditambah *padding* $8\text{ \AA}$ (dibulatkan ke atas, minimum $18\text{ \AA}$ dan maksimum $30\text{ \AA}$). Nilai *padding* dapat diatur dengan `--box-padding`, dan ukuran cadangan bila struktur tidak memiliki ligan native diatur lewat `--default-box-size` (bawaan `20`).
- **Multi-Situs & Multi-Reseptor**: Kode PDB yang sama boleh ditulis pada beberapa baris dengan koordinat pusat berbeda untuk *multi-site docking*.

#### Menyusun Excel Reseptor Secara Interaktif (`receptor-config`)
Jika Anda belum mengetahui koordinat dan ukuran *gridbox*, jalankan asisten interaktif berikut sebelum memulai pipeline:

```bash
python -m chemflow receptor-config
```

Asisten ini akan memandu Anda:
1. Memasukkan satu atau beberapa kode PDB (misal: `3PTB 1HVR`).
2. Mengunduh struktur dari RCSB dan menampilkan tabel seluruh ligan native yang terdeteksi beserta saran titik pusat dan ukuran *gridbox*-nya.
3. Memilih nomor ligan (bisa lebih dari satu nomor untuk *multi-site*, `m` untuk input koordinat manual, atau `s` untuk melewati).
4. Menyimpan hasilnya langsung menjadi file Excel (bawaan: `reseptor.xlsx`) yang siap digunakan pada `--receptors`.

<details>
<summary><strong>Contoh Sesi Interaktif <code>chemflow receptor-config</code> (Klik untuk melihat)</strong></summary>

```text
Kode PDB (pisahkan dengan spasi atau koma, contoh 6LU7 3PTB): 3PTB

[1/1] 3PTB: mengunduh struktur dari RCSB
Ligan native pada 3PTB:
  No  Chain   Residu   Nomor   Atom    Pusat X    Pusat Y    Pusat Z   Kotak
   1      A      BEN       1      9     -1.759     14.461     16.916      18
   2      A       CA     480      1    -10.300      4.358     36.895      18
Pilih nomor ligan (beberapa nomor dipisah spasi), m untuk koordinat manual, s untuk melewati: 1

Ligan BEN_A1: pusat (-1.759, 14.461, 16.916), panjang 4.5 Angstrom.
Ukuran kotak x y z dalam Angstrom, Enter untuk 18 (satu angka untuk kubus):

Nama file keluaran [reseptor.xlsx]:
```
</details>

---

## 5. Menjalankan Pipeline

Perintah standar untuk menjalankan skrining penuh:

```bash
python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --output hasil/
```

### Opsi yang Sering Digunakan

| Opsi CLI | Fungsi |
| :--- | :--- |
| `--run-rmsd-validation` | Menghitung RMSD pose *redocking* ligan native terhadap posisi kristalnya ($\le 2\text{ \AA}$ = protokol valid). |
| `--n-replicates 3` | Mengulang setiap pasangan docking sebanyak 3 kali dengan *seed* berbeda untuk menghitung rata-rata dan simpangan baku $\Delta G$. |
| `--exhaustiveness 16` | Tingkat ketelitian pencarian konformasi AutoDock Vina (bawaan: `8`). |
| `--merge-mode all` | Menyimpan seluruh pose dari setiap replikat sebagai kompleks terpisah (bawaan: `best`, hanya pose terbaik). |
| `--no-native` | Menonaktifkan ekstraksi dan *redocking* ligan native pembanding. |
| `--no-similarity` | Menonaktifkan ekspor interaksi otomatis BIOVIA meskipun BIOVIA terdeteksi di Windows. |
| `--admet-file file.csv` | Menggunakan file hasil unduhan manual ADMETLab 3.0 (lihat [Bagian 6](#6-admet-otomatis-atau-dari-file)). |
| `--no-admet` | Melewati tahapan prediksi ADMET. |
| `--gcms data-gcms/` | Menjalankan analisis kemometrik GC-MS tambahan setelah pipeline utama selesai. |
| `--dpi 600` | Mengatur resolusi ekspor gambar grafik (bawaan: `300`). |
| `--figure-formats png svg pdf` | Mengekspor grafik ke format vektor tambahan (`svg`, `pdf`) selain `png`. |
| `--plot-max-rows 30` | Batas maksimum baris/ligan per gambar sebelum dipotong otomatis menjadi beberapa bagian (`0` = tanpa pemotongan). |

*(Untuk melihat seluruh opsi, jalankan `python -m chemflow run --help` atau lihat [Bagian 11](#11-untuk-pengguna-lanjutan)).*

---

### 5.1 Melanjutkan Run yang Terhenti (`resume`)

Setiap ligan yang selesai disiapkan, reseptor beserta *gridbox*, hasil ADMET, dan setiap run AutoDock Vina langsung dicatat sebagai *checkpoint* di dalam `hasil/_state/`. Apabila eksekusi terputus karena terminal tertutup, ditekan `Ctrl+C`, atau listrik/komputer mati, cukup jalankan:

```bash
python -m chemflow resume --output hasil/
```

- **Otomatis Memulihkan Konfigurasi**: Seluruh parameter dan salinan file Excel asli dibaca kembali dari `hasil/_state/`.
- **Hanya Melanjutkan yang Belum Selesai**: Tahapan yang sudah sukses (pencarian PubChem, preparasi ligan/reseptor, ADMET, dan docking yang telah selesai) tidak akan diulang.
- **Regenerasi Laporan & Grafik Cepat**: Jika dijalankan pada folder `hasil/` yang sudah selesai 100%, `resume` hanya akan membuat ulang laporan Excel dan seluruh grafik dari *checkpoint* dalam hitungan detik tanpa melakukan docking ulang.

---

### 5.2 Ligan Native sebagai Pembanding

Secara bawaan, ligan kokristal (*native*) yang berada paling dekat dengan titik pusat *gridbox* (maksimal berjarak $8\text{ \AA}$) akan diekstrak, di-*redock* dengan parameter yang sama seperti ligan uji, dan dimasukkan ke dalam grup **`Native`** pada seluruh analisis (Lipinski, ADMET, perbandingan $\Delta G$, heatmap, PCA, HCA, dan grafik radar).

Jika opsi `--run-rmsd-validation` diaktifkan, **chemflow** menghitung nilai RMSD seluruh pose *redocking* terhadap koordinat kristal asli tanpa superposisi (`rdMolAlign.CalcRMS` dengan koreksi simetri molekul).

---

### 5.3 Validasi RMSD Mandiri (`--rmsd-only`)

Sejak versi 2.1.0, Anda dapat menjalankan **khusus validasi redocking ligan native** tanpa perlu menyiapkan Excel ligan uji, tanpa ADMET, dan tanpa docking senyawa skrining:

```bash
python -m chemflow run --rmsd-only --receptors reseptor.xlsx --output validasi/ --no-similarity
```

Contoh dengan replikasi dan pengaturan mode *merge*/interaksi:
```bash
python -m chemflow run --rmsd-only --receptors reseptor.xlsx --output validasi/ \
  --n-replicates 3 --num-modes 9 --rmsd-merge-mode best --rmsd-interaction-mode all --similarity
```

| Opsi Validasi RMSD | Keterangan & Nilai Bawaan |
| :--- | :--- |
| `--rmsd-only` | Menjalankan hanya preparasi reseptor & ligan native, *redocking*, perhitungan RMSD, serta *merge*/interaksi RMSD. |
| `--rmsd-merge-mode {best,all}` | Memilih pose dengan **RMSD terkecil** (`best`, bawaan) atau seluruh pose (`all`) untuk digabung menjadi kompleks di `<output>/rmsd/complexes/`. |
| `--rmsd-interaction-mode {best,all}` | Memilih kompleks yang akan diekspor interaksinya ke BIOVIA secara independen (bawaan: `best`). |
| `--similarity` / `--no-similarity` | Mengaktifkan atau mematikan ekspor interaksi BIOVIA untuk kompleks RMSD. |

Hasil validasi mandiri disimpan di `<output>/rmsd/hasil_rmsd.xlsx` (sheet `Validasi RMSD` untuk pose terbaik per reseptor dan sheet `Hasil Docking` untuk seluruh pose dari semua replikat). Ekspor interaksi BIOVIA untuk hasil RMSD juga dapat dijalankan terpisah:
```bash
python -m chemflow interactions --output validasi/ --rmsd
```

---

## 6. ADMET: Otomatis atau dari File

Secara bawaan, **chemflow** mengirim SMILES unik ke server ADMETLab 3.0 secara otomatis (dilengkapi *retry* otomatis bila server sedang sibuk / `HTTP 429`). Apabila server ADMETLab 3.0 sedang dalam perawatan atau Anda ingin menggunakan hasil unduhan manual:

1. Buka situs **ADMETLab 3.0** (menu *Screening*), masukkan daftar SMILES **dengan urutan yang sama seperti pada Excel ligan**, lalu unduh hasilnya dalam format `.csv` atau `.xlsx`.
2. Jalankan **chemflow** dengan menambahkan `--admet-file`:
   ```bash
   python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --admet-file hasil_admetlab.csv
   ```

**Aturan Pemetaan Baris ADMET:**
- Baris ke-$N$ pada file ADMET dipetakan ke ligan ke-$N$ pada Excel ligan (atau ke SMILES unik ke-$N$ apabila terdapat senyawa yang sama di beberapa grup).
- Jika file memuat kolom `raw_smiles` atau `smiles`, **chemflow** akan memverifikasi kecocokan strukturnya secara otomatis.

---

## 7. Membaca Hasil

Setelah eksekusi selesai, folder keluaran (`hasil/`) akan memiliki struktur berikut:

```text
hasil/
├── hasil_chemflow.xlsx       # Laporan utama Excel (multi-sheet, berwarna)
├── chemflow.log              # Log eksekusi lengkap
├── ligands/<nama>/           # Gambar 2D (.png), struktur 3D (.pdb), dan .pdbqt tiap ligan (termasuk NATIVE_*)
├── receptors/<kunci>/        # Reseptor siap docking (_docking.pdbqt) dan reseptor bersih (_clean.pdb)
├── docking/<kunci>/<ligan>/  # File pose keluaran Vina (.pdbqt) dan log per replikat
├── complexes/<kunci>/        # Kompleks gabungan protein-ligan (.pdb) siap dibuka di PyMOL / BIOVIA
├── analytics/                # Seluruh grafik 300 dpi (.png, serta .svg/.pdf bila diaktifkan)
├── interaksi/<kunci>/        # Diagram interaksi 2D (.png) & tabel Non-bond (.xlsx) hasil ekspor BIOVIA
├── rmsd/                     # Laporan & kompleks khusus validasi RMSD
├── gcms/                     # Hasil analisis kemometrik GC-MS (bila diaktifkan)
└── _state/                   # Data checkpoint & salinan konfigurasi untuk perintah `resume`
```

### Daftar Sheet pada `hasil_chemflow.xlsx`

| Nama Sheet | Isi Ringkas |
| :--- | :--- |
| **Ringkasan Ligan** | Daftar seluruh senyawa uji & native, SMILES, grup, status preparasi, dan `nama_file`. |
| **Hasil Docking** | Nilai afinitas ikatan ($\Delta G$, kcal/mol) setiap replikat. Semakin negatif berarti ikatan semakin kuat. |
| **Fisikokimia (Lipinski)** | Bobot molekul (`MW`), `LogP`, donor/akseptor ikatan H (`HBD`, `HBA`), jumlah pelanggaran, dan status lolos Ro5. |
| **ADMET** | Seluruh parameter ADMETLab 3.0 dikelompokkan per kategori dengan sel berwarna **Hijau** (baik), **Kuning** (sedang), atau **Merah** (buruk). |
| **Legenda ADMET** | Penjelasan kategori, satuan, ambang batas evaluasi, dan referensi ilmiah setiap parameter ADMET. |
| **Validasi RMSD** | Nilai RMSD redocking ligan native ($\text{\AA}$) beserta status validasi ($\le 2,0\text{ \AA}$). |
| **Statistik Replikasi** | Rata-rata, simpangan baku, $\Delta G$ terbaik antar-replikat, serta `delta_vs_native` ($\Delta G_{\text{uji}} - \Delta G_{\text{native}}$). |
| **Ringkasan per Grup** | Statistik rata-rata fisikokimia, persentase lolos Ro5, dan skor kategori ADMET per kelompok senyawa. |
| **Docking per Grup** | Perbandingan $\Delta G$ rata-rata & terbaik per grup terhadap ligan native pada masing-masing reseptor. |

### Daftar Grafik pada Folder `analytics/`

| Nama Berkas | Deskripsi Visualisasi |
| :--- | :--- |
| `bar_affinity.png` | Diagram batang peringkat afinitas ikatan ($\Delta G$) ligan uji dan native. |
| `radar_combined.png` | Grafik radar profil gabungan ($\Delta G$, fisikokimia, dan skor kategori ADMET) untuk ligan terbaik. |
| `radar_admet_<kategori>.png` | Grafik radar parameter ADMET per kategori untuk ligan dengan skor tertinggi. |
| `admet_klasifikasi_<kategori>.png` | Distribusi persentase kategori Baik / Sedang / Buruk pada setiap parameter ADMET. |
| `heatmap_afinitas.png` | Peta panas afinitas ikatan seluruh ligan terhadap seluruh reseptor. |
| `heatmap_fisikokimia.png` & `..._klaster.png` | Peta panas profil Lipinski (standar dan terklaster secara hierarkis dengan dendrogram). |
| `pca_2d.png` & `pca_3d.png` | Plot skor & vektor loading *Principal Component Analysis* (PCA) bergaya jurnal dengan elips kepercayaan 95%. |
| `hca_dendrogram.png` | Dendrogram *Hierarchical Cluster Analysis* (Ward, Euclidean) dengan warna label per kelompok. |
| `grup_*.png` | Rangkaian grafik perbandingan antar-kelompok senyawa (boxplot $\Delta G$, heatmap grup vs native, radar ADMET grup, dan boxplot fisikokimia). |

---

## 8. Analisis Similaritas Interaksi

Membandingkan kesamaan residu kontak dan tipe interaksi antara ligan uji dan ligan native menggunakan metode **Pratama et al. (2021)** berdasarkan tabel interaksi dari **BIOVIA Discovery Studio**.

- **Mode Otomatis (Windows + BIOVIA Terpasang)**:
  Saat menjalankan `chemflow run`, apabila BIOVIA Discovery Studio terdeteksi, **chemflow** otomatis membuka setiap kompleks di `complexes/`, mengekspor diagram 2D (`.png`) dan tabel *Non-bond* (`.xlsx`) ke `interaksi/`, lalu menghitung similaritas interaksi.
  - Selama proses ekspor GUI berlangsung, input mouse dan keyboard dikunci sementara agar klik tidak meleset (tekan **`Esc` 3 kali berturut-turut** jika ingin membatalkan).
- **Menjalankan Ekspor Interaksi Saja**:
  ```bash
  python -m chemflow interactions --output hasil/
  ```
- **Menjalankan Perhitungan & Grafik Similaritas Saja** *(jika tabel interaksi sudah tersedia)*:
  ```bash
  python -m chemflow similarity --output hasil/
  ```
  Menghasilkan laporan `similaritas_interaksi.xlsx` serta grafik `similaritas_bar.png`, `similaritas_vs_deltag.png`, dan heatmap jejak kontak residu `similaritas_jejak_<reseptor>.png`. Panduan lengkap tersedia di [`docs/biovia-interactions.md`](docs/biovia-interactions.md) dan [`docs/similarity-analysis.md`](docs/similarity-analysis.md).

---

## 9. Analisis GC-MS (Opsional)

Modul kemometrik untuk membandingkan kromatogram atau tabel puncak GC-MS (misalnya autentikasi parfum/minyak atsiri asli vs tiruan, atau perbandingan multi-produk). Dapat dijalankan secara mandiri tanpa docking:

```bash
python -m chemflow gcms --data data-gcms/ --output hasil/
```

Atau digabungkan langsung setelah pipeline docking selesai:
```bash
python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --output hasil/ --gcms data-gcms/
```

- **Format Input yang Didukung**: Ekspor Shimadzu GCMSsolution (`.xls`, `.xlsx`, `.txt`), CSV/TSV, ANDI-MS (`.cdf`), `.mzML`, dan `.mzXML`.
- **Keluaran di `hasil/gcms/`**:
  - `analisis_gcms.xlsx`: Tabel sampel, puncak terdeteksi, matriks fitur selaras, uji statistik dengan koreksi FDR (*Benjamini–Hochberg*), skor VIP PLS-DA, akurasi validasi silang, skor/loading PCA, matriks kemiripan kosinus, dan deteksi alergen.
  - `plots/`: Kromatogram TIC bertumpuk, pemeriksaan penyelarasan RT, scree & loading plot, PCA 2D/3D, dendrogram HCA, heatmap fitur teratas, *mirror plot*, *volcano plot*, grafik VIP, *confusion matrix*, uji permutasi, dan grafik alergen.
  - `ligan_gcms.xlsx`: Daftar senyawa teridentifikasi beserta SMILES yang siap langsung dijadikan input `--ligands` untuk skrining docking.
- Dokumentasi lengkap tersedia di [`docs/gcms-analysis.md`](docs/gcms-analysis.md).

---

## 10. Jika Terjadi Error

| Gejala / Pesan di Log | Penyebab & Solusi |
| :--- | :--- |
| `Executable 'obabel' tidak ditemukan` | OpenBabel belum terpasang atau belum terdeteksi. Pasang OpenBabel (Bagian 2.3) atau berikan lokasinya satu kali dengan `--openbabel-path "C:/.../obabel.exe"`. |
| SMILES tidak ditemukan di PubChem | Nama senyawa tidak dikenali di database PubChem. Gunakan nama IUPAC/internasional dalam bahasa Inggris, atau isi langsung kolom `smiles` di Excel. |
| ADMETLab3 membalas `HTTP 429` / lambat | Server publik ADMETLab 3.0 sedang membatasi permintaan. **chemflow** akan mencoba ulang secara otomatis; jika masih gagal, gunakan `--admet-file` (Bagian 6) atau `--no-admet`. |
| `File ADMET ... berisi N baris, sedangkan input memuat M ligan` | Jumlah baris pada file `--admet-file` harus sama persis dengan jumlah ligan (atau jumlah SMILES unik) pada file Excel ligan. |
| `PCA dilewati: ... minimal 2 kelompok` | Kolom `group` hanya berisi 1 kelompok dan `--no-native` aktif. Isi minimal 2 nama kelompok berbeda di kolom `group` atau biarkan ligan native aktif. |
| Proses terhenti karena terminal tertutup / `Ctrl+C` / PC mati | Jalankan `python -m chemflow resume --output hasil/` untuk melanjutkan dari *checkpoint* terakhir tanpa mengulang dari awal. |
| Proses berhenti menunggu input di terminal | **chemflow** sedang menunggu Anda memilih nomor ligan native untuk *gridbox* atau mengisi SMILES. Gunakan `--no-interactive-gridbox` dan `--no-pubchem-interactive-fallback` untuk mode tanpa prompt. |
| `Gagal mengunduh PDB ...` | Kode PDB keliru atau struktur raksasa tersebut tidak memiliki format `.pdb` standar di RCSB. Periksa kode di [rcsb.org](https://www.rcsb.org). |
| `Similaritas interaksi dilewati: BIOVIA tidak terdeteksi` | Bukan error fatal. Komputer bukan Windows atau BIOVIA belum terpasang, sehingga tahap ekspor GUI dilewati dan pipeline tetap selesai normal. |
| `Fokus jendela BIOVIA hilang` / `Dibatalkan pengguna (Esc 3x)` | Ekspor GUI BIOVIA terinterupsi. Cukup jalankan ulang `python -m chemflow interactions --output hasil/`; kompleks yang sudah selesai akan dilewati otomatis. |

> Detail seluruh proses dan *traceback* teknis selalu dapat diperiksa pada berkas `chemflow.log` di dalam folder output.

---

## 11. Untuk Pengguna Lanjutan

<details>
<summary><strong>Tabel Lengkap Argumen <code>chemflow run</code> (Klik untuk membuka)</strong></summary>

| Kategori | Argumen CLI |
| :--- | :--- |
| **Input & Output** | `--ligands`, `--receptors`, `--output` |
| **Pemetaan Kolom Excel** | `--ligand-name-col`, `--ligand-smiles-col`, `--ligand-group-col`, `--receptor-pdb-col` |
| **Gridbox** | `--default-box-size`, `--box-padding`, `--no-interactive-gridbox` |
| **Preparasi Ligan** | `--force-field {MMFF94,UFF}`, `--minimize-max-iters`, `--no-2d-image` |
| **Preparasi Reseptor** | `--keep-waters`, `--keep-hetero-ligands`, `--no-keep-metals`, `--kollman-fallback {zero,gasteiger}` |
| **Docking (Vina)** | `--vina-version`, `--vina-executable`, `--exhaustiveness`, `--num-modes`, `--energy-range`, `--seed`, `--n-replicates` |
| **Merge Kompleks** | `--merge-mode {best,all}` |
| **Ligan Native & RMSD** | `--no-native`, `--run-rmsd-validation`, `--rmsd-only`, `--rmsd-merge-mode {best,all}`, `--rmsd-interaction-mode {best,all}`, `--rmsd-threshold-good`, `--rmsd-threshold-acceptable` |
| **BIOVIA & Similaritas** | `--similarity`, `--no-similarity`, `--biovia-exe`, `--biovia-timeout`, `--no-lock-input` |
| **OpenBabel** | `--openbabel-path` |
| **ADMET & PubChem** | `--no-admet`, `--admet-file`, `--admet-batch-size`, `--admet-ssl-verify`, `--no-pubchem-fetch`, `--no-pubchem-interactive-fallback` |
| **Grafik & Analitik** | `--no-charts`, `--no-pca`, `--no-hca`, `--no-heatmap`, `--dpi`, `--figure-formats`, `--plot-max-rows`, `--plot-max-cols` |
| **GC-MS** | `--gcms`, `--gcms-groups`, `--gcms-library` |
| **Logging & Tampilan** | `--verbose`, `--log-level`, `--no-progress` |
</details>

### Daftar Seluruh Subperintah CLI

- `chemflow web [--host H] [--port P] [--workspace DIR] [--allowed-host H] [--trusted-proxy IP] [--secure-cookie]`: Menjalankan server ruang kerja WebUI.
- `chemflow init [--output DIR] [--format tidy|wide|both] [--skip-check]`: Membuat template Excel contoh dan memeriksa kesiapan sistem.
- `chemflow run ...`: Menjalankan pipeline utama skrining virtual atau validasi `--rmsd-only`.
- `chemflow resume --output DIR [...]`: Melanjutkan eksekusi yang terhenti dari *checkpoint* terakhir.
- `chemflow receptor-config`: Asisten interaktif penyusun Excel reseptor dan *gridbox* dari kode PDB.
- `chemflow interactions --output DIR [--rmsd] [...]`: Mengekspor diagram 2D dan tabel *Non-bond* melalui GUI BIOVIA Discovery Studio (Windows).
- `chemflow similarity --output DIR [...]`: Menghitung similaritas interaksi terhadap ligan native dari berkas interaksi yang sudah ada.
- `chemflow gcms --output DIR [--data PATH ...] [...]`: Menjalankan pipeline kemometrik GC-MS mandiri.
- `chemflow list-vina-versions`: Menampilkan daftar versi AutoDock Vina yang kompatibel dengan sistem operasi Anda.
- `chemflow citations`: Menampilkan daftar sitasi perangkat lunak dan pustaka ilmiah dalam format teks/BibTeX.

### Pemakaian sebagai Library Python

```python
from chemflow import Pipeline, PipelineConfig

config = PipelineConfig(
    ligand_excel="ligan.xlsx",
    receptor_excel="reseptor.xlsx",
    output_dir="hasil",
)
Pipeline(config).run()
```
Setiap modul (preparasi ligan/reseptor, docking, ADMET, analitik grafik, similaritas, maupun GC-MS) juga dapat dipanggil secara terpisah. Lihat contoh lengkapnya di [`docs/library-usage.md`](docs/library-usage.md) dan dokumentasi arsitektur di [`docs/README.md`](docs/README.md).

### Menjalankan Pengujian (Unit Test)

```bash
pytest tests/ -v
```
Seluruh pengujian unit berjalan secara lokal menggunakan *fixture* sintetis tanpa memanggil koneksi internet, OpenBabel, maupun AutoDock Vina.

---

## Referensi Ilmiah

- **Lipinski et al. (1997)**, *Adv. Drug Deliv. Rev.* — *Rule of Five* sifat fisikokimia senyawa obat.
- **Fu et al. (2024)**, *Nucleic Acids Research* 52(W1):W422–W431 — Platform prediksi ADMETLab 3.0.
- **Morris et al. (2009)**, *J. Comput. Chem.* — Sistem tipe atom AutoDock4 dan spesifikasi PDBQT.
- **Cornell et al. (1995)**, *JACS* 117:5179; **Hornak et al. (2006)**, *Proteins* 65(3):712–725 — Parameter muatan parsial AMBER ff99SB.
- **Hevener et al. (2009)**, *J. Chem. Inf. Model.* 49(2):444–460 — Kriteria validasi RMSD *redocking* $\le 2,0\text{ \AA}$.
- **Pratama, Poerwono, & Siswodihardjo (2021)**, *Indonesian Journal of Biotechnology* 26(1):54–60 (DOI: `10.22146/ijbiotech.62194`) — Metode kuantifikasi similaritas interaksi ligan–reseptor.
- **Aghoutane et al. (2023)**, *Micromachines* 14(3):524 (DOI: `10.3390/mi14030524`) — Konvensi visualisasi PCA kemometrik dan analisis GC-MS.
- **Eilers & Boelens (2005)** (koreksi baseline ALS); **Savitzky & Golay (1964)**, *Anal. Chem.* 36(8):1627–1639; **Dieterle et al. (2006)**, *Anal. Chem.* 78(13):4281–4290 (normalisasi PQN); **Benjamini & Hochberg (1995)**, *J. R. Stat. Soc. B* 57(1):289–300 (koreksi FDR).
- **Okabe & Ito (2008)** — Palet warna kategorikal ramah buta warna.

---

## Lisensi & Pengembang

Dirilis di bawah lisensi **MIT** — lihat berkas [`LICENSE`](LICENSE).  
Dikembangkan oleh **Arif Maulana Azis** ([@Arifmaulanaazis](https://github.com/Arifmaulanaazis)).
