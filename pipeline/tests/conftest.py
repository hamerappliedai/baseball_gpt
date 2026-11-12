import pytest

from baseball_pipeline import config
from baseball_pipeline.fetch import _entry_for
from baseball_pipeline.manifest import Manifest

# Small stand-ins for Lahman files, covering the awkward cases:
# a BOM, CRLF endings, empty fields, a quoted comma, a quoted newline.
PEOPLE = (
    b"\xef\xbb\xbfID,playerID,nameFirst,nameLast,deathYear\r\n"
    b"1,ruthba01,Babe,Ruth,1948\r\n"
    b'2,judgeaa01,Aaron,"Judge, Jr.",\r\n'
    b'3,oddca01,"Car\r\nl",Odd,""\r\n'
)
BATTING = b"playerID,yearID,stint,2B,3B\r\nruthba01,1927,1,29,8\r\nruthba01,1928,1,,\r\n"
README = b"read me\n"

FILES = {"People.csv": PEOPLE, "Batting.csv": BATTING, "readme.txt": README}


@pytest.fixture
def release(tmp_path, monkeypatch):
    """A fake release '1999' pinned in a temp manifest dir and cached on disk."""
    monkeypatch.setattr(config, "RELEASES_DIR", tmp_path / "releases")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    cache = tmp_path / "cache" / "1999"
    cache.mkdir(parents=True)
    entries = []
    for i, (name, data) in enumerate(FILES.items()):
        (cache / name).write_bytes(data)
        entries.append(_entry_for(name, f"f_{i}", data))
    m = Manifest("1999", "https://example.test", "shared", "2000-01-01T00:00:00+00:00", entries)
    config.RELEASES_DIR.mkdir()
    (config.RELEASES_DIR / "1999.json").write_text(m.to_json())
    return m

