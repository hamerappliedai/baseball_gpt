"""Release manifests: the pinned record of what a good download looks like.

A manifest is created once per release by `discover` (trust on first use) and
committed. Every later download is checked against it: same files, same bytes
(SHA-256), same header, same row count. SABR publishes no checksums, so this is
what catches a file changing upstream without notice.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config

BOM = b"\xef\xbb\xbf"


@dataclass
class FileEntry:
    name: str  # file name in the release, e.g. "Batting.csv"
    box_file_id: str  # Box typed id, e.g. "f_2084275487842"
    size: int
    sha256: str
    table: str | None = None  # raw table name; None for non-CSV files (readme)
    columns: list[str] = field(default_factory=list)
    rows: int | None = None  # data rows, header excluded


@dataclass
class Manifest:
    release: str
    source_page: str  # human-facing page the release was found on
    box_shared_name: str
    discovered_at: str
    files: list[FileEntry]

    @property
    def csv_files(self) -> list[FileEntry]:
        return [f for f in self.files if f.table]

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2) + "\n"

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        return cls(**{**d, "files": [FileEntry(**f) for f in d["files"]]})


def manifest_path(release: str) -> Path:
    return config.RELEASES_DIR / f"{release}.json"


def load_manifest(release: str) -> Manifest:
    path = manifest_path(release)
    if not path.exists():
        raise FileNotFoundError(
            f"No manifest for release {release} at {path}. Run `discover` first."
        )
    return Manifest.from_dict(json.loads(path.read_text()))


def table_name(file_name: str) -> str:
    """Raw table name for a CSV: the lowercased file stem (Batting.csv -> batting).

    Raw keeps the source's naming; snake_case renames happen in staging.
    """
    stem = Path(file_name).stem.lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", stem):
        raise ValueError(f"Cannot derive a safe table name from {file_name!r}")
    return stem


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decode_csv(data: bytes) -> str:
    """Decode a Lahman CSV: UTF-8, with a byte-order mark on some files."""
    if data.startswith(BOM):
        data = data[len(BOM) :]
    return data.decode("utf-8")


def profile_csv(data: bytes) -> tuple[list[str], int]:
    """Return (header columns, data row count), parsed with a real CSV reader
    so quoted commas and newlines are counted correctly."""
    reader = csv.reader(io.StringIO(decode_csv(data), newline=""))
    header = next(reader)
    rows = 0
    for row in reader:
        if not row:  # trailing blank line
            continue
        if len(row) != len(header):
            raise ValueError(
                f"Row {rows + 2} has {len(row)} fields, header has {len(header)}"
            )
        rows += 1
    return header, rows
