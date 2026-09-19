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

exit_code = Pipeline(config).run()
```

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

Baris ke-N file dipetakan ke ligan ke-N secara posisional, jumlahnya harus sama.
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

### Hierarchical Cluster Analysis (HCA)

```python
from chemflow import HierarchicalClustering

hca = HierarchicalClustering()
result = hca.compute(
    feature_matrix=[[180, 2.1], [412, 4.5], [250, 1.2]],
    labels=["Aspirin", "Quercetin", "Ibuprofen"],
    groups=["Obat", "Tanaman_X", "Obat"],
)
hca.plot_dendrogram(result, "dendrogram.png")
assignment = hca.assign_clusters(result, n_clusters=2)  # {"Aspirin": 1, ...}
```

### Grafik ADMET dan gaya publikasi

```python
from chemflow import ChartBuilder

charts = ChartBuilder("output/analytics", dpi=300, formats=("png", "svg"))
charts.radar_all_admet_categories(rows)
charts.admet_all_stacked_bars(rows)
```

### Heatmap

```python
from chemflow import HeatmapBuilder

builder = HeatmapBuilder("output/analytics")

builder.heatmap_affinity([
    {"receptor": "3PTB", "ligand": "Quercetin", "affinity_best": -7.8},
    {"receptor": "3PTB", "ligand": "Aspirin", "affinity_best": -5.3},
    {"receptor": "6LU7", "ligand": "Quercetin", "affinity_best": -6.9},
])

builder.heatmap_properties(
    rows=[{"ligand": "Quercetin", "MW": 302.2, "LogP": 1.5}, {"ligand": "Aspirin", "MW": 180.2, "LogP": 1.2}],
    properties=["MW", "LogP"],
)
```

### Analisis similaritas interaksi

```python
from chemflow import SimilarityAnalyzer, export_similarity_results

results = SimilarityAnalyzer().analyze_output_dir("hasil/")
export_similarity_results(results, "hasil/similaritas_interaksi.xlsx")
```

Detail konvensi file interaksi & rumus perhitungan ada di
[`docs/similarity-analysis.md`](similarity-analysis.md).

## Referensi API lengkap

Seluruh kelas dan fungsi publik diekspor langsung dari `chemflow`. Lihat
`chemflow/__init__.py` untuk daftar lengkap, atau `help(chemflow)` di
Python interaktif.
