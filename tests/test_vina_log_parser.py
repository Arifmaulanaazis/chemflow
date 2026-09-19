"""Test parser tabel skor Vina dari teks stdout tertangkap (VinaRunner._parse_score_table)."""

from chemflow.docking.vina_runner import VinaRunner

_SAMPLE_NEW_FORMAT = """\
AutoDock Vina v1.2.5
mode |   affinity | dist from best mode
     | (kcal/mol) | rmsd l.b.| rmsd u.b.
-----+------------+----------+----------
   1       -7.234      0.000      0.000
   2       -6.912      1.523      3.001
   3       -6.500      2.100      4.502
"""

_SAMPLE_WITH_EXTRA_TEXT_AFTER = _SAMPLE_NEW_FORMAT + "\nWriting output ... done.\n"


def test_parse_score_table_format_baru():
    lines = _SAMPLE_NEW_FORMAT.splitlines(keepends=True)
    poses = VinaRunner._parse_score_table(lines)
    assert len(poses) == 3
    assert poses[0]["mode"] == 1
    assert poses[0]["affinity"] == -7.234
    assert poses[0]["rmsd_lb"] == 0.0
    assert poses[1]["affinity"] == -6.912


def test_parse_score_table_terurut_afinitas_terbaik_dulu():
    lines = _SAMPLE_NEW_FORMAT.splitlines(keepends=True)
    poses = VinaRunner._parse_score_table(lines)
    affinities = [p["affinity"] for p in poses]
    assert affinities == sorted(affinities)  # Vina selalu urutkan terbaik (paling negatif) dulu


def test_parse_score_table_toleran_teks_tambahan_setelah_tabel():
    lines = _SAMPLE_WITH_EXTRA_TEXT_AFTER.splitlines(keepends=True)
    poses = VinaRunner._parse_score_table(lines)
    assert len(poses) == 3


def test_parse_score_table_kosong_tanpa_separator():
    lines = ["AutoDock Vina v1.2.5\n", "Error: something went wrong\n"]
    poses = VinaRunner._parse_score_table(lines)
    assert poses == []
