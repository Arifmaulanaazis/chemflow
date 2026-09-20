<p align="center">
  <img src="chemflow.png" alt="Logo chemflow: labu Erlenmeyer dengan dua simpul molekul" width="160">
</p>

<h1 align="center">chemflow</h1>

<p align="center">
  Skrining virtual senyawa obat otomatis: dari dua file Excel sampai docking, ADMET, dan analitik.
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img alt="Python 3.9 atau lebih baru" src="https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white"></a>
  <a href="LICENSE"><img alt="Lisensi MIT" src="https://img.shields.io/badge/license-MIT-green"></a>
  <a href="pyproject.toml"><img alt="Versi 2.0.0" src="https://img.shields.io/badge/version-2.0.0-3C71E8"></a>
  <img alt="Platform Windows, macOS, dan Linux" src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey">
  <img alt="Docking dengan AutoDock Vina" src="https://img.shields.io/badge/docking-AutoDock%20Vina-8E70EB">
  <img alt="Kemoinformatika dengan RDKit" src="https://img.shields.io/badge/cheminformatics-RDKit-8E70EB">
  <img alt="Konversi format dengan Open Babel" src="https://img.shields.io/badge/converter-Open%20Babel-8E70EB">
  <a href="docs/README.md"><img alt="Dokumentasi teknis" src="https://img.shields.io/badge/docs-referensi%20teknis-3C71E8"></a>
</p>

**chemflow** adalah program baris perintah (CLI) untuk skrining virtual senyawa
obat secara otomatis. Dari dua file Excel (daftar senyawa dan daftar protein
target), chemflow menyiapkan senyawa dan protein, menghitung sifat fisikokimia
dan ADMET, menjalankan docking molekuler dengan AutoDock Vina, memvalidasi
hasilnya, lalu membuat tabel, grafik siap publikasi, dan analisis statistik.

Anda tidak perlu bisa coding. Panduan ini ditulis untuk pengguna yang belum
pernah memakai terminal.

## Tentang

chemflow merangkai seluruh alur skrining virtual dalam satu perintah:
preparasi senyawa dan protein, sifat fisikokimia dan ADMET, docking molekuler,
validasi RMSD, penggabungan kompleks, hingga analitik. Masukannya cukup dua file
Excel, keluarannya tabel hasil, grafik siap publikasi, dan kompleks
protein-ligan.

