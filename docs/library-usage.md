# Pemakaian sebagai Library

chemflow bisa dipakai lewat CLI (`python -m chemflow`) atau langsung
diimpor sebagai library Python di skrip atau notebook sendiri. Instalasi
cukup clone repo lalu:

```bash
pip install -r requirements.txt
pip install -e .
```

Header ASCII-art hanya dicetak oleh CLI. Memakai chemflow sebagai library
tidak mencetak header apa pun.

## Pipeline penuh

Setara dengan `chemflow run` di CLI, tapi dari kode Python:

```python
from chemflow import Pipeline, PipelineConfig

config = PipelineConfig(
    ligand_excel="ligan.xlsx",
    receptor_excel="reseptor.xlsx",
    output_dir="hasil",
    exhaustiveness=16,
    n_replicates=3,
    run_rmsd_validation=True,
)

exit_code = Pipeline(config).run()          # 0 sukses, 1 fatal, 130 dihentikan pengguna (Ctrl+C)
```

Melanjutkan run yang terhenti (setara `chemflow resume --output hasil`):

```python
from chemflow import Pipeline, RunState

config = RunState("hasil").load_config()     # config dan salinan Excel input dari hasil/_state/
config.log_level = "DEBUG"                   # setelan boleh diubah sebelum dilanjutkan
exit_code = Pipeline(config, resume=True).run()
```

`PipelineConfig.to_dict()` dan `from_dict()` menyerialisasi seluruh konfigurasi ke JSON. Parameter baru:
`include_native` (default True), `native_match_radius` (8 Angstrom), `box_padding`, `plot_max_rows`,
`plot_max_cols`.

## Komponen individual

Setiap tahap juga bisa dipakai berdiri sendiri, tanpa Excel maupun CLI.

### Preparasi ligan

```python
from pathlib import Path
from chemflow import LigandPreparer, OpenBabelConverter

converter = OpenBabelConverter()  # cari obabel di PATH
preparer = LigandPreparer(converter)

result = preparer.prepare("Quercetin", "Oc1cc(O)c2c(=O)c(O)c(-c3ccc(O)c(O)c3)oc2c1", Path("output/ligan"))
print(result.pdbqt_path, result.force_field_used, result.minimized_energy)
```

### Sifat fisikokimia

```python
from rdkit import Chem
from chemflow import LipinskiCalculator

mol = Chem.MolFromSmiles("CC(=O)OC1=CC=CC=C1C(=O)O")
lipinski = LipinskiCalculator.calculate(mol)
print(lipinski.molecular_weight, lipinski.violations, lipinski.passes_ro5)
```

### Resolusi SMILES via PubChem

```python
from chemflow import PubChemResolver

resolver = PubChemResolver()
smiles = resolver.resolve("Aspirin")
```

### ADMET dari file hasil ADMETLab3

```python
from chemflow import load_admet_rows

rows = load_admet_rows("hasil_admetlab.csv", ligand_names=["Aspirin", "Ibuprofen", "Quercetin"])
```

Baris ke-N file dipetakan ke ligan ke-N secara posisional, jumlahnya harus sama. Bila lewat argumen
`ligand_smiles` ada SMILES yang kembar (senyawa yang sama di beberapa grup), file boleh memuat SMILES
unik saja: barisnya disalin ke tiap ligan kembar. `chemflow.admet.dedup` (`group_by_smiles`, `fan_out`)
menyediakan pemetaan ini untuk pemakaian sendiri.

Klasifikasi hijau/kuning/merah satu nilai:

```python
from chemflow import classify_admet_value

classify_admet_value("hERG", 0.82).flag   # Flag.RED
```

### Preparasi reseptor

```python
from pathlib import Path
from chemflow import ReceptorPreparer, fetch_pdb

fetched = fetch_pdb("3PTB", Path("output/pdb_cache"))
preparer = ReceptorPreparer(kollman_fallback="zero")
mol = preparer.load(fetched.pdb_path)

preparer.prepare_for_docking(mol, Path("output/3ptb_docking.pdbqt"))
preparer.prepare_for_merge(mol, Path("output/3ptb_clean.pdb"))
```

### Excel reseptor dari ligan native

```python
from pathlib import Path
from chemflow import ReceptorConfigRow, fetch_pdb, suggest_box_size, write_receptor_config

fetched = fetch_pdb("3PTB", Path("output/pdb_cache"))
ligand = fetched.native_ligands[0]
size = suggest_box_size(ligand)

row = ReceptorConfigRow(
    "3PTB", (ligand.center_x, ligand.center_y, ligand.center_z), (size, size, size), ligand.label,
)
write_receptor_config([row], "reseptor.xlsx")
```

Versi interaktifnya tersedia sebagai `chemflow receptor-config`
([detail](receptor-config.md)).

