"""
Antarmuka baris perintah (CLI) chemflow.

Subperintah:
    chemflow init                 Buat template Excel input & cek kesiapan mesin.
    chemflow receptor-config      Susun Excel reseptor secara interaktif (kode PDB + pilih ligan native).
    chemflow run --ligands ... --receptors ...   Jalankan pipeline penuh.
    chemflow resume --output hasil/   Lanjutkan run yang terhenti dari checkpoint terakhir.
    chemflow list-vina-versions   Tampilkan versi AutoDock Vina yang kompatibel.
    chemflow interactions --output hasil/   Ekspor interaksi kompleks lewat BIOVIA (diagram 2D dan tabel Non-bond).
    chemflow similarity --output hasil/   Analisis similaritas interaksi vs ligan native.
    chemflow gcms --data data-gcms/ --output hasil/   Analisis GC-MS opsional (tanpa docking).

Contoh pemakaian:

    python -m chemflow init --output contoh/

    python -m chemflow receptor-config

    python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx \\
        --output hasil/ --exhaustiveness 16 --n-replicates 3 \\
        --run-rmsd-validation

    python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --output hasil/ --gcms data-gcms/

    python -m chemflow resume --output hasil/

    python -m chemflow list-vina-versions

    python -m chemflow interactions --output hasil/

    python -m chemflow gcms --data data-gcms/ --output hasil/

    python -m chemflow similarity --output hasil/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chemflow.banner import print_banner
from chemflow.config import PipelineConfig
from chemflow.docking.vina_manager import VinaReleaseManager
from chemflow.pipeline import Pipeline


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chemflow",
        description="Pipeline CLI: preparasi ligan/reseptor, ADMET, docking AutoDock Vina, merge, & PCA kemometrik.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    _add_init_subparser(sub)
    sub.add_parser(
        "receptor-config",
        help="Susun Excel reseptor secara interaktif: masukkan kode PDB, pilih ligan native, koordinat dan ukuran "
             "kotak terisi otomatis. Hanya mode interaktif dan tidak menerima opsi lain.",
    )
    _add_run_subparser(sub)
    _add_resume_subparser(sub)
    sub.add_parser("list-vina-versions", help="Tampilkan versi AutoDock Vina yang kompatibel dengan mesin ini.")
    _add_interactions_subparser(sub)
    _add_similarity_subparser(sub)
    _add_gcms_subparser(sub)

    return p


def _add_init_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "init",
        help="Buat template Excel input & cek kesiapan mesin (paket Python, OpenBabel, AutoDock Vina, jaringan).",
    )
    p.add_argument("--output", type=Path, default=Path("chemflow_templates"),
                   help="Direktori tujuan template Excel (default: ./chemflow_templates).")
    p.add_argument("--format", choices=["tidy", "wide", "both"], default="both",
                   help="Format template ligan yang dibuat (default: both).")
    p.add_argument("--skip-check", action="store_true",
                   help="Jangan jalankan pemeriksaan kesiapan mesin, cukup buat template.")


def _add_run_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("run", help="Jalankan pipeline penuh: preparasi, ADMET, docking, merge, analitik.")

    g_input = p.add_argument_group("Input")
    g_input.add_argument("--ligands", type=Path, required=True, help="Excel data ligan (nama senyawa [+ SMILES opsional]).")
    g_input.add_argument("--receptors", type=Path, required=True, help="Excel data reseptor (kode PDB [+ gridbox opsional]).")
    g_input.add_argument("--output", type=Path, default=Path("chemflow_output"), help="Direktori output.")

    g_cols = p.add_argument_group("Pemetaan kolom Excel (opsional, default auto-detect)")
    g_cols.add_argument("--ligand-name-col", type=str, default=None)
    g_cols.add_argument("--ligand-smiles-col", type=str, default=None)
    g_cols.add_argument("--ligand-group-col", type=str, default=None)
    g_cols.add_argument("--receptor-pdb-col", type=str, default=None)

    g_grid = p.add_argument_group("Gridbox")
    g_grid.add_argument("--default-box-size", type=float, default=20.0,
                         help="Ukuran kotak cadangan (Angstrom) bila tak ada ligan native untuk menurunkannya "
                              "(default: 20). Bila ada native, ukuran default = ekstensi native + --box-padding.")
    g_grid.add_argument("--box-padding", type=float, default=8.0,
                         help="Padding (Angstrom) di atas ekstensi ligan native untuk ukuran kotak default (default: 8).")
    g_grid.add_argument("--no-interactive-gridbox", action="store_true",
                         help="Larang prompt interaktif, wajib gridbox eksplisit di Excel reseptor.")

    g_prep = p.add_argument_group("Preparasi ligan")
    g_prep.add_argument("--force-field", choices=["MMFF94", "UFF"], default="MMFF94")
    g_prep.add_argument("--minimize-max-iters", type=int, default=1000)
    g_prep.add_argument("--no-2d-image", action="store_true", help="Lewati pembuatan gambar 2D.")

    g_rec = p.add_argument_group("Preparasi reseptor")
    g_rec.add_argument("--keep-waters", action="store_true", help="Jangan hapus molekul air.")
    g_rec.add_argument("--keep-hetero-ligands", action="store_true", help="Jangan hapus ligan HETATM asli.")
    g_rec.add_argument("--no-keep-metals", action="store_true", help="Ikut hapus ion logam.")
    g_rec.add_argument("--kollman-fallback", choices=["zero", "gasteiger"], default="zero",
                        help="Strategi fallback muatan Kollman untuk atom di luar tabel kurasi.")

    g_dock = p.add_argument_group("Docking (AutoDock Vina)")
    g_dock.add_argument("--vina-version", type=str, default=None, help="Versi Vina spesifik (default: terbaru kompatibel).")
    g_dock.add_argument("--vina-executable", type=Path, default=None, help="Path executable Vina manual (skip auto-download).")
    g_dock.add_argument("--exhaustiveness", type=int, default=8)
    g_dock.add_argument("--num-modes", type=int, default=9)
    g_dock.add_argument("--energy-range", type=float, default=3.0)
    g_dock.add_argument("--seed", type=int, default=None)
    g_dock.add_argument("--n-replicates", type=int, default=1)

    g_merge = p.add_argument_group("Merge kompleks reseptor-ligan")
    g_merge.add_argument("--merge-mode", choices=["best", "all"], default="best",
                          help="'best' = 1 pose terbaik lintas replikat per ligan-reseptor (default), "
                               "'all' = semua pose semua replikat sukses digabung sebagai file terpisah.")

    g_native = p.add_argument_group("Ligan native (referensi)")
    g_native.add_argument("--no-native", action="store_true",
                          help="Jangan sertakan ligan native kokristal (redocking, Lipinski, ADMET, dan grup "
                               "'Native' pada semua analitik).")

    g_rmsd = p.add_argument_group("Validasi RMSD redocking")
    g_rmsd.add_argument("--run-rmsd-validation", action="store_true")
    g_rmsd.add_argument("--rmsd-threshold-good", type=float, default=2.0)
    g_rmsd.add_argument("--rmsd-threshold-acceptable", type=float, default=3.0)

    g_sim = p.add_argument_group("Interaksi dan similaritas (BIOVIA)")
    g_sim.add_argument("--similarity", action=argparse.BooleanOptionalAction, default=None,
                       help="Ekspor interaksi tiap kompleks lewat GUI BIOVIA Discovery Studio (diagram 2D dan tabel "
                            "Non-bond) lalu hitung similaritas terhadap ligan native. Bawaan: otomatis bila Windows dan "
                            "BIOVIA terdeteksi; --similarity memaksa, --no-similarity mematikan. Mouse dan keyboard "
                            "dikunci selama ekspor (Esc tiga kali untuk membatalkan).")
    g_sim.add_argument("--biovia-exe", type=Path, default=None,
                       help="Path DiscoveryStudio<tahun>.exe (default: deteksi otomatis, tahun terbaru).")
    g_sim.add_argument("--biovia-timeout", type=float, default=90.0,
                       help="Batas menunggu jendela BIOVIA muncul, dalam detik (default: 90).")
    g_sim.add_argument("--no-lock-input", action="store_true",
                       help="Jangan kunci mouse dan keyboard selama ekspor BIOVIA.")

    g_ob = p.add_argument_group("OpenBabel")
    g_ob.add_argument("--openbabel-path", type=Path, default=None, help="Path manual ke obabel (default: cari di PATH).")

    g_admet = p.add_argument_group("ADMET")
    g_admet.add_argument("--no-admet", action="store_true", help="Lewati prediksi ADMET (ADMETLab3).")
    g_admet.add_argument("--admet-file", type=Path, default=None,
                          help="File hasil ADMETLab3 (.csv/.xlsx) sebagai pengganti scraping. Baris file harus "
                               "berurutan sama dengan ligan input (tidy: atas ke bawah; wide: kolom kiri ke kanan, "
                               "tiap kolom atas ke bawah).")
    g_admet.add_argument("--admet-batch-size", type=int, default=50)
    g_admet.add_argument("--admet-ssl-verify", action="store_true", help="Aktifkan verifikasi SSL saat scraping ADMETLab3.")

    g_pubchem = p.add_argument_group("PubChem")
    g_pubchem.add_argument("--no-pubchem-fetch", action="store_true", help="Jangan resolve SMILES kosong via PubChem.")
    g_pubchem.add_argument("--no-pubchem-interactive-fallback", action="store_true",
                            help="Jangan tanya SMILES manual saat PubChem gagal, langsung lewati senyawa itu.")

    g_analytics = p.add_argument_group("Analitik")
    g_analytics.add_argument("--no-charts", action="store_true", help="Lewati bar/radar chart.")
    g_analytics.add_argument("--no-pca", action="store_true", help="Lewati PCA kemometrik (2D & 3D).")
    g_analytics.add_argument("--no-hca", action="store_true", help="Lewati HCA (dendrogram).")
    g_analytics.add_argument("--no-heatmap", action="store_true", help="Lewati heatmap afinitas & properti.")
    g_analytics.add_argument("--dpi", type=int, default=300, help="Resolusi grafik (default: 300).")
    g_analytics.add_argument("--figure-formats", nargs="+", default=["png"], choices=["png", "svg", "pdf"],
                              help="Format grafik (PNG selalu ditulis; tambahkan svg/pdf untuk naskah jurnal).")
    g_analytics.add_argument("--plot-max-rows", type=int, default=30,
                              help="Maks. ligan/baris per gambar; grafik yang lebih besar dipotong otomatis "
                                   "menjadi beberapa bagian (default: 30, 0 = tidak dipotong). Radar per-ligan "
                                   "selalu dibagi per 8 garis (maks. 5 bagian).")
    g_analytics.add_argument("--plot-max-cols", type=int, default=20,
                              help="Maks. kolom per gambar heatmap (default: 20, 0 = tidak dipotong).")

    g_gcms = p.add_argument_group("Analisis GC-MS (opsional, tidak memengaruhi docking)")
    g_gcms.add_argument("--gcms", nargs="+", type=Path, default=None, metavar="PATH",
                        help="Berkas, folder, atau pola data GC-MS (xls, xlsx, csv, tsv, txt, cdf, mzML, mzXML). "
                             "Bila diisi, analisis GC-MS berjalan setelah analitik dan hasilnya ditulis di <output>/gcms/. "
                             "Opsi lanjutan dan rerun tanpa docking: 'chemflow gcms'.")
    g_gcms.add_argument("--gcms-groups", type=Path, default=None,
                        help="Tabel sampel, seri, dan kelas (CSV/Excel). Bawaan: seri dari nama berkas, kelas dari folder.")
    g_gcms.add_argument("--gcms-library", type=Path, default=None,
                        help="Pustaka senyawa untuk memberi nama puncak (kolom name, rt atau ri, cas, smiles).")

    g_log = p.add_argument_group("Logging")
    g_log.add_argument("--verbose", action="store_true")
    g_log.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    g_log.add_argument("--no-progress", action="store_true", help="Matikan progress bar (tetap ada log biasa).")


def _add_resume_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "resume",
        help="Lanjutkan run yang terhenti (terminal ditutup, Ctrl+C, komputer mati) dari checkpoint terakhir. "
             "Semua pengaturan diambil dari run asli; pada run yang sudah selesai, laporan dan grafik dibuat ulang.",
    )
    p.add_argument("--output", type=Path, required=True,
                   help="Folder output run yang mau dilanjutkan (berisi _state/).")
    p.add_argument("--no-progress", action="store_true", help="Matikan progress bar.")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--log-level", default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                   help="Ganti level log (default: sama dengan run asli).")
    p.add_argument("--openbabel-path", type=Path, default=None,
                   help="Ganti path obabel (bila lokasinya berubah sejak run asli).")
    p.add_argument("--vina-executable", type=Path, default=None,
                   help="Ganti path executable Vina (bila lokasinya berubah sejak run asli).")
    p.add_argument("--biovia-exe", type=Path, default=None,
                   help="Ganti path DiscoveryStudio<tahun>.exe (bila lokasinya berubah sejak run asli).")


def _add_interactions_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "interactions",
        help="Ekspor interaksi ligan-reseptor tiap kompleks lewat GUI BIOVIA Discovery Studio: diagram 2D (PNG) dan "
             "tabel Non-bond (Excel) di <output>/interaksi/. Kompleks yang sudah lengkap dilewati. Hanya Windows; "
             "jangan pakai mouse/keyboard selama ekspor. Hasilnya dipakai 'chemflow similarity'.",
    )
    p.add_argument("--output", type=Path, required=True,
                   help="Folder output 'chemflow run' yang berisi complexes/.")
    p.add_argument("--interactions-dir", type=Path, default=None,
                   help="Folder hasil ekspor (default: <output>/interaksi).")
    p.add_argument("--interaction-suffix", type=str, default="_interaksi.xlsx",
                   help="Akhiran nama file Excel per kompleks (default: _interaksi.xlsx); "
                        "samakan dengan 'chemflow similarity'.")
    p.add_argument("--receptor", type=str, default=None,
                   help="Hanya reseptor ini (nama folder di complexes/, mis. 1UWH_R001).")
    p.add_argument("--force", action="store_true", help="Ekspor ulang walau hasilnya sudah lengkap.")
    p.add_argument("--biovia-exe", type=Path, default=None,
                   help="Path DiscoveryStudio<tahun>.exe (default: deteksi otomatis, tahun terbaru).")
    p.add_argument("--biovia-timeout", type=float, default=90.0,
                   help="Batas menunggu jendela BIOVIA muncul, dalam detik (default: 90).")
    p.add_argument("--no-lock-input", action="store_true",
                   help="Jangan kunci mouse dan keyboard selama ekspor (bawaan: dikunci, Esc tiga kali membatalkan).")
    p.add_argument("--no-progress", action="store_true", help="Matikan progress bar.")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])


def _add_similarity_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "similarity",
        help="Analisis similaritas interaksi ligan-reseptor vs ligan native (Pratama et al. 2021), "
             "bisa di-rerun kapan saja pada folder output run yang sudah ada.",
    )
    p.add_argument("--output", type=Path, required=True,
                    help="Folder output 'chemflow run' yang berisi complexes/ (butuh kompleks referensi native, "
                         "dibuat otomatis oleh run yang mendeteksi ligan native; tidak ada bila --no-native).")
    p.add_argument("--interactions-dir", type=Path, default=None,
                    help="Folder file interaksi BIOVIA manual, struktur membayangkan complexes/ "
                         "(default: <output>/interaksi).")
    p.add_argument("--interaction-suffix", type=str, default="_interaksi.xlsx",
                    help="Akhiran nama file interaksi per kompleks (default: _interaksi.xlsx).")
    p.add_argument("--result-filename", type=str, default="similaritas_interaksi.xlsx",
                    help="Nama file Excel hasil, ditulis di dalam --output (default: similaritas_interaksi.xlsx).")
    p.add_argument("--no-plots", action="store_true", help="Lewati pembuatan grafik similaritas.")
    p.add_argument("--dpi", type=int, default=300, help="Resolusi grafik (default: 300).")
    p.add_argument("--figure-formats", nargs="+", default=["png"], choices=["png", "svg", "pdf"],
                    help="Format grafik (PNG selalu ditulis).")
    p.add_argument("--plot-max-rows", type=int, default=30,
                    help="Maks. ligan per gambar; lebih dari itu dipotong menjadi beberapa bagian (0 = tidak dipotong).")
    p.add_argument("--plot-max-cols", type=int, default=20,
                    help="Maks. kolom (residu) per gambar heatmap jejak kontak (0 = tidak dipotong).")


def _add_gcms_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "gcms",
        help="Analisis data GC-MS opsional tanpa docking: kromatogram, puncak, PCA, HCA, PLS-DA, LDA, uji univariat, "
             "kemiripan, dan skrining alergen. Berjalan mandiri dan bisa diulang pada folder output yang sama.",
    )
    p.add_argument("--output", type=Path, required=True,
                   help="Folder output; hasil ditulis di <output>/gcms/. Boleh folder run yang sudah ada atau folder baru.")
    p.add_argument("--data", nargs="+", type=Path, default=None, metavar="PATH",
                   help="Berkas, folder (rekursif), atau pola data GC-MS. Bila dihilangkan, dipakai data dari analisis GC-MS "
                        "sebelumnya pada --output (atau dari 'chemflow run --gcms').")
    g_meta = p.add_argument_group("Sampel dan pustaka")
    g_meta.add_argument("--groups", type=Path, default=None,
                        help="Tabel sampel, seri, dan kelas (CSV/Excel; kolom sample, series, class). Bawaan: seri dari nama "
                             "berkas tanpa nomor ulangan, kelas dari subfolder atau kata asli/tiruan pada nama.")
    g_meta.add_argument("--library", type=Path, default=None,
                        help="Pustaka senyawa (CSV/Excel; kolom name, rt atau ri, cas, smiles) untuk memberi nama puncak.")
    g_meta.add_argument("--alkanes", type=Path, default=None,
                        help="Deret alkana (kolom carbon, rt) untuk menghitung indeks retensi Kovats.")
    g_meta.add_argument("--label-by", choices=["auto", "class", "series"], default=None,
                        help="Kelompok untuk statistik terawasi dan univariat (default: auto, kelas bila minimal dua).")
    g_proc = p.add_argument_group("Pemrosesan sinyal")
    g_proc.add_argument("--rt-unit", choices=["auto", "min", "sec", "msec", "min_x1000"], default=None,
                        help="Satuan waktu retensi masukan (default: auto, dideteksi dari selang antar titik).")
    g_proc.add_argument("--rt-range", nargs=2, type=float, default=None, metavar=("MULAI", "AKHIR"),
                        help="Batasi analisis ke rentang RT ini, dalam menit (membuang pelarut awal atau ekor).")
    g_proc.add_argument("--no-baseline", action="store_true", help="Lewati koreksi baseline.")
    g_proc.add_argument("--smooth-window", type=float, default=None,
                        help="Jendela Savitzky-Golay, menit (default: 0.02, 0 = mati).")
    g_proc.add_argument("--no-align", action="store_true", help="Lewati penyelarasan waktu retensi antar sampel.")
    g_proc.add_argument("--max-shift", type=float, default=None,
                        help="Pergeseran RT maksimum saat penyelarasan, menit (default: 0.3).")
    g_proc.add_argument("--min-snr", type=float, default=None,
                        help="Rasio sinyal terhadap derau minimum sebuah puncak (default: 5).")
    g_proc.add_argument("--min-prominence", type=float, default=None,
                        help="Prominence minimum puncak sebagai pecahan puncak terbesar (default: 0.005).")
    g_proc.add_argument("--peak-tolerance", type=float, default=None,
                        help="Toleransi RT untuk menyamakan puncak antar sampel, menit (default: 0.05).")
    g_proc.add_argument("--min-presence", type=float, default=None,
                        help="Pecahan sampel minimum yang harus memiliki sebuah puncak agar dipakai (0 sampai 1, default: 0).")
    g_proc.add_argument("--feature-mode", choices=["peaks", "bins"], default=None,
                        help="Fitur untuk statistik: puncak selaras (default) atau sidik jari per bin waktu.")
    g_proc.add_argument("--bin-width", type=float, default=None,
                        help="Lebar bin waktu untuk sidik jari dan kemiripan, menit (default: 0.05).")
    g_stats = p.add_argument_group("Statistik")
    g_stats.add_argument("--normalization", choices=["total", "max", "pqn", "none"], default=None,
                         help="Normalisasi per sampel (default: total).")
    g_stats.add_argument("--transform", choices=["none", "log", "sqrt"], default=None,
                         help="Transformasi nilai (default: none).")
    g_stats.add_argument("--scaling", choices=["auto", "pareto", "center"], default=None,
                         help="Penskalaan kolom untuk PCA dan model terawasi (default: pareto).")
    g_stats.add_argument("--permutations", type=int, default=None,
                         help="Jumlah permutasi uji model terawasi (default: 200, 0 = mati).")
    g_stats.add_argument("--rt-tolerance", type=float, default=None,
                         help="Toleransi RT pencocokan pustaka, menit (default: 0.05).")
    g_stats.add_argument("--ri-tolerance", type=float, default=None, help="Toleransi RI pencocokan pustaka (default: 10).")
    g_stats.add_argument("--top-features", type=int, default=None, help="Jumlah fitur pada peta panas (default: 30).")
    g_stats.add_argument("--seed", type=int, default=None, help="Benih acak validasi silang dan permutasi (default: 0).")
    g_out = p.add_argument_group("Keluaran")
    g_out.add_argument("--no-plots", action="store_true", help="Lewati pembuatan grafik.")
    g_out.add_argument("--dpi", type=int, default=None, help="Resolusi grafik (default: 300).")
    g_out.add_argument("--figure-formats", nargs="+", default=None, choices=["png", "svg", "pdf"],
                       help="Format grafik (PNG selalu ditulis).")
    g_out.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])


def _run_init(args: argparse.Namespace) -> int:
    from chemflow.templates import write_ligand_tidy_template, write_ligand_wide_template, write_receptor_template

    output_dir: Path = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    if args.format in ("tidy", "both"):
        written.append(write_ligand_tidy_template(output_dir / "ligan_contoh_tidy.xlsx"))
    if args.format in ("wide", "both"):
        written.append(write_ligand_wide_template(output_dir / "ligan_contoh_wide.xlsx"))
    written.append(write_receptor_template(output_dir / "reseptor_contoh.xlsx"))

    print(f"Template Excel dibuat di: {output_dir}")
    for path in written:
        print(f"  - {path.name}")

    if not args.skip_check:
        from chemflow.system_check import format_report, run_all_checks
        print("\nMemeriksa kesiapan mesin (paket Python, OpenBabel, AutoDock Vina, jaringan) ...")
        results = run_all_checks()
        print(format_report(results))

    print(f"Isi/sesuaikan file di {output_dir}, lalu jalankan:")
    print(f'  python -m chemflow run --ligands "{output_dir / "ligan_contoh_tidy.xlsx"}" '
          f'--receptors "{output_dir / "reseptor_contoh.xlsx"}"')
    print("Belum tahu koordinat gridbox? Susun Excel reseptor dengan: python -m chemflow receptor-config")
    return 0


def _run_receptor_config() -> int:
    from chemflow.io.receptor_config import run_receptor_config

    if not sys.stdin.isatty():
        print("receptor-config hanya berjalan di terminal interaktif.")
        return 1
    try:
        return run_receptor_config()
    except (KeyboardInterrupt, EOFError):
        print("\nDibatalkan, tidak ada file yang ditulis.")
        return 1


def _run_list_vina_versions() -> int:
    manager = VinaReleaseManager()
    print("Mengambil daftar rilis AutoDock Vina dari GitHub ...")
    try:
        compatible = manager.list_compatible()
    except RuntimeError as exc:
        print(f"  Gagal menghubungi GitHub Releases: {exc}")
        return 1
    if not compatible:
        print("  Tidak ada versi Vina yang kompatibel dengan mesin ini ditemukan di GitHub Releases.")
        return 0
    print("  Versi kompatibel dengan mesin ini (otomatis diunduh saat dipilih):")
    for asset in compatible:
        print(f"    - {asset.version}  ({asset.filename})")
    return 0


def _run_pipeline(args: argparse.Namespace) -> int:
    config = PipelineConfig(
        ligand_excel=args.ligands, receptor_excel=args.receptors, output_dir=args.output,
        ligand_name_col=args.ligand_name_col, ligand_smiles_col=args.ligand_smiles_col,
        ligand_group_col=args.ligand_group_col, receptor_pdb_col=args.receptor_pdb_col,
        default_box_size=args.default_box_size, box_padding=args.box_padding,
        interactive_gridbox=not args.no_interactive_gridbox,
        force_field=args.force_field, minimize_max_iters=args.minimize_max_iters,
        generate_2d_image=not args.no_2d_image,
        remove_waters=not args.keep_waters, remove_hetero_ligands=not args.keep_hetero_ligands,
        keep_metals=not args.no_keep_metals, kollman_fallback_zero=(args.kollman_fallback == "zero"),
        vina_version=args.vina_version, vina_executable=args.vina_executable,
        exhaustiveness=args.exhaustiveness, num_modes=args.num_modes, energy_range=args.energy_range,
        seed=args.seed, n_replicates=args.n_replicates,
        merge_mode=args.merge_mode, include_native=not args.no_native,
        run_similarity=args.similarity, biovia_exe=args.biovia_exe, biovia_launch_timeout=args.biovia_timeout,
        lock_input=not args.no_lock_input,
        run_rmsd_validation=args.run_rmsd_validation, rmsd_threshold_good=args.rmsd_threshold_good,
        rmsd_threshold_acceptable=args.rmsd_threshold_acceptable,
        openbabel_path=args.openbabel_path,
        run_admet=not args.no_admet, admet_file=args.admet_file,
        admet_batch_size=args.admet_batch_size, admet_ssl_verify=args.admet_ssl_verify,
        fetch_missing_smiles=not args.no_pubchem_fetch,
        interactive_pubchem_fallback=not args.no_pubchem_interactive_fallback,
        generate_charts=not args.no_charts, run_pca=not args.no_pca,
        run_hca=not args.no_hca, run_heatmap=not args.no_heatmap,
        figure_dpi=args.dpi, figure_formats=tuple(args.figure_formats),
        plot_max_rows=args.plot_max_rows, plot_max_cols=args.plot_max_cols,
        gcms_data=tuple(args.gcms or ()), gcms_groups=args.gcms_groups, gcms_library=args.gcms_library,
        verbose=args.verbose, log_level=args.log_level, show_progress=not args.no_progress,
    )
    return Pipeline(config).run()


def _run_resume(args: argparse.Namespace) -> int:
    from chemflow.state import RunState

    state = RunState(args.output)
    try:
        config = state.load_config()
    except (FileNotFoundError, ValueError) as exc:
        print(f"  Gagal: {exc}")
        return 1

    if args.log_level is not None:
        config.log_level = args.log_level
    if args.verbose:
        config.verbose = True
    if args.no_progress:
        config.show_progress = False
    if args.openbabel_path is not None:
        config.openbabel_path = Path(args.openbabel_path).resolve()
    if args.vina_executable is not None:
        config.vina_executable = Path(args.vina_executable).resolve()
    if args.biovia_exe is not None:
        config.biovia_exe = Path(args.biovia_exe).resolve()

    progress = state.read_progress()
    if progress.get("finished"):
        print("  Run ini sudah selesai. Semua tahap dipakai ulang dari checkpoint, laporan dan grafik dibuat ulang.")
    else:
        print(f"  Melanjutkan run yang terhenti pada tahap '{progress.get('stage', 'awal')}'.")
    return Pipeline(config, resume=True).run()


def _run_interactions(args: argparse.Namespace) -> int:
    import logging

    from chemflow.interaction import BioviaUnavailableError, export_interactions
    from chemflow.interaction.biovia_gui import BioviaError

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(message)s")
    print(f"Mengekspor interaksi BIOVIA dari: {args.output}")
    try:
        summary = export_interactions(
            args.output, args.interactions_dir, executable=args.biovia_exe, launch_timeout=args.biovia_timeout,
            xlsx_suffix=args.interaction_suffix, receptor=args.receptor, force=args.force,
            show_progress=not args.no_progress, lock_input=False if args.no_lock_input else None,
        )
    except KeyboardInterrupt:
        print("  Dihentikan pengguna. Jalankan perintah yang sama untuk melanjutkan; kompleks yang selesai dilewati.")
        return 130
    except (BioviaUnavailableError, BioviaError, FileNotFoundError) as exc:
        print(f"  Gagal: {exc}")
        return 1

    print(f"  {len(summary.succeeded)} kompleks berhasil, {len(summary.failed)} gagal, "
          f"{summary.skipped} dilewati (sudah lengkap).")
    for job, message in summary.failed:
        print(f"    - {job.receptor_key}/{job.stem}: {message}")
    return 1 if summary.failed else 0


def _run_similarity(args: argparse.Namespace) -> int:
    from chemflow.similarity.report import run_similarity_report

    print(f"Menganalisis similaritas interaksi di: {args.output}")
    try:
        report = run_similarity_report(
            args.output, interactions_dir=args.interactions_dir, interaction_suffix=args.interaction_suffix,
            result_filename=args.result_filename, make_plots=not args.no_plots, dpi=args.dpi,
            formats=args.figure_formats, max_rows=args.plot_max_rows, max_cols=args.plot_max_cols,
        )
    except FileNotFoundError as exc:
        print(f"  Gagal: {exc}")
        return 1

    if not report.results:
        print("  Tidak ada hasil similaritas yang bisa dihitung (lihat warning di atas untuk penyebabnya).")
        return 0

    print(f"  {len(report.results)} pasangan ligan-reseptor berhasil dianalisis.")
    print(f"  Hasil tersimpan di: {report.workbook}")
    for path in report.plots:
        print(f"  Grafik: {path}")
    return 0


def _gcms_overrides(args: argparse.Namespace) -> dict:
    """Opsi ``gcms`` yang diberikan eksplisit di baris perintah (sisanya dari konfigurasi tersimpan atau bawaan)."""
    values = {
        "groups_file": args.groups, "library": args.library, "alkanes": args.alkanes, "label_by": args.label_by,
        "rt_unit": args.rt_unit, "rt_range": tuple(args.rt_range) if args.rt_range else None,
        "baseline": False if args.no_baseline else None, "smooth_window": args.smooth_window,
        "align": False if args.no_align else None, "max_shift": args.max_shift, "min_snr": args.min_snr,
        "min_prominence": args.min_prominence, "peak_tolerance": args.peak_tolerance, "min_presence": args.min_presence,
        "feature_mode": args.feature_mode, "bin_width": args.bin_width,
        "normalization": args.normalization, "transform": args.transform, "scaling": args.scaling,
        "n_permutations": args.permutations, "rt_tolerance": args.rt_tolerance, "ri_tolerance": args.ri_tolerance,
        "top_features": args.top_features, "seed": args.seed, "make_plots": False if args.no_plots else None,
        "dpi": args.dpi, "figure_formats": tuple(args.figure_formats) if args.figure_formats else None,
    }
    return {key: value for key, value in values.items() if value is not None}


def _run_gcms(args: argparse.Namespace) -> int:
    import logging

    from chemflow.gcms import GcmsConfig, GcmsFormatError, load_saved_config, run_gcms_analysis

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(message)s")
    settings: dict = {}
    saved = load_saved_config(args.output)
    if saved is not None:
        settings = saved.to_dict()
    settings.update(_gcms_overrides(args))
    settings["output_dir"] = args.output
    if args.data:
        settings["data"] = tuple(args.data)
    elif not settings.get("data"):
        try:
            from chemflow.state import RunState
            settings["data"] = RunState(args.output).load_config().gcms_data
        except (FileNotFoundError, ValueError):
            settings["data"] = ()
    if not settings.get("data"):
        print("  Gagal: tidak ada data GC-MS. Berikan --data, atau jalankan pada folder yang pernah dianalisis "
              "('chemflow gcms --data ...' atau 'chemflow run --gcms ...').")
        return 1

    print(f"Menganalisis data GC-MS ke: {args.output / 'gcms'}")
    try:
        result = run_gcms_analysis(GcmsConfig.from_dict(settings))
    except (FileNotFoundError, GcmsFormatError, ValueError) as exc:
        print(f"  Gagal: {exc}")
        return 1

    print(f"  {len(result.samples)} sampel, {len(result.features)} fitur selaras.")
    print(f"  Hasil tersimpan di: {result.workbook}")
    if result.ligands_file:
        print(f"  Daftar senyawa untuk docking: {result.ligands_file}")
    if result.plots:
        print(f"  {len(result.plots)} grafik di: {result.plots[0].parent}")
    for note in result.notes:
        print(f"  Catatan: {note}")
    return 0


def main(argv: list[str] | None = None) -> int:
    print_banner()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init":
        return _run_init(args)
    if args.command == "receptor-config":
        return _run_receptor_config()
    if args.command == "list-vina-versions":
        return _run_list_vina_versions()
    if args.command == "run":
        return _run_pipeline(args)
    if args.command == "resume":
        return _run_resume(args)
    if args.command == "interactions":
        return _run_interactions(args)
    if args.command == "similarity":
        return _run_similarity(args)
    if args.command == "gcms":
        return _run_gcms(args)

    parser.error(f"Subperintah tidak dikenal: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
