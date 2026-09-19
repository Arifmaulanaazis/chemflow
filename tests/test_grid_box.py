"""Test GridBox: auto-sizing, vina_args guard, manual construction."""

import pytest

from chemflow.docking.grid_box import GridBox


def test_auto_belum_dikonkretkan():
    box = GridBox(center_x=1.0, center_y=2.0, center_z=3.0)
    assert box.is_auto is True
    with pytest.raises(ValueError):
        box.vina_args()


def test_cube_for_extent_pakai_padding():
    box = GridBox.cube_for_extent(0, 0, 0, extent=10.0, padding=8.0, min_size=18.0)
    assert box.size_x == pytest.approx(18.0)  # 10+8=18, sama dgn min_size
    assert box.is_auto is False


def test_cube_for_extent_dibatasi_min_size():
    box = GridBox.cube_for_extent(0, 0, 0, extent=2.0, padding=1.0, min_size=18.0)
    assert box.size_x == pytest.approx(18.0)  # 2+1=3 < 18 -> pakai min_size


def test_cube_for_extent_none_fallback_min_size():
    box = GridBox.cube_for_extent(0, 0, 0, extent=None, min_size=18.0)
    assert box.size_x == pytest.approx(18.0)


def test_manual_vina_args():
    box = GridBox.from_manual(1.0, 2.0, 3.0, 20.0, 22.0, 24.0)
    args = box.vina_args()
    assert args == [
        "--center_x", "1.0", "--center_y", "2.0", "--center_z", "3.0",
        "--size_x", "20.0", "--size_y", "22.0", "--size_z", "24.0",
    ]