### Auto-download dan menjalankan AutoDock Vina

```python
from pathlib import Path
from chemflow import GridBox, VinaReleaseManager, VinaRunner

manager = VinaReleaseManager()
vina_path = manager.resolve(version="1.2.7")  # unduh otomatis jika belum ada di cache

runner = VinaRunner(vina_path)
poses = runner.run(
    receptor_pdbqt=Path("output/3ptb_docking.pdbqt"),
    ligand_pdbqt=Path("output/ligan/Quercetin.pdbqt"),
    output_pdbqt=Path("output/out.pdbqt"),
    log_file=Path("output/run.log"),
    grid_box=GridBox.from_manual(-1.76, 14.46, 16.92, 20, 20, 20),
    exhaustiveness=16,
)
```

### PCA kemometrik (2D dan 3D)

```python
from chemflow import ChemometricPCA

pca = ChemometricPCA()
result = pca.compute(
    feature_matrix=[[180, 2.1, 1, 3], [412, 4.5, 3, 6], [250, 1.2, 2, 4], [302, 1.5, 5, 7]],
    feature_names=["MW", "LogP", "HBD", "HBA"],
    labels=["Aspirin", "Curcumin", "Ibuprofen", "Quercetin"],
    groups=["Obat", "Tanaman_X", "Obat", "Tanaman_X"],
)
pca.plot_2d(result, "pca_2d.png")
pca.plot_3d(result, "pca_3d.png")  # None jika data tak cukup untuk 3 komponen (minimal 4 senyawa, 3 fitur)
```

Gaya jurnal: `groups` menentukan bentuk penanda dan elips kepercayaan 95% (kelas), dan argumen
opsional `series` menentukan warna (mis. jenis produk). `scaling` memilih `"auto"` (z-score,
bawaan), `"pareto"`, atau `"center"`:

```python
result = pca.compute(matrix, features, labels, groups=classes, series=series, scaling="pareto")
pca.plot_2d(result, "pca_2d.png", show_loadings=False, annotate=False)
```

### Analisis GC-MS

```python
from chemflow import GcmsConfig, run_gcms_analysis

result = run_gcms_analysis(GcmsConfig(data=["data-gcms/"], output_dir="hasil"))
print(result.workbook, len(result.plots))
```

Opsional dan tanpa docking; format data, pustaka, dan statistik dijelaskan di
[`docs/gcms-analysis.md`](gcms-analysis.md).

### Hierarchical Cluster Analysis (HCA)

```python
from chemflow import HierarchicalClustering

hca = HierarchicalClustering()
result = hca.compute(
    feature_matrix=[[180, 2.1], [412, 4.5], [250, 1.2]],
    labels=["Aspirin", "Quercetin", "Ibuprofen"],
    groups=["Obat", "Tanaman_X", "Obat"],
)
paths = hca.plot_dendrogram(result, "dendrogram.png", max_leaves=30)   # List[Path], dipotong bila daun > 30
assignment = hca.assign_clusters(result, n_clusters=2)  # {"Aspirin": 1, ...}
```

### Grafik ADMET dan gaya publikasi

```python
from chemflow import ChartBuilder

rows = [  # satu dict per ligan, kolom seperti CSV ADMETLab3 (hasil load_admet_rows)
    {"ligand": "Aspirin", "hia": 0.1, "caco2": -4.5, "pgp_inh": 0.2, "hERG": 0.2, "DILI": 0.5, "Ames": 0.1},
    {"ligand": "Quercetin", "hia": 0.4, "caco2": -5.0, "pgp_inh": 0.5, "hERG": 0.3, "DILI": 0.9, "Ames": 0.9},
    {"ligand": "NATIVE_N3_A1", "hia": 0.9, "caco2": -6.0, "pgp_inh": 0.8, "hERG": 0.8, "DILI": 0.1, "Ames": 0.4},
]

charts = ChartBuilder("output/analytics", dpi=300, formats=("png", "svg"), max_rows=30)
charts.radar_all_admet_categories(rows, pinned={"NATIVE_N3_A1"})   # ligan pinned ikut di setiap bagian radar
charts.admet_all_stacked_bars(rows)
```

Semua metode grafik mengembalikan `List[Path]` (bagian ke-n berakhiran `_partNNofMM`, daftar kosong
bila dilewati). Grafik per grup dengan ligan native sebagai pembanding:

