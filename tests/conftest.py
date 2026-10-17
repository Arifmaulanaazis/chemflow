"""Keep executable preferences isolated from the user's real configuration."""
import pytest


@pytest.fixture(autouse=True)
def isolated_openbabel_config(tmp_path, monkeypatch):
    monkeypatch.setenv("CHEMFLOW_CONFIG_DIR", str(tmp_path / "preferences"))
