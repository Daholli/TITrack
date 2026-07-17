"""Tests for cross-platform path resolution (Linux/Nix support)."""

from pathlib import Path

from titrack.config.paths import get_data_dir, get_resource_path
from titrack.config.settings import get_default_db_path


def test_resource_path_env_override(tmp_path, monkeypatch):
    """TITRACK_RESOURCE_DIR takes precedence when the file exists there."""
    seed = tmp_path / "tlidb_items_seed_en.json"
    seed.write_text("{}")
    monkeypatch.setenv("TITRACK_RESOURCE_DIR", str(tmp_path))

    assert get_resource_path("tlidb_items_seed_en.json") == seed


def test_resource_path_env_override_ignored_when_missing(tmp_path, monkeypatch):
    """An env dir without the file falls through to normal resolution."""
    monkeypatch.setenv("TITRACK_RESOURCE_DIR", str(tmp_path))

    result = get_resource_path("tlidb_items_seed_en.json")
    assert result != tmp_path / "tlidb_items_seed_en.json"
    # Dev checkout: resolves to the project root copy
    assert result.exists()


def test_resource_path_package_fallback(monkeypatch):
    """A resource absent from the project root resolves beside the package."""
    monkeypatch.delenv("TITRACK_RESOURCE_DIR", raising=False)

    result = get_resource_path("does_not_exist_anywhere.json")
    # Fallback is <site-packages>/titrack/<name> (src/titrack in dev)
    assert result.parent.name == "titrack"


def test_data_dir_xdg_on_linux(tmp_path, monkeypatch):
    """Without LOCALAPPDATA on non-Windows, XDG_DATA_HOME is used."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr("titrack.config.paths.sys.platform", "linux")

    result = get_data_dir()
    assert result == tmp_path / "TITracker"
    assert result.is_dir()


def test_default_db_path_xdg_fallback(tmp_path, monkeypatch):
    """Without LOCALAPPDATA and no legacy ~/.titrack, use XDG data home."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))

    assert get_default_db_path() == tmp_path / "xdg" / "TITracker" / "tracker.db"


def test_default_db_path_keeps_legacy(tmp_path, monkeypatch):
    """A pre-existing legacy ~/.titrack/tracker.db is kept."""
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    home = tmp_path / "home"
    legacy = home / ".titrack" / "tracker.db"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

    assert get_default_db_path() == legacy
