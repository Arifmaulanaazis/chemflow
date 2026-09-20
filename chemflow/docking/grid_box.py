"""GridBox: parameter kotak pencarian AutoDock Vina."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

MAX_BOX_SIZE = 30.0


def parse_box_size(text: str, default: float) -> Optional[Tuple[float, float, float]]:
    """Tafsirkan ukuran kotak: kosong memakai ``default``, satu angka untuk kubus, tiga angka untuk x y z.

    Returns:
        ``(x, y, z)``, atau ``None`` bila masukan tidak valid.
    """
    tokens = text.split()
    if not tokens:
        return (default, default, default)
    try:
        values = [float(t.replace(",", ".")) for t in tokens]
    except ValueError:
        return None
    if len(values) == 1:
        values = values * 3
    if len(values) != 3 or any(not math.isfinite(v) or v <= 0 for v in values):
        return None
    return (values[0], values[1], values[2])


@dataclass
class GridBox:
    """Parameter grid box AutoDock Vina.

    ``size_x/y/z`` bernilai ``None`` berarti "belum ditentukan" (template
    auto-sizing), harus dikonkretkan lewat ``cube_for_extent()`` per-ligan
    sebelum dipakai Vina (``vina_args()`` raise jika masih ``None``).
    """
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    size_x: Optional[float] = None
    size_y: Optional[float] = None
    size_z: Optional[float] = None
    ref_label: Optional[str] = None

    @property
    def is_auto(self) -> bool:
        return self.size_x is None or self.size_y is None or self.size_z is None

    def vina_args(self) -> List[str]:
        """Argumen CLI Vina untuk gridbox ini.

        Raises:
            ValueError: ukuran belum dikonkretkan (``is_auto`` True).
        """
        if self.is_auto:
            raise ValueError(
                "Ukuran GridBox belum dikonkretkan. Panggil cube_for_extent() "
                "untuk ligan spesifik sebelum dipakai Vina."
            )
        return [
            "--center_x", str(self.center_x), "--center_y", str(self.center_y), "--center_z", str(self.center_z),
            "--size_x", str(self.size_x), "--size_y", str(self.size_y), "--size_z", str(self.size_z),
        ]

    @classmethod
    def cube_for_extent(
        cls, cx: float, cy: float, cz: float, extent: Optional[float],
        padding: float = 8.0, min_size: float = 18.0, ref_label: Optional[str] = None,
    ) -> "GridBox":
        """Bangun gridbox kubus berukuran sesuai ekstensi 3D ligan + padding.

        Kubus (bukan kotak rapat per-sumbu) supaya ligan punya ruang
        isotropik untuk berotasi tanpa langsung menabrak dinding di sumbu
        yang kebetulan paling pendek.

        Args:
            cx, cy, cz: pusat gridbox (biasanya centroid ligan native).
            extent: dimensi bounding-box terbesar ligan (Angstrom); ``None``
                jika perhitungan ekstensi gagal -> jatuh ke ``min_size``.
            padding: ruang tambahan di atas ekstensi ligan.
            min_size: ukuran minimum absolut.
            ref_label: label ligan referensi (untuk pelaporan).
        """
        base = extent if extent is not None else 0.0
        side = max(base + padding, min_size)
        return cls(center_x=cx, center_y=cy, center_z=cz, size_x=side, size_y=side, size_z=side,
                    ref_label=ref_label)

    @staticmethod
    def suggested_size(
        extent: Optional[float], padding: float = 8.0, min_size: float = 18.0, max_size: float = MAX_BOX_SIZE,
    ) -> float:
        """Sisi kubus (Angstrom) yang memuat ligan native beserta ruang gerak.

        Ekstensi + padding, minimal ``min_size``, dibulatkan ke atas, maksimum ``max_size``.
        Ini ukuran default gridbox saat pengguna tidak menentukan ukuran sendiri.
        """
        box = GridBox.cube_for_extent(0.0, 0.0, 0.0, extent, padding=padding, min_size=min_size)
        return float(min(math.ceil(box.size_x), max_size))

    @classmethod
    def from_manual(cls, cx: float, cy: float, cz: float,
                     sx: float = 20.0, sy: float = 20.0, sz: float = 20.0,
                     ref_label: Optional[str] = None) -> "GridBox":
        return cls(center_x=cx, center_y=cy, center_z=cz, size_x=sx, size_y=sy, size_z=sz, ref_label=ref_label)

    def to_dict(self) -> dict:
        return {
            "gridbox_center_x": self.center_x, "gridbox_center_y": self.center_y, "gridbox_center_z": self.center_z,
            "gridbox_size_x": self.size_x if self.size_x is not None else "auto",
            "gridbox_size_y": self.size_y if self.size_y is not None else "auto",
            "gridbox_size_z": self.size_z if self.size_z is not None else "auto",
            "ref_ligand": self.ref_label or "",
        }