| Item | Keterangan |
|---|---|
| Nama | chemflow |
| Versi | 2.0.0 |
| Antarmuka | CLI (`chemflow` atau `python -m chemflow`) dan library Python |
| Bahasa | Python 3.9 atau lebih baru |
| Komponen utama | RDKit, OpenBabel, AutoDock Vina, ADMETLab3 |
| Lisensi | MIT, lihat [`LICENSE`](LICENSE) |
| Pengembang | Arif Maulana Azis ([@Arifmaulanaazis](https://github.com/Arifmaulanaazis)) |
| Repositori | [github.com/Arifmaulanaazis/chemflow](https://github.com/Arifmaulanaazis/chemflow) |

## Fitur

- **Preparasi ligan**: SMILES (atau nama senyawa yang dicari otomatis di PubChem)
  diproses RDKit (netralisasi, hidrogenasi, minimisasi MMFF94/UFF, muatan
  Gasteiger, gambar 2D), lalu dikonversi ke PDBQT lewat OpenBabel.
- **Preparasi reseptor**: struktur PDB dibersihkan dari air dan ligan asli,
  residu termodifikasi tetap dipertahankan lewat deteksi struktural, lalu
  ditambah hidrogen polar dan muatan Kollman.
- **Excel reseptor otomatis**: `chemflow receptor-config` menyusun Excel
  reseptor secara interaktif. Anda cukup memasukkan kode PDB dan memilih ligan
  native, pusat dan ukuran kotak docking terisi otomatis.
- **Sifat fisikokimia**: Lipinski Rule of Five dari RDKit.
- **ADMET**: prediksi dari ADMETLab3 (otomatis) atau dari file CSV/Excel hasil
  unduhan ADMETLab3 (`--admet-file`). Sel Excel diwarnai hijau/kuning/merah
  sesuai ambang tiap parameter, lengkap dengan sheet legenda ambang.
- **Docking**: AutoDock Vina diunduh otomatis sesuai OS dan arsitektur mesin.
  Mendukung banyak reseptor, banyak situs per reseptor, dan replikasi dengan
  rata-rata dan simpangan baku afinitas.
- **Ligan native sebagai pembanding**: ligan kokristal diambil dari struktur PDB,
  di-dock ulang dengan parameter yang sama seperti ligan uji, lalu ikut semua
  analitik (ADMET, fisikokimia, ΔG, heatmap, PCA, HCA, radar) sebagai grup
  **Native**.
- **Validasi RMSD redocking** (opsional): RMSD pose terbaik hasil redocking native
  dihitung terhadap posisi kristalnya pada koordinat aslinya, tanpa superposisi,
  sehingga pose yang bergeser dari kantong ikat ikut terhitung.
- **Kompleks protein-ligan**: pose docking digabung dengan reseptor bersih
  (`--merge-mode best` atau `all`), termasuk kompleks referensi native.
- **Analitik**: bar afinitas, radar gabungan, radar dan bar klasifikasi per
  kategori ADMET, heatmap (termasuk terklaster dengan dendrogram), PCA 2D/3D
  bergaya jurnal (warna per seri, penanda dan elips 95% per kelas), dan HCA.
  Semua grafik memakai palet aman buta warna, 300 dpi, dan bisa ditulis juga
  sebagai SVG/PDF untuk naskah jurnal.
- **Perbandingan antar-grup**: grafik ADMET, ΔG, dan fisikokimia per grup senyawa
  dengan ligan native sebagai pembanding, serta sheet ringkasan per grup.
- **Grafik besar dipotong otomatis**: bila ligan, reseptor, atau parameter terlalu
  banyak, grafik dibagi menjadi beberapa gambar (`_part01of03`) dengan skala yang
  sama supaya tetap terbaca.
- **Melanjutkan run yang terhenti**: `chemflow resume --output hasil/` meneruskan
  dari checkpoint terakhir setelah terminal ditutup, Ctrl+C, atau komputer mati.
- **Similaritas interaksi** (opsional): membandingkan pola interaksi ligan
  terhadap ligan native memakai metode Pratama et al. (2021), dengan grafik
  peringkat, grafik similaritas terhadap selisih ΔG, dan heatmap jejak kontak
  terklaster.
- **Interaksi otomatis dari BIOVIA** (Windows): diagram 2D dan tabel interaksi
  tiap kompleks diekspor sendiri lewat GUI BIOVIA Discovery Studio. Bila BIOVIA
  terdeteksi, `chemflow run` berjalan dari docking sampai similaritas tanpa opsi
  tambahan, dengan mouse dan keyboard dikunci selama ekspor agar tidak salah klik
  (Esc tiga kali membatalkan).
- **Analisis GC-MS** (opsional): kromatogram, puncak, PCA, HCA, PLS-DA, uji
  statistik dengan koreksi FDR, dan skrining alergen wewangian dari data
  Shimadzu, CSV, CDF, mzML, atau mzXML. Berjalan mandiri tanpa docking
  (`chemflow gcms`) atau sebagai tahap tambahan (`chemflow run --gcms`).
- **Progress bar** pada setiap tahap panjang, di samping log.

## Daftar Isi

1. [Yang perlu disiapkan](#1-yang-perlu-disiapkan)
2. [Instalasi](#2-instalasi)
3. [Uji coba pertama](#3-uji-coba-pertama)
4. [Menyiapkan data](#4-menyiapkan-data)
5. [Menjalankan pipeline](#5-menjalankan-pipeline)
   - [Melanjutkan run yang terhenti](#51-melanjutkan-run-yang-terhenti-resume)
   - [Ligan native sebagai pembanding](#52-ligan-native-sebagai-pembanding)
6. [ADMET: otomatis atau dari file](#6-admet-otomatis-atau-dari-file)
7. [Membaca hasil](#7-membaca-hasil)
8. [Analisis similaritas interaksi](#8-analisis-similaritas-interaksi)
9. [Analisis GC-MS (opsional)](#9-analisis-gc-ms-opsional)
10. [Jika terjadi error](#10-jika-terjadi-error)
11. [Untuk pengguna lanjutan](#11-untuk-pengguna-lanjutan)

## 1. Yang perlu disiapkan

| Apa | Kegunaan | Wajib |
|---|---|---|
| Koneksi internet | Mengunduh struktur protein (RCSB), mencari SMILES (PubChem), mengunduh AutoDock Vina (GitHub), dan ADMETLab3 bila tidak memakai file ADMET. | Ya |
| Python 3.9 atau lebih baru | Bahasa pemrograman yang menjalankan chemflow. | Ya |
| OpenBabel | Mengubah format struktur kimia. Satu-satunya program yang harus dipasang manual. | Ya |
| Excel, LibreOffice Calc, atau Google Sheets | Mengisi daftar senyawa dan protein. | Ya |
| BIOVIA Discovery Studio (Windows) | Ekspor interaksi otomatis untuk analisis similaritas; dijalankan sendiri bila terdeteksi. Versi Visualizer yang gratis cukup. | Tidak |

AutoDock Vina tidak perlu dipasang. chemflow mengunduhnya sendiri dan
menjalankannya lewat path lengkap, tanpa pengaturan PATH.

## 2. Instalasi

Langkah di bawah untuk Windows. Di macOS dan Linux langkahnya serupa, hanya
cara memasang Python dan OpenBabel yang berbeda.

### 2.1 Pasang Python

1. Unduh installer dari [python.org/downloads](https://www.python.org/downloads/).
2. Pada halaman pertama installer, centang **Add python.exe to PATH**, lalu klik Install.
3. Buka **Command Prompt** (tombol Windows, ketik `cmd`, Enter) dan cek:
   ```
   python --version
   ```
   Jika muncul versi Python, instalasi berhasil.

### 2.2 Ambil chemflow dan pasang dependency

Ekstrak folder chemflow (atau `git clone`), lalu di Command Prompt masuk ke
folder itu dan jalankan:

```
cd D:\lokasi\chemflow
pip install -r requirements.txt
pip install -e .
```

### 2.3 Pasang OpenBabel

Pilih salah satu cara.

**Cara A, lewat Miniconda (paling mudah):**

1. Pasang [Miniconda](https://docs.conda.io/en/latest/miniconda.html).
2. Buka **Anaconda Prompt** dan jalankan:
   ```
   conda create -n chemflow_tools -c conda-forge openbabel -y
   conda run -n chemflow_tools where obabel
   ```
3. Catat path `obabel.exe` yang muncul. Path ini diberikan ke chemflow lewat
   `--openbabel-path`, atau folder tempat `obabel.exe` berada bisa ditambahkan
   ke PATH Windows agar opsi itu tidak perlu ditulis.

**Cara B, installer resmi:** unduh dari [openbabel.org](https://openbabel.org),
jalankan installer, lalu buka Command Prompt baru dan cek dengan `obabel -V`.

### 2.4 Cek kesiapan

```
python -m chemflow init --output contoh/
```

Perintah ini membuat template Excel dan mencetak laporan: library Python yang
terpasang, lokasi OpenBabel, versi AutoDock Vina yang tersedia untuk komputer
Anda, dan apakah layanan online yang dipakai bisa dijangkau.

## 3. Uji coba pertama

Template dari langkah 2.4 sudah berisi contoh data. Jalankan:

```
python -m chemflow run --ligands contoh/ligan_contoh_tidy.xlsx --receptors contoh/reseptor_contoh.xlsx --output hasil_pertama/ --openbabel-path "C:/path/ke/obabel.exe"
```

Hapus `--openbabel-path` jika `obabel` sudah ada di PATH. Progress bar muncul
di terminal untuk tiap tahap. Setelah selesai, isi folder `hasil_pertama/`
dijelaskan di [bagian 7](#7-membaca-hasil).

Baris reseptor contoh tanpa gridbox akan membuat chemflow menampilkan daftar
ligan native pada struktur itu dan meminta Anda memilih salah satu sebagai
pusat docking. Tambahkan `--no-interactive-gridbox` untuk run tanpa
pertanyaan (gridbox harus diisi di Excel). Untuk menyiapkan gridbox lebih
dulu, lihat [bagian 4.2](#42-excel-protein-reseptor).

## 4. Menyiapkan data

### 4.1 Excel senyawa (ligan)

| Kolom | Wajib | Isi |
|---|---|---|
| `name` | Ya | Nama senyawa, boleh mengandung karakter apa saja. Nama file dan folder diturunkan otomatis dari nama ini (lihat di bawah). |
| `smiles` | Tidak | Struktur SMILES. Jika kosong, dicari otomatis di PubChem berdasarkan nama. |
| `group` | Tidak | Kelompok atau sumber senyawa. PCA dan HCA butuh minimal 2 kelompok berbeda. |

Contoh:

| name | smiles | group |
|---|---|---|
| Aspirin | CC(=O)OC1=CC=CC=C1C(=O)O | Obat_Sintetis |
| Kuersetin | | Senyawa_Alami |

Format alternatif **wide** dipakai jika tidak ada kolom `smiles`: tiap kolom
adalah satu kelompok dan isi sel adalah nama senyawa, sehingga semua nama
dicari di PubChem.

| Tanaman_X | Tanaman_Y |
|---|---|
| Quercetin | Curcumin |
| Kaempferol | Demethoxycurcumin |

Jika sebuah nama tidak ditemukan di PubChem, chemflow menawarkan input SMILES
manual atau melewati senyawa itu. Tambahkan `--no-pubchem-interactive-fallback`
agar senyawa yang gagal langsung dilewati tanpa pertanyaan.

**Nama file dari nama senyawa.** Nama senyawa sering memuat karakter yang
dilarang di nama file Windows, sehingga chemflow menurunkan nama file yang
aman dan unik dari nama itu:

- Karakter terlarang (`< > : " / \ | ? *`), spasi, dan tanda kurung menjadi
  garis bawah. Titik atau garis di ujung nama dibuang.
- Huruf beraksen ditulis huruf dasarnya (`Café` menjadi `Cafe`) dan huruf
  Yunani ditulis namanya (`α-Tocopherol` menjadi `alpha-Tocopherol`).
- Nama perangkat Windows (`CON`, `NUL`, `AUX`, `COM1` sampai `COM9`, `LPT1`
  sampai `LPT9`) diberi garis bawah di belakangnya.
- Aksara non-Latin yang tidak bisa dituliskan ulang (mis. nama Mandarin)
  diganti `unnamed_` dan kode hash pendek yang selalu sama untuk nama itu.
- Nama yang kembar setelah dirapikan, termasuk yang hanya beda huruf besar
  dan kecil (`Aspirin` dan `ASPIRIN`), diberi akhiran `_2`, `_3`, dan
  seterusnya. chemflow mencatat peringatan untuk tiap nama yang diubah.
- Nama dibatasi 60 karakter, dan lebih pendek lagi bila folder output sudah
  dalam, agar path terpanjang tetap di bawah batas 260 karakter Windows.

Sheet `Ringkasan Ligan` pada hasil memuat kolom `nama_file` yang memetakan
nama asli ke nama folder dan file di `ligands/`, `docking/`, dan `complexes/`.

### 4.2 Excel protein (reseptor)

| Kolom | Wajib | Isi |
|---|---|---|
| `pdb_code` | Ya | Kode 4 karakter dari [RCSB PDB](https://www.rcsb.org), misalnya `6LU7`. |
| `center_x`, `center_y`, `center_z` | Tidak | Pusat kotak docking (Angstrom). |
| `size_x`, `size_y`, `size_z` | Tidak | Ukuran kotak docking (Angstrom). Kosong berarti diturunkan dari ligan native (lihat di bawah). |

Jika gridbox dikosongkan, chemflow mendeteksi ligan native pada struktur dan
meminta Anda memilihnya. Jika hanya ukuran yang dikosongkan, ukuran diturunkan
dari ligan native terdekat dari pusat kotak (paling jauh 8 Angstrom dari pusat).

**Ukuran kotak default berasal dari ligan native**, bukan angka tetap: kubus
dengan sisi ekstensi terpanjang native ditambah padding 8 Angstrom, dibulatkan
ke atas, minimal 18 dan maksimal 30 Angstrom (sama dengan `receptor-config`).
Saat memilih ligan secara interaktif, tabel menampilkan ukuran tiap ligan dan
Enter menerima ukuran itu; ketik `n` untuk mengganti (satu angka untuk kubus atau
tiga angka `x y z`). Padding diatur dengan `--box-padding`. `--default-box-size`
(default 20) hanya cadangan bila struktur tidak punya ligan native. Kode PDB yang
sama boleh muncul di beberapa baris
dengan gridbox berbeda untuk docking multi-situs. Kode PDB berbeda
menghasilkan docking ke semua reseptor sekaligus.

#### Belum tahu koordinat dan ukuran gridbox?

Susun Excel reseptor lewat perintah interaktif sebelum menjalankan `run`:

```
python -m chemflow receptor-config
```

Perintah ini tidak punya opsi dan hanya berjalan di terminal interaktif.
Semua isian ditanyakan satu per satu:

1. Kode PDB, satu atau beberapa, misalnya `3PTB 1HVR`.
2. Ligan native untuk tiap struktur. chemflow mengunduh struktur dari RCSB dan
   menampilkan ligan yang ditemukan beserta pusat dan ukuran kotak yang
   disarankan. Ketik nomor ligan. Beberapa nomor (`1 2`) menghasilkan beberapa
   baris untuk docking multi-situs, `m` untuk mengetik koordinat sendiri, dan
   `s` untuk melewati struktur itu.
3. Ukuran kotak. Tekan Enter untuk memakai ukuran yang disarankan, atau ketik
   satu angka (kubus) atau tiga angka `x y z`.
4. Nama file keluaran (default `reseptor.xlsx`).

Contoh sesi (dipersingkat):

```
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

Pusat kotak adalah titik tengah ligan yang dipilih. Ukuran yang disarankan
adalah panjang terpanjang ligan ditambah 8 Angstrom, dibulatkan ke atas,
minimal 18 dan maksimal 30 Angstrom. File hasilnya berisi kolom
`pdb_code`, `center_x/y/z`, `size_x/y/z`, dan `native_ligand` (catatan asal
ligan, tidak dibaca chemflow) dan langsung dipakai sebagai `--receptors`:

```
python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --run-rmsd-validation
```

chemflow memakai ligan native yang paling dekat dengan pusat kotak sebagai referensi
(redocking, ADMET, dan pembanding di semua analitik), yaitu ligan yang Anda pilih. Tambahkan
`--run-rmsd-validation` untuk menghitung RMSD redocking-nya.

## 5. Menjalankan pipeline

```
python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --output hasil/
```

Opsi yang sering dipakai:

| Opsi | Fungsi |
|---|---|
| `--run-rmsd-validation` | Hitung RMSD pose redocking ligan native terhadap posisi kristalnya (pada posisi asli, tanpa superposisi). Di bawah 2 Angstrom berarti protokol docking dapat dipercaya. Native di-dock ulang dan kompleks referensinya dibuat di setiap run kecuali `--no-native`. |
| `--n-replicates 3` | Ulangi tiap docking 3 kali dengan seed berbeda untuk menilai konsistensi. |
| `--exhaustiveness 16` | Ketelitian pencarian Vina (default 8). Lebih besar berarti lebih teliti dan lebih lama. |
| `--merge-mode all` | Simpan semua pose semua replikat sebagai kompleks terpisah (default hanya pose terbaik). |
| `--no-native` | Jangan sertakan ligan native sebagai referensi (lihat bagian 5.2). |
| `--no-similarity` | Jangan jalankan ekspor interaksi BIOVIA dan similaritas walau BIOVIA terdeteksi (bagian 8). |
| `--gcms data-gcms/` | Tambahkan analisis GC-MS opsional setelah analitik (bagian 9). |
| `--plot-max-rows 30`, `--plot-max-cols 20` | Batas ligan (baris) dan kolom per gambar. Grafik yang lebih besar dipotong otomatis menjadi beberapa bagian, `0` mematikan pemotongan. |
| `--admet-file file.csv` | Pakai file hasil ADMETLab3 (lihat bagian 6). |
| `--no-admet` | Lewati ADMET. |
| `--dpi 600`, `--figure-formats png svg pdf` | Resolusi dan format tambahan grafik. |
| `--no-progress` | Matikan progress bar. |
| `--vina-version 1.2.5` | Pilih versi AutoDock Vina tertentu. |

Seluruh opsi: `python -m chemflow run --help`.

### 5.1 Melanjutkan run yang terhenti (`resume`)

Run panjang aman dari terminal yang tertutup, Ctrl+C yang tidak sengaja, atau
komputer yang mati. Setiap ligan yang selesai disiapkan, setiap reseptor beserta
gridbox pilihan Anda, setiap run Vina, dan setiap hasil ADMET langsung disimpan
sebagai checkpoint di `hasil/_state/` dan di samping berkasnya. Lanjutkan dari
titik terakhir hanya dengan folder outputnya:

```
python -m chemflow resume --output hasil/
```

- Semua pengaturan (Excel, exhaustiveness, replikasi, dan seterusnya) diambil dari
  run asli. Salinan Excel input disimpan di `_state/inputs/`, jadi mengedit atau
  memindahkan file asli tidak berpengaruh. Folder `hasil/` juga boleh dipindah.
- Yang sudah selesai tidak diulang: pencarian PubChem, preparasi, ADMET, reseptor
  (tanpa pertanyaan gridbox ulang), dan run Vina yang sukses. Run Vina yang gagal
  atau terputus di tengah dijalankan ulang.
- Opsi yang boleh diganti: `--no-progress`, `--verbose`, `--log-level`,
  `--openbabel-path`, `--vina-executable` (bila lokasinya berubah).
- Pada run yang sudah selesai, `resume` hanya membuat ulang laporan Excel dan
  grafik dari checkpoint, cepat dan tanpa docking ulang.
- Menjalankan `chemflow run` lagi ke folder yang sama memulai run baru dan
  menimpa checkpoint; chemflow memberi peringatan bila folder itu berisi run
  yang belum selesai.
- Bila `Ctrl+C`, chemflow menghentikan proses Vina yang sedang berjalan, mencetak
  perintah `resume`, dan keluar dengan kode 130.

### 5.2 Ligan native sebagai pembanding

Ligan native (ligan kokristal pada struktur PDB) otomatis ikut sebagai grup
**Native** pada semua analitik agar ligan uji bisa dibandingkan dengan
referensinya: Lipinski, prediksi ADMET, ΔG hasil redocking (parameter dan jumlah
replikasi sama dengan ligan uji), heatmap, PCA, HCA, dan radar. Untuk tiap
reseptor dipakai native yang paling dekat dengan pusat kotak (paling jauh 8
Angstrom, supaya situs alosterik tidak dibandingkan dengan native yang salah).
Matikan dengan `--no-native`.

`--run-rmsd-validation` menambahkan penghitungan RMSD dari pose terbaik hasil
redocking native. RMSD dihitung terhadap koordinat kristal pada posisi asli, tanpa
superposisi (`rdMolAlign.CalcRMS`, memperhitungkan simetri molekul). Pose Vina
berada pada kerangka koordinat yang sama dengan struktur kristal, sehingga pose
yang bergeser di dalam kantong ikat ikut terhitung sebagai selisih.

## 6. ADMET: otomatis atau dari file

Secara default chemflow mengirim SMILES ke ADMETLab3 dan mengambil hasilnya.
Karena situs itu sering sibuk, membatasi permintaan, atau sedang perawatan,
chemflow mencoba ulang otomatis beberapa kali. Jika tetap sulit, gunakan file
hasil unduhan:

1. Buka ADMETLab3 (menu Screening), kirim SMILES semua ligan **dengan urutan
   yang sama seperti di Excel ligan**, lalu unduh hasilnya sebagai CSV atau Excel.
2. Jalankan chemflow dengan file itu:
   ```
   python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --admet-file hasil_admetlab.csv
   ```

Aturan pemetaan (posisional, tanpa kolom nama):

- Baris ke-N file ADMET adalah ligan ke-N di Excel ligan.
- Format tidy: urutan baris Excel dari atas ke bawah.
- Format wide: kolom dari kiri ke kanan, tiap kolom dari atas ke bawah.
- Jumlah baris file harus sama dengan jumlah ligan di Excel, jika tidak chemflow
  berhenti dengan pesan yang jelas sebelum docking dimulai.
- **Senyawa yang sama di beberapa grup** (mis. Aspirin di grup 1 dan grup 2)
  dihitung sebagai ligan terpisah per grup, tetapi ADMET-nya identik. File boleh
  memuat baris untuk **SMILES unik saja** (urutan kemunculan pertama): baris itu
  disalin ke semua ligan kembar. Jalur otomatis bekerja sama: SMILES unik dikirim
  sekali ke ADMETLab3 lalu hasilnya disalin ke tiap grup sesuai urutan kirim.
- Jika file memuat kolom `raw_smiles` atau `smiles`, chemflow mencocokkannya
  dengan SMILES ligan dan memberi peringatan jika ada yang tidak cocok.

Format yang didukung: `.csv` dan `.xlsx` (sheet pertama).

## 7. Membaca hasil

```
hasil/
├── ligands/<nama>/        gambar 2D, PDB, PDBQT per ligan (dan per ligan native: NATIVE_*)
├── receptors/<kunci>/     PDBQT docking dan PDB bersih per reseptor
├── docking/<kunci>/<ligan>/      pose dan log tiap run
├── complexes/<kunci>/     kompleks PDB + sidecar .json (NATIVE_* = referensi kristal native)
├── analytics/             seluruh grafik
├── interaksi/<kunci>/     diagram 2D (.png) dan tabel Non-bond (.xlsx) per kompleks (bila BIOVIA dipakai)
├── gcms/                  hasil analisis GC-MS (bila dijalankan, bagian 9)
├── _state/                config, salinan input, dan checkpoint untuk `resume`
├── hasil_chemflow.xlsx    tabel hasil lengkap
└── chemflow.log
```

`hasil_chemflow.xlsx` berisi sheet (muncul sesuai fitur yang aktif):

| Sheet | Isi |
|---|---|
| Ringkasan Ligan | Status tiap senyawa dan `nama_file` (nama folder dan file yang dipakai untuk senyawa itu). |
| Hasil Docking | Afinitas (kcal/mol) tiap ligan terhadap tiap reseptor. Makin negatif, ikatan makin kuat. |
| Fisikokimia (Lipinski) | MW, LogP, HBD, HBA, pelanggaran Ro5. |
| ADMET | Seluruh kolom ADMETLab3, diurutkan per kategori dengan header berwarna per kategori. Sel hijau berarti baik, kuning sedang, merah buruk. |
| Legenda ADMET | Kategori, satuan, ambang batas, dan rujukan tiap parameter. |
| Validasi RMSD | RMSD redocking (pada posisi asli, tanpa superposisi) dan afinitas redocking ligan native. |
| Statistik Replikasi | Rata-rata, simpangan baku, afinitas terbaik antar replikat, dan `delta_vs_native` (selisih terhadap ΔG native pada reseptor yang sama, negatif berarti lebih kuat dari native). |
| Ringkasan per Grup | Jumlah ligan, rata-rata sifat fisikokimia, persen lolos Ro5, dan skor tiap kategori ADMET per grup (termasuk grup Native). |
| Docking per Grup | ΔG rata-rata, simpangan baku, dan terbaik per reseptor x grup, ΔG native, dan persen ligan yang lebih baik dari native. |

Kolom `group` ada di sheet ligan, docking, Lipinski, ADMET, dan statistik. Ligan
native muncul dengan grup `Native` dan `tipe = native` di Ringkasan Ligan.

Grafik di `analytics/`:

| File | Isi |
|---|---|
| `bar_affinity.png` | Peringkat afinitas docking. |
| `radar_combined.png` | Profil gabungan afinitas, fisikokimia, dan skor tiap kategori ADMET untuk enam ligan dengan ΔG terbaik (reseptor terbaik per ligan). Judul menyesuaikan data yang dipakai. |
| `radar_admet_<kategori>.png` | Profil parameter satu kategori ADMET untuk delapan ligan dengan skor tertinggi (maksimal 12 parameter dengan variasi terbesar). |
| `admet_klasifikasi_<kategori>.png` | Persentase ligan baik/sedang/buruk untuk tiap parameter. |
| `heatmap_afinitas.png` | Afinitas semua ligan terhadap semua reseptor. |
| `heatmap_fisikokimia.png`, `heatmap_fisikokimia_klaster.png` | Sifat fisikokimia, dengan versi terklaster beserta dendrogram. |
| `pca_2d.png`, `pca_3d.png` | Ruang kimia senyawa per kelompok (butuh kolom `group`), bergaya jurnal: penanda dan elips kepercayaan 95% per kelompok, sumbu berlabel persen variansi. |
| `hca_dendrogram.png` | Pengelompokan hierarkis senyawa. |
| `grup_afinitas_box.png` | Sebaran ΔG per grup, satu panel per reseptor; garis putus-putus adalah ΔG native. |
| `grup_heatmap_afinitas.png`, `grup_heatmap_lebih_baik_dari_native.png` | ΔG rata-rata reseptor x grup (dengan kolom Native) dan persen ligan yang ΔG-nya sama atau lebih baik dari native. |
| `grup_admet_ringkasan.png`, `grup_admet_heatmap_<kategori>.png` | Skor ADMET rata-rata (baik 1, sedang 0,5, buruk 0) per grup x kategori dan grup x parameter. |
| `grup_admet_radar_<kategori>.png`, `grup_admet_klasifikasi_<kategori>.png` | Radar profil ADMET per grup dan bar baik/sedang/buruk, satu panel per grup. |
| `grup_fisikokimia_box.png`, `grup_radar_gabungan.png` | MW, LogP, HBD, HBA per grup dan profil gabungan per grup. |

**Pemotongan otomatis.** Bila ligan, reseptor, atau parameter terlalu banyak,
sebuah grafik dibagi menjadi beberapa gambar berakhiran `_part01of03`,
`_part02of03`, dan seterusnya (nama tetap tanpa akhiran bila muat satu gambar).
Skala warna, sumbu, dan normalisasi dihitung dari seluruh data sehingga
antar-bagian tetap sebanding: bar dan radar diurutkan menurut peringkat (bagian 1
terbaik), heatmap dipotong menjadi ubin baris x kolom (kolom Native ikut di tiap
ubin), dan dendrogram menampilkan jendela daun dari pohon yang sama. Radar
per-ligan dibatasi lima bagian. Batas diatur dengan `--plot-max-rows` dan
`--plot-max-cols`. Ligan native diberi warna berbeda dan disematkan di setiap
radar.

Kompleks di `complexes/` dapat dibuka dengan PyMOL atau BIOVIA Discovery Studio Visualizer.

## 8. Analisis similaritas interaksi

Membandingkan interaksi tiap ligan dengan ligan native memakai tabel interaksi BIOVIA
Discovery Studio (butuh ligan native terdeteksi, jangan pakai `--no-native`). Tabel itu bisa
diambil otomatis atau dibuat manual.

**Otomatis (Windows dengan BIOVIA Discovery Studio; Visualizer gratis cukup).** Tidak perlu
opsi apa pun. Bila mesin Anda Windows dan BIOVIA terdeteksi, `chemflow run` berjalan dari
docking sampai similaritas:

```
python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --output hasil/
```

Setelah analitik, chemflow membuka BIOVIA (lokasinya dideteksi otomatis, tahun terbaru),
membuka tiap kompleks di `complexes/`, menyimpan diagram 2D dan tabel Non-bond ke
`interaksi/`, lalu menghitung similaritas. Di mesin tanpa BIOVIA (atau bukan Windows) tahap
ini dilewati dengan satu baris log, dan run selesai normal. `--no-similarity` mematikannya
walau BIOVIA ada; `--similarity` memaksa: bila BIOVIA tidak tersedia, log mencatat galatnya dan
similaritas tetap dihitung dari berkas interaksi yang sudah ada (mis. hasil ekspor manual).

**Mouse dan keyboard dikunci selama ekspor** agar tidak ada klik yang salah. Input dari
otomasi tetap berjalan, input dari Anda diabaikan. Tekan **Esc tiga kali berturut-turut**
bila ingin membatalkan (lanjutkan nanti dengan `resume`); kunci juga lepas sendiri bila
otomasi macet lebih dari 2 menit. `--no-lock-input` mematikan penguncian. Ekspor saja pada
folder yang sudah ada:

```
python -m chemflow interactions --output hasil/
```

Kompleks yang hasilnya sudah lengkap dilewati, jadi ekspor yang terhenti tinggal
dijalankan lagi. Detail, deteksi instalasi, dan pemecahan masalah ada di
[`docs/biovia-interactions.md`](docs/biovia-interactions.md).

**Hanya analisis** (berkas interaksi sudah ada, hasil ekspor otomatis atau manual):

```
python -m chemflow similarity --output hasil/
```

Keluaran: `similaritas_interaksi.xlsx` (termasuk selisih ΔG bila `hasil_chemflow.xlsx`
ada di folder yang sama) dan grafik di `analytics/`: `similaritas_bar.png`,
`similaritas_vs_deltag.png`, dan `similaritas_jejak_<kunci>.png`. Konvensi
penamaan file dan detail metode ada di [`docs/similarity-analysis.md`](docs/similarity-analysis.md).

## 9. Analisis GC-MS (opsional)

Membandingkan data GC-MS (misalnya parfum asli terhadap tiruan, atau beberapa produk) dengan
kemometrik. Tidak butuh docking dan tidak memengaruhi pipeline utama; tanpa argumen GC-MS, fitur
ini tidak berjalan sama sekali.

```
python -m chemflow gcms --data data-gcms/ --output hasil/
```

Hasilnya di `hasil/gcms/`. `--data` menerima berkas, folder (rekursif), atau pola, dan format
campuran: ekspor GCMSsolution (`.xls`, `.xlsx`, `.txt`), CSV/TSV, ANDI-MS (`.cdf`), `.mzML`, dan
`.mzXML`; format dan satuan waktu retensi dikenali dari isi berkas (termasuk RT menit yang
terkali 1000 akibat ekspor Excel). Sebagai tahap tambahan pada run docking:

```
python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --output hasil/ --gcms data-gcms/
```

Menjalankan `chemflow gcms --output hasil/` lagi tanpa `--data` memakai ulang data dan
pengaturan sebelumnya, jadi opsi bisa dicoba berulang tanpa mengulang docking. Yang dihasilkan:

- `analisis_gcms.xlsx` (sampel, puncak, fitur selaras, uji per fitur dengan nilai q, VIP,
  akurasi model, skor dan loading PCA, kemiripan, alergen).
- `plots/`: kromatogram tumpang tindih dan berlabel puncak, penyelarasan RT, PCA 2D/3D gaya
  jurnal, dendrogram, peta panas fitur teratas, kemiripan, plot cermin antar kelompok, volcano,
  VIP, konfusi dan uji permutasi, serta alergen.
- `ligan_gcms.xlsx`: senyawa bernama beserta SMILES, langsung bisa jadi `--ligands` untuk docking.

Warna PCA menandai seri (nama berkas tanpa nomor ulangan) dan penanda menandai kelas (subfolder
atau kata seperti asli/tiruan pada nama); ganti lewat `--groups tabel.csv` (kolom `sample`,
`series`, `class`). Untuk memberi nama pada puncak dari data TIC, berikan `--library` (nama, RT
atau indeks retensi, CAS, SMILES). Detail metode, batasan, dan seluruh opsi ada di
[`docs/gcms-analysis.md`](docs/gcms-analysis.md).

## 10. Jika terjadi error

| Gejala | Penyebab dan solusi |
|---|---|
| `Executable 'obabel' tidak ditemukan di PATH` | OpenBabel belum terpasang atau tidak ada di PATH. Ulangi langkah 2.3 atau tambahkan `--openbabel-path`. |
| SMILES tidak ditemukan di PubChem | Nama tidak dikenali. Coba nama internasional atau isi kolom `smiles`. |
| Timeout atau error jaringan | Layanan (RCSB, PubChem, ADMETLab3, GitHub) tidak terjangkau. Coba jaringan lain atau ulangi nanti. |
| ADMETLab3 membalas 429 atau tidak menjawab | chemflow mencoba ulang otomatis. Jika tetap gagal, gunakan `--admet-file` (bagian 6) atau `--no-admet`. |
| `File ADMET ... berisi N baris, sedangkan input memuat M ligan` | Jumlah dan urutan baris file ADMET harus sama dengan ligan di Excel (bagian 6). |
| `Preparasi reseptor ... gagal` di log | Struktur PDB tidak bisa diproses (unduhan gagal, format tidak didukung, atau struktur tidak lazim). Reseptor itu dilewati dan yang lain tetap diproses; pesan lengkapnya ada di `chemflow.log`. Coba entri PDB lain untuk protein yang sama. |
| PCA atau HCA dilewati, log menyebut minimal 2 kelompok | Kolom `group` hanya berisi satu nilai dan ligan native tidak ikut (`--no-native`). Isi minimal dua kelompok atau aktifkan native. |
| Run terhenti (terminal ditutup, Ctrl+C, komputer mati) | Jalankan `python -m chemflow resume --output hasil/` (bagian 5.1). |
| Grafik terpecah menjadi `_part01of03` dan seterusnya | Ligan atau reseptor terlalu banyak untuk satu gambar. Naikkan `--plot-max-rows` atau `--plot-max-cols`, atau `0` untuk satu gambar utuh. |
| Proses berhenti menunggu jawaban | chemflow menunggu Anda memilih ligan native untuk gridbox. Isi `center_x/y/z` di Excel (bisa dibuat dengan `chemflow receptor-config`) atau gunakan `--no-interactive-gridbox`. |
| `Gagal mengunduh PDB ...` saat `receptor-config` atau `run` | Kode PDB salah, atau strukturnya tidak tersedia dalam format `.pdb` (sebagian struktur besar hanya ada dalam mmCIF). Periksa kode di rcsb.org atau pakai entri lain. |
| `Similaritas interaksi dilewati: BIOVIA tidak terdeteksi` | Bukan error. Mesin bukan Windows atau BIOVIA belum terpasang, jadi tahap otomatis dilewati. Pasang BIOVIA Discovery Studio dan `pip install pywinauto pyperclip psutil`, atau jalankan `chemflow interactions` nanti. Berkas interaksi manual tetap bisa dianalisis dengan `chemflow similarity`. |
| `BIOVIA Discovery Studio tidak ditemukan` atau `Dependensi otomasi Windows belum lengkap` | Pada `--similarity` (paksa) hanya tercatat di log dan similaritas memakai berkas interaksi yang ada; pada `chemflow interactions` perintah berhenti. Pasang BIOVIA dan paket di atas, atau berikan `--biovia-exe`. |
| `Fokus jendela BIOVIA hilang` | Jendela lain merebut fokus selama ekspor. Jalankan lagi perintah yang sama, kompleks yang selesai dilewati. |
| `Dibatalkan pengguna (Esc tiga kali)` | Anda membatalkan ekspor. Jalankan lagi perintah yang sama atau `resume`. |
| `Tidak ada berkas GC-MS`, `tidak ada kromatogram, tabel puncak, atau tabel fitur` | Folder `--data` tidak berisi format yang didukung, atau isi berkas tidak dikenali (butuh kolom waktu dan intensitas, atau RT dan Area/Height). Lihat bagian 9. |
| Analisis GC-MS menyebut model terawasi dilewati | Model terawasi butuh minimal dua kelas, tiap kelas minimal dua sampel, dan enam sampel. PCA, HCA, dan kemiripan tetap dibuat. |
| Gagal menulis grafik di Windows | File gambar yang sama sedang terbuka di aplikasi lain. Tutup lalu jalankan ulang. |
| `Path folder output panjang ... nama file ligan dipendekkan` | Path folder output sudah mendekati batas 260 karakter Windows, jadi nama file ligan dipotong. Pilih folder output yang lebih pendek agar nama tetap utuh. |

Log lengkap ada di `chemflow.log` pada folder hasil.

## 11. Untuk pengguna lanjutan

### Semua opsi `chemflow run`

| Grup | Argumen |
|---|---|
| Input | `--ligands`, `--receptors` (wajib), `--output` |
| Pemetaan kolom | `--ligand-name-col`, `--ligand-smiles-col`, `--ligand-group-col`, `--receptor-pdb-col` |
| Gridbox | `--default-box-size`, `--box-padding`, `--no-interactive-gridbox` |
| Preparasi ligan | `--force-field {MMFF94,UFF}`, `--minimize-max-iters`, `--no-2d-image` |
| Preparasi reseptor | `--keep-waters`, `--keep-hetero-ligands`, `--no-keep-metals`, `--kollman-fallback {zero,gasteiger}` |
| Docking | `--vina-version`, `--vina-executable`, `--exhaustiveness`, `--num-modes`, `--energy-range`, `--seed`, `--n-replicates` |
| Merge | `--merge-mode {best,all}` |
| Ligan native | `--no-native` |
| Interaksi dan similaritas (BIOVIA) | `--similarity` / `--no-similarity` (bawaan: otomatis bila terdeteksi), `--biovia-exe`, `--biovia-timeout`, `--no-lock-input` |
| Validasi RMSD | `--run-rmsd-validation`, `--rmsd-threshold-good`, `--rmsd-threshold-acceptable` |
| OpenBabel | `--openbabel-path` |
| ADMET | `--no-admet`, `--admet-file`, `--admet-batch-size`, `--admet-ssl-verify` |
| PubChem | `--no-pubchem-fetch`, `--no-pubchem-interactive-fallback` |
| Analitik | `--no-charts`, `--no-pca`, `--no-hca`, `--no-heatmap`, `--dpi`, `--figure-formats`, `--plot-max-rows`, `--plot-max-cols` |
| Analisis GC-MS (opsional) | `--gcms`, `--gcms-groups`, `--gcms-library` |
| Logging | `--verbose`, `--log-level`, `--no-progress` |

### Subperintah lain

Setiap perintah `chemflow`, termasuk `--help`, menampilkan header logo
ASCII-art lebih dulu. Header hanya muncul di CLI; pemakaian sebagai library
tidak mencetaknya.

- `chemflow init [--output DIR] [--format tidy|wide|both] [--skip-check]`: template Excel dan cek mesin.
- `chemflow resume --output DIR [--no-progress] [--verbose] [--log-level L] [--openbabel-path P] [--vina-executable P] [--biovia-exe P]`: lanjutkan run yang terhenti dari checkpoint terakhir.
- `chemflow receptor-config`: susun Excel reseptor secara interaktif (kode PDB, pilih ligan native). Tanpa opsi.
- `chemflow list-vina-versions`: versi AutoDock Vina yang kompatibel dengan mesin ini.
- `chemflow interactions --output DIR [--interactions-dir DIR] [--interaction-suffix S] [--receptor KUNCI] [--force] [--biovia-exe P] [--biovia-timeout N] [--no-lock-input] [--no-progress]`: ekspor diagram 2D dan tabel interaksi tiap kompleks lewat BIOVIA (Windows).
- `chemflow similarity --output DIR [--interactions-dir DIR] [--interaction-suffix S] [--result-filename F] [--no-plots] [--dpi N] [--figure-formats ...] [--plot-max-rows N] [--plot-max-cols N]`.
- `chemflow gcms --output DIR [--data PATH ...] [--groups F] [--library F] [--alkanes F] [--label-by {auto,class,series}] [--rt-unit U] [--rt-range MULAI AKHIR] [--no-baseline] [--smooth-window M] [--no-align] [--max-shift M] [--min-snr N] [--min-prominence F] [--peak-tolerance M] [--min-presence F] [--feature-mode {peaks,bins}] [--bin-width M] [--normalization N] [--transform T] [--scaling S] [--permutations N] [--rt-tolerance M] [--ri-tolerance N] [--top-features N] [--seed N] [--no-plots] [--dpi N] [--figure-formats ...]`: analisis GC-MS opsional tanpa docking (bagian 9).

### Dokumentasi teknis

Diagram alur dan penjelasan algoritma ada di [`docs/`](docs/README.md).

### Pemakaian sebagai library

```python
from chemflow import Pipeline, PipelineConfig

config = PipelineConfig(ligand_excel="ligan.xlsx", receptor_excel="reseptor.xlsx", output_dir="hasil")
Pipeline(config).run()
```

Komponen individual (preparasi, docking, ADMET, grafik, similaritas, GC-MS) juga bisa
dipakai langsung. Contoh ada di [`docs/library-usage.md`](docs/library-usage.md).

### Test

```
pytest tests/ -v
```

Test bersifat unit dan tidak memanggil OpenBabel, Vina, atau layanan online.

### Referensi

- Lipinski et al. 1997, *Adv. Drug Deliv. Rev.*, Rule of Five.
- Fu et al. 2024, *Nucleic Acids Research* 52(W1):W422-W431, ADMETLab 3.0.
- Morris et al. 2009, *J. Comput. Chem.*, tipe atom AutoDock4/PDBQT.
- Cornell et al. 1995, *JACS* 117:5179; Hornak et al. 2006, *Proteins* 65(3):712-725, muatan AMBER ff99SB.
- Hevener et al. 2009, *J. Chem. Inf. Model.* 49(2):444-460, kriteria RMSD redocking di bawah 2 Angstrom.
- Pratama, Poerwono, Siswodihardjo 2021, *Indonesian Journal of Biotechnology* 26(1):54-60, DOI 10.22146/ijbiotech.62194.
- Aghoutane et al. 2023, *Micromachines* 14(3):524, DOI 10.3390/mi14030524, gaya PCA dan analisis GC-MS parfum.
- Eilers dan Boelens 2005 (baseline ALS); Savitzky dan Golay 1964, *Anal. Chem.* 36(8):1627-1639; Dieterle et al. 2006, *Anal. Chem.* 78(13):4281-4290 (normalisasi PQN); Benjamini dan Hochberg 1995, *J. R. Stat. Soc. B* 57(1):289-300 (FDR).
- Okabe & Ito 2008, palet warna aman buta warna.

### Lisensi dan pengembang

MIT, lihat [`LICENSE`](LICENSE). Pengembang: Arif Maulana Azis ([github.com/Arifmaulanaazis](https://github.com/Arifmaulanaazis)).