```python
from chemflow import GroupChartBuilder

group_of = {"Aspirin": "AINS_A", "Quercetin": "AINS_B", "NATIVE_N3_A1": "Native"}
replicate_stats = [  # hasil compute_replicate_stats: ligan, reseptor, afinitas terbaik
    {"ligand": "Aspirin", "receptor": "3PTB_R001", "affinity_best": -5.3},
    {"ligand": "Quercetin", "receptor": "3PTB_R001", "affinity_best": -7.8},
    {"ligand": "NATIVE_N3_A1", "receptor": "3PTB_R001", "affinity_best": -9.0},
]
lipinski_rows = [
    {"ligand": "Aspirin", "MW": 180.2, "LogP": 1.2, "HBD": 1, "HBA": 3},
    {"ligand": "Quercetin", "MW": 302.2, "LogP": 1.5, "HBD": 5, "HBA": 7},
    {"ligand": "NATIVE_N3_A1", "MW": 680.8, "LogP": 3.1, "HBD": 4, "HBA": 9},
]
admet_rows = [  # baris ADMET per ligan, kolom seperti CSV ADMETLab3
    {"ligand": "Aspirin", "hia": 0.1, "caco2": -4.5, "hERG": 0.2, "DILI": 0.5},
    {"ligand": "Quercetin", "hia": 0.4, "caco2": -5.0, "hERG": 0.3, "DILI": 0.9},
    {"ligand": "NATIVE_N3_A1", "hia": 0.9, "caco2": -6.0, "hERG": 0.8, "DILI": 0.1},
]
GroupChartBuilder("output/analytics").plot_all(replicate_stats, lipinski_rows, admet_rows, group_of)
```

### Heatmap

```python
from chemflow import HeatmapBuilder

builder = HeatmapBuilder("output/analytics", max_rows=30, max_cols=20)   # lebih besar dari itu dipotong jadi ubin

builder.heatmap_affinity([
    {"receptor": "3PTB", "ligand": "Quercetin", "affinity_best": -7.8},
    {"receptor": "3PTB", "ligand": "Aspirin", "affinity_best": -5.3},
    {"receptor": "6LU7", "ligand": "Quercetin", "affinity_best": -6.9},
], native_rows=[{"receptor": "3PTB", "ligand": "NATIVE_BEN_A1", "affinity_best": -6.1}])   # kolom "Native (ref)"

builder.heatmap_properties(
    rows=[{"ligand": "Quercetin", "MW": 302.2, "LogP": 1.5}, {"ligand": "Aspirin", "MW": 180.2, "LogP": 1.2}],
    properties=["MW", "LogP"],
)
```

### Analisis similaritas interaksi

```python
from chemflow import run_similarity_report

report = run_similarity_report("hasil/")     # hitung, tulis Excel, dan buat grafik
print(len(report.results), report.workbook)
```

Langkahnya bisa dipakai terpisah:

```python
from chemflow import SimilarityAnalyzer, export_similarity_results

results = SimilarityAnalyzer().analyze_output_dir("hasil/")
export_similarity_results(results, "hasil/similaritas_interaksi.xlsx")
```

Detail konvensi file interaksi & rumus perhitungan ada di
[`docs/similarity-analysis.md`](similarity-analysis.md).

### Ekspor interaksi otomatis dari BIOVIA (Windows)

```python
from chemflow import BioviaLocator, export_interactions

for install in BioviaLocator().installations():          # tahun terbaru lebih dulu
    print(install.year, install.executable)

summary = export_interactions("hasil/", receptor="1UWH_R001")    # BIOVIA dikendalikan lewat GUI
print(len(summary.succeeded), len(summary.failed), summary.skipped)
```

Mouse dan keyboard dikunci selama ekspor (Esc tiga kali membatalkan; `lock_input=False` mematikan).
Kompleks yang hasilnya sudah lengkap dilewati.
Detail dan pemecahan masalah ada di [`docs/biovia-interactions.md`](biovia-interactions.md).

Pipeline penuh sampai similaritas, sekali jalan. `run_similarity` bawaannya `None`: jalan sendiri
bila Windows dan BIOVIA terdeteksi, dilewati bila tidak. `True` memaksa dan `False` mematikan:

```python
from chemflow import Pipeline, PipelineConfig

config = PipelineConfig(ligand_excel="ligan.xlsx", receptor_excel="reseptor.xlsx",
                        output_dir="hasil", run_similarity=True)     # biovia_exe="...exe" bila tidak terdeteksi
Pipeline(config).run()
```

Deteksi dan penguncian input tersedia langsung:

```python
from chemflow.interaction import InputLock, detect_biovia

exe = detect_biovia()            # jalur DiscoveryStudio<tahun>.exe, atau None bila otomasi tidak bisa berjalan
with InputLock() as lock:        # mouse dan keyboard dikunci di dalam blok; Esc tiga kali membatalkan
    ...
```

## Referensi API lengkap

Seluruh kelas dan fungsi publik diekspor langsung dari `chemflow`. Lihat
`chemflow/__init__.py` untuk daftar lengkap, atau `help(chemflow)` di
Python interaktif.
