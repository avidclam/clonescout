"""Unit tests for scanner.py — classify_path, BaseScanner, FSScanner."""

from __future__ import annotations

import logging
import tarfile
import zipfile
from pathlib import Path

import pytest

from clonescout.config import ScanConfig
from clonescout.scanner import BaseScanner, FSScanner, classify_path


class TestClassifyPath:
    def test_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        assert classify_path(d) == "DIR"

    def test_zip(self, tmp_path: Path) -> None:
        z = tmp_path / "test.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("dummy.txt", "hello")
        assert classify_path(z) == "ZIP"

    def test_tar_gz(self, tmp_path: Path) -> None:
        t = tmp_path / "test.tar.gz"
        with tarfile.open(t, "w:gz") as tf:
            _add_tar_member(tf, "dummy.txt", b"hello")
        assert classify_path(t) == "TAR"

    def test_regular_file(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("hello")
        assert classify_path(f) == "FILE"

    def test_nonexistent(self, tmp_path: Path) -> None:
        assert classify_path(tmp_path / "does_not_exist") == "NONEXISTENT"

    def test_symlink(self, tmp_path: Path) -> None:
        target = tmp_path / "real_file.txt"
        target.write_text("data")
        link = tmp_path / "link_to_file"
        link.symlink_to(target)
        assert classify_path(link) == "UNSUPPORTED"

    def test_symlink_to_dir(self, tmp_path: Path) -> None:
        target = tmp_path / "real_dir"
        target.mkdir()
        link = tmp_path / "link_to_dir"
        link.symlink_to(target)
        assert classify_path(link) == "UNSUPPORTED"


class TestBaseScanner:
    def test_stores_root_and_config(self) -> None:
        cfg = ScanConfig(root=["/tmp"], output="out.zip")
        scanner = BaseScanner(Path("/tmp"), cfg)
        assert scanner.root == Path("/tmp")
        assert scanner.config is cfg

    def test_iter_raises(self) -> None:
        cfg = ScanConfig(root=["/tmp"], output="out.zip")
        scanner = BaseScanner(Path("/tmp"), cfg)
        with pytest.raises(NotImplementedError):
            iter(scanner)  # Calls __iter__ which raises NotImplementedError


class TestFSScanner:
    def test_simple_file_yields_correct_record(self, tmp_path: Path) -> None:
        scan_root = tmp_path / "scanme"
        subdir = scan_root / "subdir"
        subdir.mkdir(parents=True)
        filepath = subdir / "report.pdf"
        filepath.write_text("dummy content")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = FSScanner(scan_root, cfg)
        records = list(scanner)

        assert len(records) == 1
        rec = records[0]
        assert rec.stem == "report"
        assert rec.suffix == ".pdf"
        assert rec.ext == "PDF"
        assert rec.folder_name == "subdir"
        assert rec.size == len("dummy content")
        assert isinstance(rec.mtime, int)
        assert rec.anchor == ""

    def test_file_in_root_level_has_sensible_fields(self, tmp_path: Path) -> None:
        scan_root = tmp_path / "scanme"
        scan_root.mkdir()
        filepath = scan_root / "top_level.txt"
        filepath.write_text("hello")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = FSScanner(scan_root, cfg)
        records = list(scanner)

        assert len(records) == 1
        rec = records[0]
        assert rec.stem == "top_level"
        assert rec.suffix == ".txt"
        assert rec.folder_name == "scanme"
        assert isinstance(rec.folder_parent, str)
        assert rec.folder_parent != "."

    def test_skip_prunes_subdirectory(self, tmp_path: Path) -> None:
        scan_root = tmp_path / "scanme"
        keep_dir = scan_root / "keep"
        skip_dir = scan_root / "node_modules"
        keep_dir.mkdir(parents=True)
        skip_dir.mkdir(parents=True)
        (keep_dir / "a.txt").write_text("keep")
        (skip_dir / "b.txt").write_text("discard")
        (skip_dir / "sub").mkdir(parents=True, exist_ok=True)
        (skip_dir / "sub" / "c.txt").write_text("discard")

        cfg = ScanConfig(root=["dummy"], output="dummy.zip", skip=["node_modules"])
        scanner = FSScanner(scan_root, cfg)
        records = list(scanner)

        assert len(records) == 1
        assert records[0].stem == "a"

    def test_symlinks_are_not_yielded(self, tmp_path: Path) -> None:
        scan_root = tmp_path / "scanme"
        scan_root.mkdir()
        target = scan_root / "real.txt"
        target.write_text("data")
        link = scan_root / "link.txt"
        link.symlink_to(target)

        cfg = ScanConfig(root=["dummy"], output="dummy.zip")
        scanner = FSScanner(scan_root, cfg)
        records = list(scanner)

        stems = {r.stem for r in records}
        assert "real" in stems
        assert "link" not in stems

    def test_permission_error_logs_warning_and_continues(
        self, tmp_path: Path, caplog
    ) -> None:
        scan_root = tmp_path / "scanme"
        accessible = scan_root / "okdir"
        restricted = scan_root / "locked"
        accessible.mkdir(parents=True)
        restricted.mkdir(parents=True)
        (accessible / "good.txt").write_text("data")

        try:
            restricted.chmod(0o000)
            caplog.set_level(logging.WARNING)
            cfg = ScanConfig(root=["dummy"], output="dummy.zip")
            scanner = FSScanner(scan_root, cfg)
            records = list(scanner)
        finally:
            restricted.chmod(0o755)

        assert len(records) == 1
        assert records[0].stem == "good"
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) >= 1


def _add_tar_member(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    """Add a file member to an open TarFile."""
    import io

    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 1234567890
    tf.addfile(info, io.BytesIO(data))
