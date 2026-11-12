"""Discover a release (write its manifest), download it, and verify it."""

from __future__ import annotations

import datetime as dt
import logging
import os
import tempfile
from pathlib import Path

from . import box, config
from .manifest import (
    FileEntry,
    Manifest,
    load_manifest,
    manifest_path,
    profile_csv,
    sha256_bytes,
    table_name,
)

log = logging.getLogger(__name__)

# A table that shrinks by more than this versus the previous release fails
# discovery. Lahman only ever adds history, so a big drop means a bad file.
MAX_SHRINK = 0.10


class VerificationError(Exception):
    pass


def release_dir(release: str) -> Path:
    return config.CACHE_DIR / release


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _entry_for(name: str, typed_id: str, data: bytes) -> FileEntry:
    entry = FileEntry(name=name, box_file_id=typed_id, size=len(data), sha256=sha256_bytes(data))
    if name.lower().endswith(".csv"):
        entry.table = table_name(name)
        entry.columns, entry.rows = profile_csv(data)
    return entry


# --- discover -----------------------------------------------------------------


def discover(release: str, shared_name: str, source_page: str, force: bool = False) -> Manifest:
    """List the Box folder, download every file, and pin it in a new manifest.

    Refuses to overwrite an existing manifest unless `force`: re-pinning a
    release should be a deliberate, reviewed change.
    """
    path = manifest_path(release)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; pass --force to re-pin it")

    files = box.list_shared_folder(shared_name)
    if not any(f.name.lower().endswith(".csv") for f in files):
        raise VerificationError(f"No CSV files in Box folder {shared_name}")

    entries = []
    for bf in sorted(files, key=lambda f: f.name.lower()):
        log.info("downloading %s (%d bytes)", bf.name, bf.size)
        data = box.download(shared_name, bf.typed_id)
        if len(data) != bf.size:
            raise VerificationError(f"{bf.name}: Box lists {bf.size} bytes, downloaded {len(data)}")
        entries.append(_entry_for(bf.name, bf.typed_id, data))
        _write_atomic(release_dir(release) / bf.name, data)

    tables = [e.table for e in entries if e.table]
    if len(tables) != len(set(tables)):
        raise VerificationError(f"Two files map to the same raw table: {sorted(tables)}")

    manifest = Manifest(
        release=release,
        source_page=source_page,
        box_shared_name=shared_name,
        discovered_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        files=entries,
    )
    previous = _previous_manifest(release)
    if previous:
        compare_releases(previous, manifest)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.to_json())
    log.info("wrote %s (%d files)", path, len(entries))
    return manifest


def _previous_manifest(release: str) -> Manifest | None:
    earlier = sorted(
        p.stem for p in config.RELEASES_DIR.glob("*.json") if p.stem < release
    )
    return load_manifest(earlier[-1]) if earlier else None


def compare_releases(old: Manifest, new: Manifest) -> None:
    """Fail if a table disappeared or shrank sharply since the previous release."""
    new_by_table = {f.table: f for f in new.csv_files}
    problems = []
    for f in old.csv_files:
        n = new_by_table.get(f.table)
        if n is None:
            problems.append(f"{f.table}: missing (was in {old.release})")
        elif f.rows and n.rows is not None and n.rows < f.rows * (1 - MAX_SHRINK):
            problems.append(f"{f.table}: {f.rows} rows in {old.release}, {n.rows} in {new.release}")
        else:
            dropped = set(f.columns) - set(n.columns)
            if dropped:
                problems.append(f"{f.table}: columns dropped since {old.release}: {sorted(dropped)}")
    if problems:
        raise VerificationError("Release looks wrong:\n  " + "\n  ".join(problems))


# --- fetch & verify -------------------------------------------------------------


def verify_file(entry: FileEntry, data: bytes) -> None:
    """Check downloaded bytes against the manifest. Raises VerificationError."""
    if len(data) != entry.size:
        raise VerificationError(f"{entry.name}: expected {entry.size} bytes, got {len(data)}")
    digest = sha256_bytes(data)
    if digest != entry.sha256:
        raise VerificationError(f"{entry.name}: SHA-256 {digest} does not match pinned {entry.sha256}")
    if entry.table:
        columns, rows = profile_csv(data)
        if columns != entry.columns:
            raise VerificationError(f"{entry.name}: header {columns} does not match {entry.columns}")
        if rows != entry.rows:
            raise VerificationError(f"{entry.name}: {rows} rows, manifest says {entry.rows}")


def fetch(release: str) -> Manifest:
    """Download any files not already in the cache, verifying each one.

    A cached file that fails verification is downloaded again once; a fresh
    download that fails is an error.
    """
    manifest = load_manifest(release)
    for entry in manifest.files:
        path = release_dir(release) / entry.name
        if path.exists():
            try:
                verify_file(entry, path.read_bytes())
                log.info("cached  %s", entry.name)
                continue
            except VerificationError as e:
                log.warning("re-downloading %s: %s", entry.name, e)
        log.info("download %s", entry.name)
        data = box.download(manifest.box_shared_name, entry.box_file_id)
        verify_file(entry, data)
        _write_atomic(path, data)
    return manifest


def verify(release: str) -> Manifest:
    """Verify every cached file without touching the network."""
    manifest = load_manifest(release)
    for entry in manifest.files:
        path = release_dir(release) / entry.name
        if not path.exists():
            raise VerificationError(f"{entry.name}: not downloaded (run `fetch`)")
        verify_file(entry, path.read_bytes())
    log.info("verified %d files for release %s", len(manifest.files), release)
    return manifest
