# Docking: Resolusi Vina dan Matriks Docking

Implementasi: `chemflow.docking.vina_manager.VinaReleaseManager`,
`chemflow.docking.vina_runner.VinaRunner`, `chemflow.docking.docking_matrix.DockingOrchestrator`.

## Resolusi executable AutoDock Vina

Resolusi tidak pernah bergantung pada PATH sistem. Baik override manual
maupun hasil auto-download selalu berupa path absolut yang langsung
dieksekusi.

```mermaid
flowchart TD
    Start([Mulai: vina_version opsional, vina_executable override opsional]) --> Explicit{vina_executable diberikan eksplisit?}
    Explicit -->|Ya| UseExplicit([Pakai path itu langsung])
    Explicit -->|Tidak| Cached{Cache lokal punya binary versi cocok?}
    Cached -->|Ya| UseCache([Pakai binary dari cache])
    Cached -->|Tidak| FetchApi[["GET GitHub API: releases AutoDock-Vina"]]
    FetchApi --> Classify[Klasifikasi tiap asset via pola regex per era penamaan]
    Classify --> Filter[Filter: hanya asset yang cocok OS dan arsitektur host]
    Filter --> Compatible{Ada versi kompatibel?}
    Compatible -->|Tidak| FailVina[["raise RuntimeError, mis. Windows + versi 1.2.0-1.2.2 memang tidak ada build Windows"]]
    Compatible -->|Ya| Pick[Pilih versi: terbaru kompatibel default, atau sesuai --vina-version]
    Pick --> Download[["Download binary, simpan ke cache, chmod +x di POSIX"]]
    Download --> End([Path executable Vina siap pakai])
```

Era penamaan asset: legacy 1.1.2 (`autodock_vina_1_1_2_*`), transisi
1.2.0 sampai 1.2.3 (`vina_X_linux_x86_64`, dan Windows baru muncul di
1.2.3), current 1.2.4 dan seterusnya (`vina_X_win.exe`,
`vina_X_linux_aarch64`, dan seterusnya). Versi 1.2.0 sampai 1.2.2 tidak
menyediakan build Windows sama sekali.

## Matriks Docking

```mermaid
flowchart TD
    Start([Mulai: ligand_pdbqt_map, targets, n_replicates]) --> LoopTarget[Loop: tiap target reseptor]
    LoopTarget --> LoopLigand[Loop: tiap ligan siap-docking]
    LoopLigand --> LoopRep[Loop: tiap replikat 1..n, seed = base_seed+replikat-1 atau acak]
    LoopRep --> BuildCmd[Bangun perintah Vina: receptor, ligand, out, exhaustiveness, num_modes, energy_range, gridbox, seed opsional. Tanpa --log]
    BuildCmd --> Stream[["Popen, stream stdout baris per baris, tulis manual ke file .log"]]
    Stream --> ExitCode{exit code != 0?}
    ExitCode -->|Ya| FailRun[["raise RuntimeError dengan 30 baris log terakhir, pasangan ini ditandai gagal, docking lain tetap lanjut"]]
    ExitCode -->|Tidak| ParseTable[Parse tabel skor: cari baris separator lalu baris berawalan angka]
    ParseTable --> Result([DockingRunResult per ligan, reseptor, replikat])
    Result --> Stats[compute_replicate_stats: agregasi mean dan std afinitas]
```

Mendukung multi-PDB (setiap baris reseptor unik di-dock terhadap semua
ligan) dan multi-situs (kode PDB yang sama dengan gridbox berbeda pada
baris berbeda menghasilkan kunci target yang berbeda pula).

## Sumber gridbox

Gridbox dibaca dari kolom `center_x/y/z` dan `size_x/y/z` Excel reseptor.
Jika kosong, pipeline meminta pengguna memilih ligan native saat run
berjalan. Pengguna yang belum tahu koordinatnya dapat menyusun Excel itu
lebih dulu dengan `chemflow receptor-config`
(lihat [Konfigurasi Reseptor Interaktif](receptor-config.md)).

### Ukuran default dari ligan native

Ukuran yang tidak diberikan diturunkan dari ligan native, bukan angka tetap.
`GridBox.suggested_size(extent, padding=8, min_size=18, max_size=30)` menghasilkan
sisi kubus: ekstensi terpanjang native (`NativeLigand.extent`) ditambah padding
(`--box-padding`, default 8 Angstrom), minimal 18, dibulatkan ke atas, maksimal 30.
Aturan yang sama dipakai `receptor-config`.

Urutan penentuan ukuran per sumbu:

1. kolom `size_x/y/z` di Excel;
2. kolom ukuran seragam (`gridbox` atau `box_size`);
3. ukuran dari ligan native (interaktif: ligan yang dipilih, Enter menerima; jalur
   Excel dengan pusat tanpa ukuran: native terdekat dengan jarak pusat paling jauh
   `native_match_radius`, default 8 Angstrom);
4. `default_box_size` (default 20), cadangan bila struktur tidak punya native.

Log mencatat ukuran dan sumbernya. Saat memilih ligan interaktif, tabel menampilkan
kolom "Kotak" (ukuran default tiap ligan) dan jawaban `n` membuka prompt ukuran yang
menerima satu angka (kubus) atau tiga angka `x y z`.

## Checkpoint per run

`run_matrix(..., resume=False)` menulis `rep<NN>.json` (seed, pose, error, path relatif)
di samping keluaran Vina setiap kali satu run selesai, sukses maupun gagal.
Dengan `resume=True`, run yang sukses dan PDBQT keluarannya masih ada dimuat
(`DockingRunResult.reused = True`, seed asli dipertahankan) tanpa menjalankan Vina;
yang gagal, rusak, atau tak punya checkpoint dijalankan ulang.
