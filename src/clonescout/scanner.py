"""Filesystem scanner for CloneScout — classify_path, BaseScanner, FSScanner."""

from __future__ import annotations

import logging
import os
import stat as stat_module
import tarfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from clonescout.config import ScanConfig

from clonescout.models import FileRecord


def classify_path(path: Path) -> str:
    """Classify a candidate scan root.

    Args:
        path: The filesystem path to classify.

    Returns:
        One of ``"DIR"``, ``"ZIP"``, ``"TAR"``, ``"FILE"``,
        ``"NONEXISTENT"``, or ``"UNSUPPORTED"``.
    """
    if not path.exists():
        return "NONEXISTENT"
    if path.is_symlink():
        return "UNSUPPORTED"
    if path.is_dir():
        return "DIR"
    try:
        st = path.stat()
    except OSError:
        return "UNSUPPORTED"
    if not stat_module.S_ISREG(st.st_mode):
        return "UNSUPPORTED"
    if zipfile.is_zipfile(path):
        return "ZIP"
    if tarfile.is_tarfile(path):
        return "TAR"
    return "FILE"


class BaseScanner:
    """Abstract base scanner that iterates over FileRecords from a root.

    Subclasses must implement ``__iter__``.
    """

    def __init__(self, root: Path, config: ScanConfig) -> None:
        self.root = root
        self.config = config

    def __iter__(self) -> Iterator[FileRecord]:
        raise NotImplementedError


class FSScanner(BaseScanner):
    """Walks a local directory tree and yields a FileRecord for every regular file."""

    def __iter__(self) -> Iterator[FileRecord]:
        for dirpath, dirnames, filenames in os.walk(
            self.root,
            followlinks=False,
            onerror=lambda err: logging.warning(
                "Cannot access directory during walk: %s", err
            ),
        ):
            dirnames[:] = [d for d in dirnames if d not in self.config.skip]

            for filename in filenames:
                filepath = Path(dirpath) / filename
                try:
                    st = filepath.lstat()
                except OSError as e:
                    logging.warning("Cannot stat %s: %s", filepath, e)
                    continue

                if not stat_module.S_ISREG(st.st_mode):
                    continue

                resolved = filepath.resolve()
                anchor_path = Path(resolved.anchor)
                anchor = anchor_path.as_posix().rstrip("/")
                folder_name = resolved.parent.name
                relative = resolved.relative_to(anchor_path)
                folder_parent = relative.parent.parent.as_posix().strip("/")
                if folder_parent == ".":
                    folder_parent = ""
                stem = Path(filename).stem
                suffix = Path(filename).suffix
                ext = suffix.lstrip(".").upper()
                size = st.st_size
                mtime = int(st.st_mtime)

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
