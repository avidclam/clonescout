"""Unit tests for archive.py — ZipScanner, TarScanner."""

from __future__ import annotations

import io
import logging
import tarfile
import zipfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from clonescout.archive import TarScanner, ZipScanner
from clonescout.config import ScanConfig


class TestZipScanner:
    def test_member_in_subdirectory_yields_correct_record(
        self, tmp_path: Path
    ) -> None:
        archive_path = tmp_path / "test.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("photos/2021/IMG_001.jpg", b"fake image data")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = ZipScanner(archive_path, cfg)
        records = list(scanner)

        assert len(records) == 1
        rec = records[0]
        assert rec.stem == "IMG_001"
        assert rec.suffix == ".jpg"
        assert rec.ext == "JPG"
        assert rec.folder_name == "2021"
        assert rec.folder_parent == "photos"
        assert rec.size == len(b"fake image data")
        assert isinstance(rec.mtime, int)
        assert rec.anchor == archive_path.resolve().as_posix()

    def test_member_at_root_produces_empty_fields(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "test.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("report.pdf", b"pdf data")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = ZipScanner(archive_path, cfg)
        records = list(scanner)

        assert len(records) == 1
        rec = records[0]
        assert rec.stem == "report"
        assert rec.suffix == ".pdf"
        assert rec.folder_name == ""
        assert rec.folder_parent == ""

    def test_skip_suppresses_matching_components(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "test.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("src/main.py", b"code")
            zf.writestr("node_modules/pkg/index.js", b"lib")
            zf.writestr(".git/HEAD", b"ref")

        cfg = ScanConfig(
            root=["dummy"],
            output="dummy.zip",
            skip=["node_modules", ".git"],
        )
        scanner = ZipScanner(archive_path, cfg)
        records = list(scanner)

        stems = {r.stem for r in records}
        assert stems == {"main"}

    def test_directory_entries_are_skipped(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "test.zip"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("subdir/", "")
            zf.writestr("subdir/file.txt", b"text")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = ZipScanner(archive_path, cfg)
        records = list(scanner)

        assert len(records) == 1
        assert records[0].stem == "file"

    def test_corrupt_zip_logs_warning_yields_nothing(
        self, tmp_path: Path, caplog
    ) -> None:
        bad_archive = tmp_path / "bad.zip"
        bad_archive.write_text("not a valid zip file")

        caplog.set_level(logging.WARNING)
        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = ZipScanner(bad_archive, cfg)
        records = list(scanner)

        assert len(records) == 0
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "Cannot read archive" in warnings[0].message


class TestTarScanner:
    def test_member_in_subdirectory_yields_correct_record(
        self, tmp_path: Path
    ) -> None:
        archive_path = tmp_path / "test.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            _add_tar_member(tf, "photos/2021/IMG_001.jpg", b"fake image data")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = TarScanner(archive_path, cfg)
        records = list(scanner)

        assert len(records) == 1
        rec = records[0]
        assert rec.stem == "IMG_001"
        assert rec.suffix == ".jpg"
        assert rec.ext == "JPG"
        assert rec.folder_name == "2021"
        assert rec.folder_parent == "photos"
        assert rec.size == len(b"fake image data")
        assert rec.mtime == 1234567890
        assert rec.anchor == archive_path.resolve().as_posix()

    def test_member_at_root_produces_empty_fields(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "test.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            _add_tar_member(tf, "report.pdf", b"pdf data")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = TarScanner(archive_path, cfg)
        records = list(scanner)

        assert len(records) == 1
        rec = records[0]
        assert rec.stem == "report"
        assert rec.suffix == ".pdf"
        assert rec.folder_name == ""
        assert rec.folder_parent == ""

    def test_skip_suppresses_matching_components(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "test.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            _add_tar_member(tf, "src/main.py", b"code")
            _add_tar_member(tf, "node_modules/pkg/index.js", b"lib")
            _add_tar_member(tf, ".git/HEAD", b"ref")

        cfg = ScanConfig(
            root=["dummy"],
            output="dummy.zip",
            skip=["node_modules", ".git"],
        )
        scanner = TarScanner(archive_path, cfg)
        records = list(scanner)

        stems = {r.stem for r in records}
        assert stems == {"main"}

    def test_non_regular_members_are_skipped(self, tmp_path: Path) -> None:
        archive_path = tmp_path / "test.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            _add_tar_member(tf, "data/file.txt", b"content")
            # add a directory member
            dir_info = tarfile.TarInfo(name="data/")
            dir_info.type = tarfile.DIRTYPE
            tf.addfile(dir_info, io.BytesIO(b""))

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = TarScanner(archive_path, cfg)
        records = list(scanner)

        assert len(records) == 1
        assert records[0].stem == "file"

    def test_corrupt_tar_logs_warning_yields_nothing(
        self, tmp_path: Path, caplog
    ) -> None:
        bad_archive = tmp_path / "bad.tar.gz"
        bad_archive.write_text("not a valid tar.gz file")

        caplog.set_level(logging.WARNING)
        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = TarScanner(bad_archive, cfg)
        records = list(scanner)

        assert len(records) == 0
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1
        assert "Cannot read archive" in warnings[0].message


def _add_tar_member(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    """Add a regular file member to an open TarFile."""
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 1234567890
    tf.addfile(info, io.BytesIO(data))
