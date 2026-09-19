"""Test gaya grafik bersama: format, penyimpanan multi-format, isolasi rcParams."""

import matplotlib.pyplot as plt
import pytest

from chemflow.analytics.style import PALETTE, chart_style, clean_axes, normalize_formats, save_figure


def test_normalize_formats_png_selalu_ada():
    assert normalize_formats(("svg",)) == ("png", "svg")
    assert normalize_formats(("PDF", ".png", "pdf")) == ("pdf", "png")


def test_normalize_formats_tak_didukung_raise():
    with pytest.raises(ValueError, match="tidak didukung"):
        normalize_formats(("tiff",))


def test_save_figure_menulis_semua_format(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    path = save_figure(fig, tmp_path / "grafik.png", dpi=100, formats=("png", "svg", "pdf"))
    assert path == tmp_path / "grafik.png"
    for suffix in (".png", ".svg", ".pdf"):
        assert (tmp_path / f"grafik{suffix}").exists()


def test_chart_style_tidak_mengubah_rcparams_global():
    before = plt.rcParams["axes.titleweight"], plt.rcParams["font.size"]
    with chart_style():
        assert plt.rcParams["axes.titleweight"] == "bold"
    assert (plt.rcParams["axes.titleweight"], plt.rcParams["font.size"]) == before


def test_clean_axes_buang_spine_atas_kanan():
    fig, ax = plt.subplots()
    clean_axes(ax, grid_axis="x")
    assert not ax.spines["top"].get_visible()
    assert not ax.spines["right"].get_visible()
    assert ax.spines["left"].get_visible()
    plt.close(fig)


def test_palet_tanpa_duplikat():
    assert len(PALETTE) == len(set(PALETTE))


def test_annotate_without_overlap_label_tidak_bertumpuk():
    from chemflow.analytics.style import annotate_without_overlap

    fig, ax = plt.subplots(figsize=(6, 4))
    xs, ys = [1.0, 1.0, 1.0, 1.0], [1.0, 1.0, 1.0, 1.0]
    labels = ["Aspirin", "Ibuprofen", "Naproxen", "Caffeine"]
    ax.scatter(xs, ys)
    ax.set_xlim(0, 2)
    ax.set_ylim(0, 2)
    annotate_without_overlap(ax, xs, ys, labels)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    notes = [c for c in ax.get_children() if c.__class__.__name__ == "Annotation"]
    assert len(notes) == 4
    boxes = [n.get_window_extent(renderer) for n in notes]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not boxes[i].overlaps(boxes[j])
    plt.close(fig)


def test_annotate_without_overlap_menghindari_obstacle():
    from chemflow.analytics.style import annotate_without_overlap

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.scatter([1.0], [1.0])
    ax.set_xlim(0, 2)
    ax.set_ylim(0, 2)
    obstacle = ax.text(1.0, 1.0, "HBD", fontsize=8, ha="left", va="bottom")
    annotate_without_overlap(ax, [1.0], [1.0], ["Emodin"], obstacles=[obstacle])
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()

    note = next(c for c in ax.get_children() if c.__class__.__name__ == "Annotation")
    assert not note.get_window_extent(renderer).overlaps(obstacle.get_window_extent(renderer))
    plt.close(fig)


def test_judul_figure_tebal_seperti_judul_sumbu():
    from chemflow.analytics.style import chart_style

    with chart_style():
        fig = plt.figure()
        text = fig.suptitle("Judul")
        assert text.get_fontweight() == "bold"
        plt.close(fig)
