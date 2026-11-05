"""RMSD BIOVIA otomatis dengan satu sesi yang dapat dipakai ulang dan cadangan RDKit."""
from __future__ import annotations

import copy
import logging
from pathlib import Path

from chemflow.docking.rmsd_pair import prepare_rmsd_pair
from chemflow.interaction.biovia_install import detect_biovia
from chemflow.interaction.input_lock import InputLock


class RmsdBackendSession:
    def __init__(self, config, validator, logger=None):
        self.cfg, self.validator = config, validator
        self.log = logger or logging.getLogger(__name__)
        self.client = None
        self.lock = None
        self.reason = ""
        self.attempted = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            if self.client is not None:
                self.client.close()
        except Exception:
            self.log.warning("Penutupan sesi RMSD BIOVIA gagal.", exc_info=True)
        finally:
            if self.lock is not None:
                self.lock.unlock()

    def _connect(self):
        if self.attempted:
            return self.client
        self.attempted = True
        if self.cfg.rmsd_backend == "rdkit":
            self.reason = "Backend RDKit dipilih."
            return None
        try:
            executable = detect_biovia(self.cfg.biovia_exe)
        except Exception as exc:
            self.reason = f"Deteksi BIOVIA gagal: {exc}"
            self.log.warning(f"[RMSD] {self.reason} Memakai perhitungan RDKit.")
            return None
        if executable is None:
            self.reason = "BIOVIA atau dependensi otomasi tidak tersedia."
            self.log.info(f"[RMSD] {self.reason} Memakai perhitungan RDKit.")
            return None
        from chemflow.interaction.biovia_rmsd import BioviaRmsdClient

        self.lock = InputLock(enabled=self.cfg.lock_input, logger=self.log)
        try:
            self.lock.lock()
            self.client = BioviaRmsdClient(executable, self.cfg.biovia_launch_timeout,
                                          logger=self.log, input_lock=self.lock)
            self.client.prepare()
        except Exception as exc:
            self._disable(str(exc))
        return self.client

    def _disable(self, reason):
        self.reason = reason
        try:
            if self.client is not None:
                self.client.recover()
                self.client.close()
        except Exception:
            self.log.debug("Pemulihan RMSD BIOVIA gagal.", exc_info=True)
        finally:
            self.client = None
            if self.lock is not None:
                self.lock.unlock()
        self.log.warning(f"[RMSD] BIOVIA gagal; sisa validasi memakai RDKit: {reason}")

    def enhance(self, result, native_block, pose, label, *, template_smiles, directory, pose_name):
        """Simpan pasangan molekul yang dapat diperiksa dan coba BIOVIA dengan cadangan RDKit."""
        result = copy.copy(result)
        details = {"rdkit_rmsd_angstrom": result.rmsd, "rmsd_backend": "rdkit",
                   "rmsd_pair": "", "native_crystal": "", "docked_molecule": "",
                   "biovia_report": "", "rmsd_overlay": "", "rmsd_transport": "",
                   "fallback_reason": "", "pair_error": ""}
        try:
            pair = prepare_rmsd_pair(native_block, pose, label=label, pose_name=pose_name,
                                     template_smiles=template_smiles)
            paths = pair.write(directory)
            for field, key in (("rmsd_pair", "pair"), ("native_crystal", "native_crystal"),
                               ("docked_molecule", "docked")):
                details[field] = self._relative(paths[key])
        except Exception as exc:
            details["pair_error"] = str(exc)
            details["fallback_reason"] = f"Pasangan BIOVIA tidak dapat disiapkan: {exc}"
            result.note = (result.note + " " + details["fallback_reason"]).strip()
            return result, details
        client = self._connect()
        if client is not None:
            try:
                measurement = client.calculate_rmsd(pair, directory,
                                                     save_overlay=self.cfg.rmsd_overlay)
                result.rmsd = round(measurement.rmsd, 3)
                result.status = self.validator._classify(measurement.rmsd)
                result.method = "BIOVIA_HeavyAtoms"
                result.note = ("BIOVIA CalculateHeavyAtomRmsd; atom berat dipetakan menurut topologi "
                               "dan simetri, pada koordinat kristal asli tanpa superposisi. "
                               "Native sian; hasil docking jingga. " + measurement.visualization_note).strip()
                details.update(rmsd_backend="biovia", rmsd_transport=measurement.transport,
                               biovia_report=self._relative(measurement.report_path),
                               rmsd_overlay=self._relative(measurement.overlay_path) if measurement.overlay_path else "")
                return result, details
            except Exception as exc:
                self._disable(str(exc))
        if self.cfg.rmsd_backend != "rdkit":
            details["fallback_reason"] = self.reason
            result.note = (result.note + f" Fallback RDKit: {self.reason}").strip()
        return result, details

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.cfg.output_dir.resolve()).as_posix()
