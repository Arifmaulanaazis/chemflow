# Preparasi Ligan

Implementasi: `chemflow.chem.ligand_preparer.LigandPreparer`.

Gambar 2D diambil dari mol 2D asli hasil parsing SMILES, sebelum
minimisasi, bukan dari konformasi 3D yang sudah dioptimasi.

```mermaid
flowchart TD
    Start([Mulai: nama senyawa dan SMILES]) --> Parse[Chem.MolFromSmiles]
    Parse --> Valid{SMILES valid?}
    Valid -->|Tidak| Fail[["raise ValueError, ligan ditandai GAGAL, lanjut ligan lain"]]
    Valid -->|Ya| Image{generate_2d_image?}
    Image -->|Ya| Draw[Compute2DCoords + MolDraw2DCairo, fallback PIL, simpan PNG]
    Image -->|Tidak| Strip
    Draw --> Strip[Strip garam: LargestFragmentChooser]
    Strip --> Neutral[Netralkan muatan: Uncharger]
    Neutral --> AddH[Chem.AddHs, hidrogenasi penuh]
    AddH --> Embed[Embed 3D: ETKDGv3 lalu ETKDGv2 lalu randomSeed]
    Embed --> EmbedOk{Salah satu metode berhasil?}
    EmbedOk -->|Tidak| FailEmbed[["raise ValueError: gagal embed 3D"]]
    EmbedOk -->|Ya| ForceField{force_field == MMFF94?}
    ForceField -->|Ya| Mmff[MMFFGetMoleculeForceField, Minimize]
    ForceField -->|Tidak, UFF langsung| Uff[UFFGetMoleculeForceField, Minimize]
    Mmff --> MmffOk{Parameter MMFF94 tersedia untuk semua elemen?}
    MmffOk -->|Ya| Gasteiger
    MmffOk -->|Tidak| Uff
    Uff --> Gasteiger[ComputeGasteigerCharges]
    Gasteiger --> WritePdb[Tulis PDB: mol_to_pdb]
    WritePdb --> Obabel[["OpenBabel: obabel -i pdb ... -o pdbqt -O out -h"]]
    Obabel --> ObabelOk{Output PDBQT kosong atau exit != 0?}
    ObabelOk -->|Ya| FailObabel[["raise ValueError, dump stdout/stderr ke log"]]
    ObabelOk -->|Tidak| End([Selesai: LigandPrepResult])
```

Catatan penting:

- Nama file gambar 2D, PDB, dan PDBQT diturunkan dari nama senyawa lewat
  `chemflow.utils.name_sanitizer.sanitize_filename`, sehingga aman di Windows:
  karakter terlarang, nama perangkat (`CON`, `NUL`, `COM1`, dst.), aksara
  non-Latin, dan tabrakan nama (termasuk beda huruf besar dan kecil)
  ditangani. `unique_safe_names` menjamin nama unik lintas seluruh ligan, dan
  `LigandRecord.safe_name` membawanya ke semua tahap. Panjang nama menyesuaikan
  panjang folder output agar path tetap di bawah 260 karakter di Windows.
- `-h` pada OpenBabel memicu penghitungan ulang muatan Gasteiger dan
  pembangunan pohon torsi (ROOT/BRANCH/ENDBRANCH/TORSDOF) secara internal
  saat menulis PDBQT ligan.
- OpenBabel bisa keluar dengan exit code 0 walau gagal diam-diam, sehingga
  ukuran file output ikut divalidasi, bukan hanya exit code.
- Setiap tahap mencatat kegagalan sebagai warning dan, kecuali tahap yang
  benar-benar fatal (parsing SMILES gagal), tidak menghentikan pipeline
  untuk ligan lain.
