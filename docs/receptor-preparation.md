# Preparasi Reseptor

Implementasi: `chemflow.chem.receptor_preparer.ReceptorPreparer`.

Dua jalur keluaran yang sengaja dipisah total: `prepare_for_docking()`
menghasilkan PDBQT rigid dengan hidrogen polar dan muatan Kollman untuk
Vina, sementara `prepare_for_merge()` menghasilkan PDB bersih tanpa
hidrogen dan muatan sama sekali, khusus untuk penggabungan kompleks.

```mermaid
flowchart TD
    Start([Mulai: file PDB dari RCSB]) --> Load[Chem.MolFromPDBFile, SanitizeMol]
    Load --> GroupAtoms[Kelompokkan atom per chain dan nomor residu]
    GroupAtoms --> Backbone[Cek is_polymer_backbone_complete: N, CA, C lengkap?]
    Backbone --> PerAtom[Iterasi tiap atom]
    PerAtom --> Water{Residu HOH/WAT dan remove_waters?}
    Water -->|Ya| DelWater[Hapus atom]
    Water -->|Tidak| Het{HETATM dan remove_hetero_ligands?}
    Het -->|Tidak| Clean
    Het -->|Ya| Metal{Elemen logam dan keep_metals?}
    Metal -->|Ya| KeepMetal[Pertahankan]
    Metal -->|Tidak| Modified{Backbone lengkap dari langkah sebelumnya?}
    Modified -->|Ya| KeepModified[Pertahankan + log residu nonstandar]
    Modified -->|Tidak| DelHet[Hapus: ligan asli/molekul lain]
    DelWater --> Clean[Mol bersih: residu standar + nonstandar backbone-lengkap]
    KeepMetal --> Clean
    KeepModified --> Clean
    DelHet --> Clean

    Clean --> BranchA[["Cabang A: prepare_for_docking"]]
    Clean --> BranchB[["Cabang B: prepare_for_merge"]]

    BranchA --> AddHFull[AddHs penuh + copy PDBResidueInfo ke H baru]
    AddHFull --> StripNonpolar[Hapus H yang tetangganya atom C, sisakan H polar]
    StripNonpolar --> Kollman[KollmanChargeAssigner: lookup resname+atomname di tabel AMBER ff99SB]
    Kollman --> Protonation{His: HD1/HE2 hadir? Cys: HG hadir?}
    Protonation --> Fallback{Atom/residu tidak ada di tabel?}
    Fallback -->|Ya| ZeroOrGasteiger[Fallback charge nol dan log, atau Gasteiger per-atom]
    Fallback -->|Tidak| AD4Type
    ZeroOrGasteiger --> AD4Type[AD4AtomTyper: H ke HD/H, C ke A/C, N ke N/NA, O ke OA, S ke S/SA]
    AD4Type --> WritePdbqt[ReceptorPDBQTWriter: ATOM/HETATM flat + kolom charge dan tipe AD4, TER per chain]
    WritePdbqt --> EndA([receptor_docking.pdbqt])

    BranchB --> StripAllH[Hapus SEMUA atom H]
    StripAllH --> ClearCharge[Clear formal charge dan prop muatan]
    ClearCharge --> WritePdb[Chem.MolToPDBFile]
    WritePdb --> EndB([receptor_clean.pdb, khusus untuk merge])
```

Residu HETATM yang secara struktural bagian dari backbone protein (asam
amino termodifikasi, misalnya MSE selenometionin) selalu dipertahankan
lewat pengecekan struktural, bukan daftar nama hardcode, sehingga
residu termodifikasi apa pun otomatis tergeneralisasi.
