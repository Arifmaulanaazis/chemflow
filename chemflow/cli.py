"""
Antarmuka baris perintah (CLI) chemflow.

Subperintah:
    chemflow init                 Buat template Excel input & cek kesiapan mesin.
    chemflow receptor-config      Susun Excel reseptor secara interaktif (kode PDB + pilih ligan native).
    chemflow run --ligands ... --receptors ...   Jalankan pipeline penuh.
    chemflow list-vina-versions   Tampilkan versi AutoDock Vina yang kompatibel.
    chemflow similarity --output hasil/   Analisis similaritas interaksi vs ligan native.

Contoh pemakaian:

    python -m chemflow init --output contoh/

    python -m chemflow receptor-config

    python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx \\
        --output hasil/ --exhaustiveness 16 --n-replicates 3 \\
        --run-rmsd-validation

    python -m chemflow list-vina-versions

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
    sub.add_parser("list-vina-versions", help="Tampilkan versi AutoDock Vina yang kompatibel dengan mesin ini.")
    _add_similarity_subparser(sub)

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
    g_grid.add_argument("--default-box-size", type=float, default=20.0)
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

    g_rmsd = p.add_argument_group("Validasi RMSD redocking")
    g_rmsd.add_argument("--run-rmsd-validation", action="store_true")
    g_rmsd.add_argument("--rmsd-threshold-good", type=float, default=2.0)
    g_rmsd.add_argument("--rmsd-threshold-acceptable", type=float, default=3.0)

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

    g_log = p.add_argument_group("Logging")
    g_log.add_argument("--verbose", action="store_true")
    g_log.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    g_log.add_argument("--no-progress", action="store_true", help="Matikan progress bar (tetap ada log biasa).")


def _add_similarity_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "similarity",
        help="Analisis similaritas interaksi ligan-reseptor vs ligan native (Pratama et al. 2021), "
             "bisa di-rerun kapan saja pada folder output run yang sudah ada.",
    )
    p.add_argument("--output", type=Path, required=True,
                    help="Folder output 'chemflow run' yang berisi complexes/ (WAJIB run --run-rmsd-validation "
                         "sebelumnya agar kompleks referensi native tersedia).")
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
        default_box_size=args.default_box_size, interactive_gridbox=not args.no_interactive_gridbox,
        force_field=args.force_field, minimize_max_iters=args.minimize_max_iters,
        generate_2d_image=not args.no_2d_image,
        remove_waters=not args.keep_waters, remove_hetero_ligands=not args.keep_hetero_ligands,
        keep_metals=not args.no_keep_metals, kollman_fallback_zero=(args.kollman_fallback == "zero"),
        vina_version=args.vina_version, vina_executable=args.vina_executable,
        exhaustiveness=args.exhaustiveness, num_modes=args.num_modes, energy_range=args.energy_range,
        seed=args.seed, n_replicates=args.n_replicates,
        merge_mode=args.merge_mode,
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
        verbose=args.verbose, log_level=args.log_level, show_progress=not args.no_progress,
    )
    return Pipeline(config).run()


def _run_similarity(args: argparse.Namespace) -> int:
    from chemflow.similarity.similarity import SimilarityAnalyzer, export_similarity_results

    print(f"Menganalisis similaritas interaksi di: {args.output}")
    try:
        results = SimilarityAnalyzer().analyze_output_dir(
            args.output, interactions_dir=args.interactions_dir, interaction_suffix=args.interaction_suffix,
        )
    except FileNotFoundError as exc:
        print(f"  Gagal: {exc}")
        return 1

    if not results:
        print("  Tidak ada hasil similaritas yang bisa dihitung (lihat warning di atas untuk penyebabnya).")
        return 0

    out_path = export_similarity_results(results, args.output / args.result_filename)
    print(f"  {len(results)} pasangan ligan-reseptor berhasil dianalisis.")
    print(f"  Hasil tersimpan di: {out_path}")

    if not args.no_plots:
        from chemflow.analytics.style import normalize_formats
        from chemflow.similarity.plots import SimilarityPlotter

        plotter = SimilarityPlotter(args.output / "analytics", dpi=args.dpi,
                                    formats=normalize_formats(args.figure_formats))
        plots = plotter.plot_all(results)
        for path in plots:
            print(f"  Grafik: {path}")
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
    if args.command == "similarity":
        return _run_similarity(args)

    parser.error(f"Subperintah tidak dikenal: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
