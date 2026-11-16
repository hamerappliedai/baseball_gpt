"""Migration file discovery (no database needed)."""

import pytest

from baseball_pipeline.migrate import MIGRATIONS_DIR, MigrationError, discover


def test_repo_migrations_are_well_formed():
    found = discover(MIGRATIONS_DIR)
    assert found and found[0][1] == "001_accounts.sql"
    assert [v for v, _, _ in found] == sorted(v for v, _, _ in found)


def test_bad_names_and_duplicates_are_rejected(tmp_path):
    (tmp_path / "1_bad.sql").write_text("SELECT 1")
    with pytest.raises(MigrationError):
        discover(tmp_path)
    (tmp_path / "1_bad.sql").unlink()
    (tmp_path / "002_a.sql").write_text("SELECT 1")
    (tmp_path / "002_b.sql").write_text("SELECT 1")
    with pytest.raises(MigrationError):
        discover(tmp_path)
