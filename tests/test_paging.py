"""Test pemotongan otomatis grafik besar: halaman seimbang, ubin, dan nama file bagian."""

import pytest

from chemflow.analytics.paging import Page, paged_name, paginate, paginate_grid


def test_paginate_seimbang_bukan_sisa_kecil():
    pages = paginate(25, 20)
    assert [p.count for p in pages] == [13, 12]
    assert [(p.start, p.stop) for p in pages] == [(0, 13), (13, 25)]
    assert all(p.total == 2 for p in pages)


def test_paginate_kelipatan_pas():
    assert [p.count for p in paginate(60, 30)] == [30, 30]


def test_paginate_muat_satu_halaman():
    pages = paginate(20, 20)
    assert len(pages) == 1 and pages[0].is_single
    assert pages[0].suffix == "" and pages[0].title_suffix == ""


@pytest.mark.parametrize("limit", [0, None, -3])
def test_paginate_tanpa_batas(limit):
    pages = paginate(500, limit)
    assert len(pages) == 1 and pages[0].count == 500


def test_paginate_kosong():
    assert paginate(0, 10) == []


@pytest.mark.parametrize("n, size", [(1, 1), (7, 3), (31, 30), (100, 7), (30, 30)])
def test_paginate_menutup_semua_item_tanpa_tumpang_tindih(n, size):
    pages = paginate(n, size)
    covered = [i for p in pages for i in range(p.start, p.stop)]
    assert covered == list(range(n))
    assert max(p.count for p in pages) <= size
    assert max(p.count for p in pages) - min(p.count for p in pages) <= 1


def test_page_slice_dan_akhiran():
    page = Page(2, 3, 4, 8)
    assert page.slice(list(range(10))) == [4, 5, 6, 7]
    assert page.suffix == "_part02of03"
    assert page.title_suffix == " (bagian 2/3)"


def test_paged_name_menyisipkan_akhiran_sebelum_ekstensi():
    assert paged_name("bar_affinity.png", Page(2, 3, 0, 1)) == "bar_affinity_part02of03.png"
    assert paged_name("bar_affinity.png", Page(1, 1, 0, 1)) == "bar_affinity.png"


def test_paginate_grid_berurutan_baris_demi_baris():
    tiles = paginate_grid(5, 5, max_rows=3, max_cols=2)
    assert len(tiles) == 6 and all(t.total == 6 for t in tiles)
    assert [t.index for t in tiles] == [1, 2, 3, 4, 5, 6]
    assert [(t.rows.index, t.cols.index) for t in tiles] == [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3)]


def test_paginate_grid_satu_ubin_tanpa_akhiran():
    tiles = paginate_grid(3, 4, max_rows=30, max_cols=20)
    assert len(tiles) == 1 and tiles[0].suffix == "" and tiles[0].title_suffix == ""


def test_tile_title_menyebut_rentang():
    tile = paginate_grid(10, 10, max_rows=5, max_cols=10)[1]
    assert tile.title_suffix == " (bagian 2/2: baris 6-10)"
    assert paged_name("h.png", tile) == "h_part02of02.png"
