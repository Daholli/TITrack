"""Tests for seed revision propagation (_apply_seed_revisions).

_auto_seed_items uses INSERT OR IGNORE, so entries renamed in the seed
(recycled seasonal-compass ConfigBaseIds) never reach existing databases.
The seed meta's "revision" / "revised_ids" mechanism force-updates just
those rows when the stored revision is behind.
"""

import json
import tempfile
from pathlib import Path

import pytest

from titrack.db.connection import Database


SEED = {
    "meta": {
        "revision": 2,
        "revised_ids": ["100"],
    },
    "items": [
        {
            "id": "100",
            "name_en": "Lunaria Compass",
            "name_cn": "月神罗盘",
            "type_cn": "罗盘",
            "img": "https://example.com/new.webp",
            "url_en": "https://tlidb.com/en/Lunaria_Compass",
            "url_cn": "https://tlidb.com/cn/Lunaria_Compass",
        },
        {
            "id": "200",
            "name_en": "Other Item",
            "name_cn": "其他",
            "type_cn": "通用道具",
            "img": None,
            "url_en": None,
            "url_cn": None,
        },
    ],
}


@pytest.fixture
def seeded_db(monkeypatch):
    """Database wired to a temp seed file, with auto-seed enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_path = Path(tmpdir) / "seed.json"
        seed_path.write_text(json.dumps(SEED, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(
            "titrack.config.paths.get_items_seed_path", lambda: seed_path
        )
        database = Database(Path(tmpdir) / "test.db", auto_seed=True)
        database.connect()
        yield database
        database.close()


def _get_name(db, config_base_id):
    row = db.fetchone(
        "SELECT name_en FROM items WHERE config_base_id = ?", (config_base_id,)
    )
    return row["name_en"] if row else None


def _get_setting(db, key):
    row = db.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else None


def test_fresh_seed_records_revision(seeded_db):
    assert _get_name(seeded_db, 100) == "Lunaria Compass"
    assert _get_setting(seeded_db, "items_seed_revision") == "2"


def test_stale_entry_updated_when_revision_behind(seeded_db):
    # Simulate a database seeded before the rename (recycled ID with old name)
    seeded_db.execute(
        "UPDATE items SET name_en = 'Dim Lunar Stone' WHERE config_base_id = 100"
    )
    seeded_db.execute(
        "UPDATE settings SET value = '1' WHERE key = 'items_seed_revision'"
    )

    cursor = seeded_db._connection.cursor()
    seeded_db._apply_seed_revisions(cursor)

    assert _get_name(seeded_db, 100) == "Lunaria Compass"
    assert _get_setting(seeded_db, "items_seed_revision") == "2"


def test_user_edit_preserved_when_revision_current(seeded_db):
    # User renames a revised item after the revision was applied
    seeded_db.execute(
        "UPDATE items SET name_en = 'My Custom Name' WHERE config_base_id = 100"
    )

    cursor = seeded_db._connection.cursor()
    seeded_db._apply_seed_revisions(cursor)

    assert _get_name(seeded_db, 100) == "My Custom Name"


def test_non_revised_entries_untouched(seeded_db):
    # User edit on an item outside revised_ids survives a revision bump
    seeded_db.execute(
        "UPDATE items SET name_en = 'Renamed By User' WHERE config_base_id = 200"
    )
    seeded_db.execute(
        "UPDATE settings SET value = '1' WHERE key = 'items_seed_revision'"
    )

    cursor = seeded_db._connection.cursor()
    seeded_db._apply_seed_revisions(cursor)

    assert _get_name(seeded_db, 200) == "Renamed By User"


MULTI_SEED = {
    "meta": {
        "revision": 2,
        "revisions": {"1": ["100"], "2": ["200"]},
    },
    "items": [
        {**SEED["items"][0]},
        {**SEED["items"][1], "name_en": "Afterlight Compass"},
    ],
}


@pytest.fixture
def multi_db(monkeypatch):
    """Database wired to a seed with per-revision id lists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        seed_path = Path(tmpdir) / "seed.json"
        seed_path.write_text(json.dumps(MULTI_SEED, ensure_ascii=False), encoding="utf-8")
        monkeypatch.setattr(
            "titrack.config.paths.get_items_seed_path", lambda: seed_path
        )
        database = Database(Path(tmpdir) / "test.db", auto_seed=True)
        database.connect()
        yield database
        database.close()


def _stale(db, applied):
    db.execute("UPDATE items SET name_en = 'Stale 100' WHERE config_base_id = 100")
    db.execute("UPDATE items SET name_en = 'Stale 200' WHERE config_base_id = 200")
    db.execute(
        "UPDATE settings SET value = ? WHERE key = 'items_seed_revision'", (applied,)
    )


def test_multiple_revisions_behind_applies_all(multi_db):
    # A database that skipped a release picks up every intermediate rename
    _stale(multi_db, "0")
    multi_db._apply_seed_revisions(multi_db._connection.cursor())

    assert _get_name(multi_db, 100) == "Lunaria Compass"
    assert _get_name(multi_db, 200) == "Afterlight Compass"
    assert _get_setting(multi_db, "items_seed_revision") == "2"


def test_already_applied_revision_not_reapplied(multi_db):
    # Revision 1 was applied earlier (and the user since edited id 100);
    # moving to revision 2 refreshes only revision 2's ids
    _stale(multi_db, "1")
    multi_db._apply_seed_revisions(multi_db._connection.cursor())

    assert _get_name(multi_db, 100) == "Stale 100"
    assert _get_name(multi_db, 200) == "Afterlight Compass"
