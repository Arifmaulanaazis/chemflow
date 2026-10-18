# Inventaris peninjauan untuk 3.0.0

Inventaris awal mencakup 73 modul Python (15.475 baris), 62 berkas pengujian
(9.165 baris), 13 dokumen teknis (1.846 baris), README, serta PPTX/PDF workshop
50 slide/halaman. Daftar ini berasal dari pembacaan file dan inventaris simbol
AST; bukan ukuran cakupan pengujian atau audit keamanan independen.

Keputusan integrasi mengikuti batas yang sudah ada:

| Area sumber | Integrasi WebUI |
|---|---|
| cli.py, config.py | Schema form mengikuti argparse; output/executable dan prompt terminal dibatasi oleh adapter |
| pipeline.py, state.py, checkpoints.py | Proses CLI terisolasi, pembacaan tahap/checkpoint, resume tanpa menyalin rumus ilmiah |
| chem/, io/, templates.py | Unggah input, job template, penyusunan workbook reseptor lewat native/manual |
| docking/ | Parameter Vina/RMSD/merge tetap dari CLI; pose dan kompleks dipreview lewat NGL |
| analytics/, admet/ | Grafik publikasi dan workbook dipreview/diunduh; kegagalan parsial tetap terlihat pada log |
| gcms/ | Alur GC-MS mandiri dan pengaturan lanjutan yang sama dengan CLI |
| interaction/, similarity/ | Ekspor BIOVIA melalui job serial Windows; diagram, tabel dan laporan bisa dipreview lintas OS |
| utils/, system_check.py | Logging/proses lama dipertahankan; pemeriksaan mesin tersedia dalam job init |
| tests/ | Suite regresi lama dipertahankan, ditambah integrasi API dan browser nyata |
| docs/, PPTX, PDF | Panduan WebUI/arsitektur/pengujian baru; materi ilmiah lama dipertahankan dengan penanda arsip |

Materi workshop kini menambah enam slide 3.0.0. Statistik versi 2.1.0 diberi
penanda arsip; tidak disajikan sebagai pengukuran baru. Cache angka satu grafik
lama diselaraskan dengan sel workbook tertanam tanpa mengubah data sumbernya.

Lihat [arsitektur](webui-architecture.md) untuk kontrak modul dan
[pengujian](testing-3.0.0.md) untuk hasil eksekusi aktual dan batas verifikasinya.
