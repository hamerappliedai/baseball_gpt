import copy

import pytest

from baseball_pipeline import box, fetch
from baseball_pipeline.fetch import VerificationError, compare_releases, verify_file
from baseball_pipeline.manifest import profile_csv, table_name

from .conftest import BATTING, PEOPLE


def test_profile_handles_bom_quotes_and_embedded_newlines():
    columns, rows = profile_csv(PEOPLE)
    assert columns == ["ID", "playerID", "nameFirst", "nameLast", "deathYear"]
    assert rows == 3


def test_profile_rejects_ragged_rows():
    with pytest.raises(ValueError, match="Row 3 has 2 fields"):
        profile_csv(b"a,b,c\r\n1,2,3\r\n1,2\r\n")


@pytest.mark.parametrize(
    "name,expected",
    [("Batting.csv", "batting"), ("FieldingOFsplit.csv", "fieldingofsplit"), ("AllstarFull.csv", "allstarfull")],
)
def test_table_name(name, expected):
    assert table_name(name) == expected


def test_table_name_rejects_unsafe_names():
    with pytest.raises(ValueError):
        table_name("Robert'); DROP TABLE x.csv")


def test_verify_passes_on_pinned_files(release):
    assert fetch.verify("1999") is not None


@pytest.mark.parametrize(
    "tamper,message",
    [
        (lambda b: b + b"x", "expected"),  # size change
        (lambda b: b.replace(b"1927", b"1926"), "SHA-256"),  # same size, different bytes
    ],
)
def test_verify_detects_changed_bytes(release, tamper, message):
    entry = next(e for e in release.files if e.name == "Batting.csv")
    with pytest.raises(VerificationError, match=message):
        verify_file(entry, tamper(BATTING))


def test_verify_detects_header_and_row_drift(release):
    entry = copy.deepcopy(next(e for e in release.files if e.name == "Batting.csv"))
    entry.columns = ["playerID", "yearID", "stint", "doubles", "triples"]
    with pytest.raises(VerificationError, match="header"):
        # Re-pin the hash so the header check is what fails.
        entry.sha256 = fetch.sha256_bytes(BATTING)
        verify_file(entry, BATTING)


def test_verify_reports_missing_download(release):
    (fetch.release_dir("1999") / "Batting.csv").unlink()
    with pytest.raises(VerificationError, match="not downloaded"):
        fetch.verify("1999")


def test_fetch_redownloads_corrupt_cache(release, monkeypatch):
    path = fetch.release_dir("1999") / "Batting.csv"
    path.write_bytes(b"corrupted")
    calls = []
    monkeypatch.setattr(box, "download", lambda shared, fid: calls.append(fid) or BATTING)
    fetch.fetch("1999")
    assert path.read_bytes() == BATTING
    assert len(calls) == 1  # only the bad file was fetched


def test_fetch_rejects_bad_download(release, monkeypatch):
    (fetch.release_dir("1999") / "Batting.csv").unlink()
    monkeypatch.setattr(box, "download", lambda shared, fid: b"<html>not a csv</html>")
    with pytest.raises(VerificationError):
        fetch.fetch("1999")
    assert not (fetch.release_dir("1999") / "Batting.csv").exists()


def test_compare_releases_flags_shrink_and_dropped_columns(release):
    new = copy.deepcopy(release)
    new.release = "2000"
    people = next(f for f in new.files if f.table == "people")
    people.rows = 1  # 3 -> 1 rows
    batting = next(f for f in new.files if f.table == "batting")
    batting.columns = batting.columns[:-1]
    with pytest.raises(VerificationError) as exc:
        compare_releases(release, new)
    assert "people: 3 rows" in str(exc.value)
    assert "columns dropped" in str(exc.value)


def test_compare_releases_allows_growth(release):
    new = copy.deepcopy(release)
    new.release = "2000"
    for f in new.csv_files:
        f.rows += 10
    compare_releases(release, new)


def test_box_listing_follows_pages(monkeypatch):
    def page(n, names):
        items = [{"type": "file", "name": nm, "typedID": f"f_{nm}", "itemSize": 1} for nm in names]
        items.append({"type": "folder", "name": "sub", "typedID": "d_1", "itemSize": 0})
        import json

        data = {"/app-api/enduserapp/shared-folder": {"pageCount": 2, "pageNumber": n, "items": items}}
        return f"<script>Box.postStreamData = {json.dumps(data)};</script>".encode()

    pages = {1: page(1, ["A.csv", "B.csv"]), 2: page(2, ["C.csv"])}
    monkeypatch.setattr(box, "_get", lambda url: pages[int(url.rsplit("=", 1)[1])])
    files = box.list_shared_folder("shared")
    assert [f.name for f in files] == ["A.csv", "B.csv", "C.csv"]
