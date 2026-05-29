"""Archive scanners for CloneScout — ZipScanner, TarScanner."""

from __future__ import annotations

import logging
import posixpath
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

from clonescout.models import FileRecord
from clonescout.scanner import BaseScanner


def _normalize_entry_path(name: str) -> str:
    """Strip leading './' and '/' from an archive entry name.

    Both ZIP and TAR can produce paths with these prefixes depending on
    how the archive was created. Stripping them ensures that equivalent
    paths from different archive types produce identical metadata keys.

    Args:
        name: Raw entry name from ZipInfo.filename or TarInfo.name.

    Returns:
        Clean relative POSIX path (empty string for root-level entries).
        Returns ``""`` for empty-string and ``"."`` inputs.
    """
    cleaned = posixpath.normpath(name)
    if cleaned == ".":
        return ""
    return cleaned.lstrip("/")


class ZipScanner(BaseScanner):
    """Iterates over members of a ZIP archive, yielding a FileRecord per file."""

    def __iter__(self) -> Iterator[FileRecord]:
        anchor = self.root.resolve().as_posix()

        try:
            with zipfile.ZipFile(self.root) as zf:
                for zip_info in zf.infolist():
                    if zip_info.is_dir():
                        continue

                    member_path = _normalize_entry_path(zip_info.filename)
                    if any(
                        comp in self.config.skip
                        for comp in member_path.split("/")
                    ):
                        continue

                    try:
                        parts = member_path.split("/")
                        filename = parts[-1]
                        folder_name = parts[-2] if len(parts) >= 2 else ""
                        folder_parent = (
                            "/".join(parts[:-2]) if len(parts) >= 3 else ""
                        )
                        stem = Path(filename).stem
                        suffix = Path(filename).suffix
                        ext = suffix.lstrip(".").upper()
                        size = zip_info.file_size
                        mtime = int(datetime(*zip_info.date_time).timestamp())

                        yield FileRecord(
                            anchor=anchor,
                            folder_parent=folder_parent,
                            folder_name=folder_name,
                            stem=stem,
                            suffix=suffix,
                            ext=ext,
                            size=size,
                            mtime=mtime,
                        )
                    except Exception as e:
                        logging.warning(
                            "Skipping corrupt member %s in %s: %s",
                            member_path,
                            self.root,
                            e,
                        )
        except Exception as e:
            logging.warning("Cannot read archive %s: %s", self.root, e)


class TarScanner(BaseScanner):
    """Iterates over members of a tar/tar.gz/tgz archive, yielding a FileRecord per file."""

    def __iter__(self) -> Iterator[FileRecord]:
        anchor = self.root.resolve().as_posix()

        try:
            with tarfile.open(self.root) as tf:
                for member in tf:
                    if not member.isfile() or member.type == tarfile.CONTTYPE:
                        continue

                    member_path = _normalize_entry_path(member.name)
                    if any(
                        comp in self.config.skip
                        for comp in member_path.split("/")
                    ):
                        continue

                    try:
                        parts = member_path.split("/")
                        filename = parts[-1]
                        folder_name = parts[-2] if len(parts) >= 2 else ""
                        folder_parent = (
                            "/".join(parts[:-2]) if len(parts) >= 3 else ""
                        )
                        stem = Path(filename).stem
                        suffix = Path(filename).suffix
                        ext = suffix.lstrip(".").upper()
                        size = member.size
                        mtime = int(member.mtime)

                        yield FileRecord(
                            anchor=anchor,
                            folder_parent=folder_parent,
                            folder_name=folder_name,
                            stem=stem,
                            suffix=suffix,
                            ext=ext,
                            size=size,
                            mtime=mtime,
                        )
                    except Exception as e:
                        logging.warning(
                            "Skipping corrupt member %s in %s: %s",
                            member_path,
                            self.root,
                            e,
                        )
        except Exception as e:
            logging.warning("Cannot read archive %s: %s", self.root, e)
