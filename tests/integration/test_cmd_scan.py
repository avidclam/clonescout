"""Integration tests for the scan command — run_scan()."""

from __future__ import annotations

import io
import re
import tarfile
import zipfile
from typing import TYPE_CHECKING

import pytest

from clonescout.commands.scan import run_scan
from clonescout.config import ScanConfig
from clonescout.constants import EXIT_BAD_ARGS, EXIT_RUNTIME_ERROR
from clonescout.storage import read_zip

if TYPE_CHECKING:
    from pathlib import Path


class TestRunScanDirectory:
    def test_happy_path_creates_zip_and_counts_files(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        (root / "sub").mkdir(parents=True)
        (root / "a.txt").write_text("hello")
        (root / "b.txt").write_text("world")
        (root / "sub" / "c.pdf").write_text("data")

        output = tmp_path / "out.zip"
        config = ScanConfig(node="test-node", root=[str(root)], output=str(output))
        run_scan(config)

        assert output.exists()
        vocab, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 3
        assert run_info["files_excluded"] == 0
        assert run_info["clonescout_version"] == "2026.05"
        assert "hostname" in run_info
        assert "timestamp" in run_info

        folder_parent = root.parent.relative_to("/").as_posix()
        fp_idx = vocab[folder_parent]
        fn_idx = vocab["scanme"]
        sf_idx = vocab[".txt"]
        stem_idx = vocab["a"]
        leaf = metadata["test-node"][0][fp_idx][fn_idx][sf_idx][stem_idx]
        assert leaf == ("TXT", len("hello"), leaf[2])
        assert isinstance(leaf[2], int)

    def test_file_at_root_level(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "top.txt").write_text("a" * 10)

        output = tmp_path / "out.zip"
        config = ScanConfig(node="test-node", root=[str(root)], output=str(output))
        run_scan(config)

        vocab, metadata, _ = read_zip(output)
        folder_parent = root.parent.relative_to("/").as_posix()
        leaf = metadata["test-node"][0][vocab[folder_parent]][vocab["scanme"]][
            vocab[".txt"]
        ][vocab["top"]]
        assert leaf[1] == 10


class TestRunScanArchive:
    def test_zip_archive(self, tmp_path: Path) -> None:
        archive = tmp_path / "test.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("docs/report.pdf", b"pdf content")
            zf.writestr("README.md", b"readme content")

        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node", root=[str(archive)], output=str(output)
        )
        run_scan(config)

        vocab, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2
        assert run_info["files_excluded"] == 0

        anchor_idx = vocab[archive.resolve().as_posix()]
        fn_idx = vocab["docs"]
        sf_idx = vocab[".pdf"]
        stem_idx = vocab["report"]
        leaf = metadata["test-node"][anchor_idx][vocab[""]][fn_idx][sf_idx][stem_idx]
        assert leaf[0] == "PDF"

    def test_tar_gz_archive(self, tmp_path: Path) -> None:
        archive = tmp_path / "test.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            _add_tar_member(tf, "docs/report.pdf", b"pdf content")
            _add_tar_member(tf, "README.md", b"readme content")

        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node", root=[str(archive)], output=str(output)
        )
        run_scan(config)

        vocab, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2

        anchor_idx = vocab[archive.resolve().as_posix()]
        fn_idx = vocab["docs"]
        sf_idx = vocab[".pdf"]
        stem_idx = vocab["report"]
        leaf = metadata["test-node"][anchor_idx][vocab[""]][fn_idx][sf_idx][stem_idx]
        assert leaf[0] == "PDF"


class TestMixedRoots:
    def test_dir_and_zip_contribute_records(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("hi")

        archive = tmp_path / "test.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("data/b.log", b"bytes")

        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node",
            root=[str(root), str(archive)],
            output=str(output),
        )
        run_scan(config)

        vocab, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2

        folder_parent = root.parent.relative_to("/").as_posix()
        leaf1 = metadata["test-node"][0][vocab[folder_parent]][vocab["scanme"]][
            vocab[".txt"]
        ][vocab["a"]]
        assert leaf1[0] == "TXT"

        anchor_idx = vocab[archive.resolve().as_posix()]
        leaf2 = metadata["test-node"][anchor_idx][vocab[""]][vocab["data"]][
            vocab[".log"]
        ][vocab["b"]]
        assert leaf2[0] == "LOG"


class TestSkip:
    def test_skip_excludes_subdirectory(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        keep_dir = root / "keep"
        skip_dir = root / "skip_me"
        keep_dir.mkdir(parents=True)
        skip_dir.mkdir(parents=True)
        (keep_dir / "a.txt").write_text("keep")
        (skip_dir / "b.txt").write_text("discard")
        (skip_dir / "sub").mkdir()
        (skip_dir / "sub" / "c.txt").write_text("discard")

        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node",
            root=[str(root)],
            output=str(output),
            skip=["skip_me"],
        )
        run_scan(config)

        _, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 1


class TestExclude:
    def test_exclude_pattern_filters_file(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        (root / "b.log").write_text("other")
        (root / "c.txt").write_text("more")

        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node",
            root=[str(root)],
            output=str(output),
            exclude=[re.compile(r"b\.log")],
        )
        run_scan(config)

        _, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2
        assert run_info["files_excluded"] == 1

        vocab, _, _ = read_zip(output)
        assert "b" not in vocab

    def test_exclude_matches_path_with_folder_components(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        sub = root / "nested"
        sub.mkdir(parents=True)
        (sub / "secret.txt").write_text("x")

        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node",
            root=[str(root)],
            output=str(output),
            exclude=[re.compile(r"nested/secret")],
        )
        run_scan(config)

        _, _, run_info = read_zip(output)
        assert run_info["files_scanned"] == 0
        assert run_info["files_excluded"] == 1


class TestForce:
    def test_force_false_raises_on_existing_output(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node", root=[str(root)], output=str(output), force=False
        )
        run_scan(config)

        with pytest.raises(SystemExit) as exc:
            run_scan(config)
        assert exc.value.code == EXIT_RUNTIME_ERROR

    def test_force_true_overwrites_existing_output(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        output = tmp_path / "out.zip"
        config = ScanConfig(
            node="test-node", root=[str(root)], output=str(output), force=True
        )
        run_scan(config)

        (root / "b.txt").write_text("more")
        run_scan(config)

        _, _, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2


class TestInvalidRoot:
    def test_nonexistent_root_exits_bad_args(self, tmp_path: Path) -> None:
        bad = tmp_path / "does_not_exist"
        config = ScanConfig(
            node="test-node", root=[str(bad)], output=str(tmp_path / "out.zip")
        )
        with pytest.raises(SystemExit) as exc:
            run_scan(config)
        assert exc.value.code == EXIT_BAD_ARGS

    def test_one_bad_among_good_exits_bad_args(self, tmp_path: Path) -> None:
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        bad = tmp_path / "ghost"

        config = ScanConfig(
            node="test-node",
            root=[str(root), str(bad)],
            output=str(tmp_path / "out.zip"),
        )
        with pytest.raises(SystemExit) as exc:
            run_scan(config)
        assert exc.value.code == EXIT_BAD_ARGS

    def test_regular_file_root_exits_bad_args(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("hello")
        config = ScanConfig(
            node="test-node", root=[str(f)], output=str(tmp_path / "out.zip")
        )
        with pytest.raises(SystemExit) as exc:
            run_scan(config)
        assert exc.value.code == EXIT_BAD_ARGS


def _add_tar_member(tf: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = 1234567890
    tf.addfile(info, io.BytesIO(data))
