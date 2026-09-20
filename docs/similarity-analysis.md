# Analisis Similaritas Interaksi

Fitur opsional yang membandingkan pola kontak protein-ligan tiap ligan uji dengan ligan
native. Datanya berupa tabel interaksi tiap kompleks dari BIOVIA Discovery Studio. Tabel itu
bisa diambil otomatis lewat GUI BIOVIA (dijalankan sendiri oleh `chemflow run` di Windows bila
BIOVIA terdeteksi, atau lewat `chemflow interactions`, lihat
[biovia-interactions.md](biovia-interactions.md)), atau dibuat manual di BIOVIA Discovery
Studio Visualizer. Analisis bisa di-rerun kapan saja pada folder output `chemflow run` yang
sudah ada, tanpa docking ulang.

Metode perhitungan: Pratama et al. (2021), "Introducing a two-dimensional
graph of docking score difference vs. similarity of ligand-receptor
interactions", *Indonesian Journal of Biotechnology* 26(1):54-60,
DOI [10.22146/ijbiotech.62194](https://doi.org/10.22146/ijbiotech.62194).

## Prasyarat

1. Jalankan `chemflow run` (butuh ligan native terdeteksi di struktur PDB
   reseptor dan tanpa `--no-native`), supaya pipeline juga
   menghasilkan kompleks referensi native (`NATIVE_<label>_complex.pdb`
   di `complexes/<kunci>/`, lihat `merge-and-analytics.md`).
2. Sediakan berkas interaksi tiap file `.pdb` di `complexes/<kunci>/` (referensi native
   maupun ligan uji), salah satu cara:
   - Otomatis: `chemflow run` mengekspornya sendiri bila Windows dan BIOVIA terdeteksi
     (`--no-similarity` mematikan, `--similarity` memaksa), atau `chemflow interactions --output hasil/`
     pada folder yang sudah ada. Mouse dan keyboard dikunci selama ekspor (Esc tiga kali membatalkan).
   - Manual: buka tiap kompleks di BIOVIA Discovery Studio Visualizer, jalankan analisis
     interaksi ligan-reseptornya, lalu export tabel Non-bond ke Excel dengan nama sesuai
     konvensi di bawah.

## Konvensi penamaan file interaksi

Untuk setiap file kompleks `complexes/<kunci>/<basis>.pdb`, file
interaksi hasil export BIOVIA harus disimpan di:

```
<interactions_dir>/<kunci>/<basis>_interaksi.xlsx
```

`<interactions_dir>` default adalah `<output>/interaksi` (bisa diubah
lewat `--interactions-dir`), akhiran `_interaksi.xlsx` bisa diubah lewat
`--interaction-suffix`. Struktur folder `<interactions_dir>` membayangi
struktur `complexes/` persis (satu subfolder per reseptor).

Contoh, untuk reseptor `6LU7` (kunci `6LU7_R001`, yaitu kode PDB dan nomor baris
Excel reseptor) dengan native `NATIVE_ASP_X1_complex.pdb` dan ligan uji
`Quercetin_complex.pdb`:

```
hasil/
  complexes/
    6LU7_R001/
      NATIVE_ASP_X1_complex.pdb
      NATIVE_ASP_X1_complex.json
      Quercetin_complex.pdb
      Quercetin_complex.json
  interaksi/
    6LU7_R001/
      NATIVE_ASP_X1_complex_interaksi.xlsx   tabel interaksi native
      NATIVE_ASP_X1_complex_interaksi.png    diagram 2D (hanya dari ekspor otomatis)
      Quercetin_complex_interaksi.xlsx        tabel interaksi ligan uji
      Quercetin_complex_interaksi.png
```

## Format file interaksi

Sumbernya tabel Non-bond BIOVIA. Kolom yang dipakai: Category, Types (atau Type/Subtype),
From, From Chemistry, To, To Chemistry. Bila baris pertama berisi judul kolom, kolom dicari
lewat namanya, jadi urutan dan kolom tambahan (Distance, Angle, ID, dan lain-lain) tidak
berpengaruh; ini format yang ditulis ekspor otomatis. Tanpa judul dipakai urutan bawaan
Discovery Studio: Name, Visible atau Rendered, Color, Parent atau Style, Distance atau ID,
Category, Types, From, From Chemistry, To, To Chemistry (11 kolom pertama).

Sisi interaksi ditulis `Chain:RESNAME+RESNUM:ATOM` (mis. `A:SER195:OG`). Interaksi pi
(Pi-Sigma, Pi-Pi) menuliskan cincin aromatik tanpa nama atom (`A:PHE330`), dan tetap
terbaca. Berkas yang hanya berisi judul berarti kompleks tanpa interaksi. Baris intra-ligand
(kedua sisi chain ligan) dan intra-protein (kedua sisi chain protein) otomatis disaring,
hanya interaksi protein-ligan murni yang dipakai.

## Menjalankan analisis

```bash
python -m chemflow similarity --output hasil/
```

Perintah ini hanya membaca berkas interaksi yang sudah ada dan tidak membuka BIOVIA. Untuk
mengekspor interaksi sekaligus, biarkan `chemflow run` menjalankannya otomatis atau jalankan
`chemflow interactions --output hasil/` lebih dulu.

Opsi tambahan: `--no-plots` (lewati grafik), `--dpi N`, dan
`--figure-formats png svg pdf` (PNG selalu ditulis).

```mermaid
flowchart TD
    Start([chemflow similarity --output hasil/]) --> ScanComplex[Scan hasil/complexes/*/*_complex.pdb]
    ScanComplex --> FindNative{Ada kompleks is_native=true di sidecar JSON?}
    FindNative -->|Tidak| SkipReceptor[["Warning: reseptor dilewati, tidak ada baseline"]]
    FindNative -->|Ya| CheckRefFile{File interaksi referensi ada?}
    CheckRefFile -->|Tidak| SkipReceptor2[["Warning: reseptor dilewati, minta pengguna buat file itu"]]
    CheckRefFile -->|Ya| ReadRef[Baca & saring interaksi protein-ligan referensi]
    ReadRef --> LoopLigand[Untuk setiap kompleks ligan uji lain di reseptor ini]
    LoopLigand --> CheckTestFile{File interaksi ligan ini ada?}
    CheckTestFile -->|Tidak| SkipLigand[["Warning: ligan ini dilewati, lanjut ke ligan lain"]]
    CheckTestFile -->|Ya| ReadTest[Baca & saring interaksi protein-ligan ligan uji]
    ReadTest --> Compute[compute_similarity: Eq. 2 Pratama et al. 2021]
    Compute --> LoopLigand
    SkipLigand --> LoopLigand
    LoopLigand --> Affinity[Baca afinitas dari hasil_chemflow.xlsx bila ada: selisih delta G]
    Affinity --> Export[export_similarity_results: 1 file Excel semua hasil]
    Export --> Plots[SimilarityPlotter: bar, similaritas vs delta G, heatmap jejak kontak]
    Plots --> End([hasil/similaritas_interaksi.xlsx dan grafik di hasil/analytics/])
```

Setiap kegagalan per-file (file belum dibuat, kolom tidak lengkap, format
tidak dikenali) hanya melewati pasangan/reseptor itu dengan warning yang
jelas (menyebut nama file & path yang diharapkan), tidak menggagalkan
seluruh analisis. Ini disengaja supaya analisis bisa dijalankan bertahap,
mis. saat berkas interaksi baru sebagian tersedia.

## Rumus similaritas (Persamaan 2, Pratama et al. 2021)

```
%similarity = (0.5 * (nAAtest / nAAref) + 0.5 * (intAAtest / intAAref)) * 100%
```

- `nAAtest / nAAref`: rasio jumlah residu (identitas posisi+nama saja)
  yang berinteraksi dengan ligan uji DAN juga berinteraksi dengan ligan
  referensi, dibagi total residu yang berinteraksi dengan referensi.
- `intAAtest / intAAref`: rasio jumlah pasangan (residu, tipe interaksi)
  yang identik di ligan uji dan referensi, dibagi total pasangan itu di
  referensi. Tipe interaksi memakai kolom "Type/Subtype" BIOVIA (mis.
  "Conventional Hydrogen Bond", "Pi-Alkyl"), bukan kolom "Category" yang
  lebih kasar.

## Selisih ΔG dan grafik

Jika `hasil_chemflow.xlsx` ada di folder output, afinitas tiap ligan uji
(sheet "Statistik Replikasi") dan afinitas ligan native dibaca otomatis. Afinitas
native diambil dari sheet "Validasi RMSD" (kolom `redock_affinity`) bila ada, dan bila
tidak (run tanpa `--run-rmsd-validation`) dari ΔG docking native pada sheet "Statistik
Replikasi" (baris berkolom `group = Native`). Selisih
`delta_g` (ΔG uji dikurangi ΔG referensi) dicatat di Excel. Nilai negatif berarti
ligan uji berikatan lebih kuat daripada ligan native. Tanpa file itu, kolom
ΔG dikosongkan dan grafik yang membutuhkannya dilewati.

Grafik yang dihasilkan di `<output>/analytics/`:

| File | Isi |
|---|---|
| `similaritas_bar.png` | Peringkat similaritas gabungan beserta komponen kemiripan residu dan kemiripan tipe interaksi. |
| `similaritas_vs_deltag.png` | Grafik dua dimensi selisih ΔG (sumbu x) terhadap similaritas interaksi (sumbu y) seperti diusulkan Pratama et al. (2021). Ligan terbaik berada di kiri atas: afinitas lebih kuat dan interaksi lebih mirip dengan native. |
| `similaritas_jejak_<kunci>.png` | Heatmap terklaster ligan x residu yang menunjukkan residu mana yang dikontak tiap ligan, dengan ligan native sebagai baris acuan. Ligan dengan jejak kontak serupa mengelompok pada dendrogram. |

## Pemakaian sebagai library

```python
from chemflow import run_similarity_report

report = run_similarity_report("hasil/")           # hitung, tulis Excel, dan buat grafik
print(len(report.results), report.workbook, len(report.plots))
```

Langkahnya bisa dipakai terpisah:

```python
from chemflow import SimilarityAnalyzer, export_similarity_results

results = SimilarityAnalyzer().analyze_output_dir("hasil/")
export_similarity_results(results, "hasil/similaritas_interaksi.xlsx")
```

Grafik dari hasil yang sama:

```python
from chemflow import SimilarityPlotter

SimilarityPlotter("hasil/analytics", formats=("png", "svg")).plot_all(results)
```

Atau langsung dari kontak protein-ligan yang sudah diparse sendiri:

```python
from chemflow import compute_similarity

result = compute_similarity(test_contacts, ref_contacts, ligand_name="Quercetin", reference_name="Celecoxib")
print(result.overall_similarity_pct)
```
