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
        vocabulary, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 3
        assert run_info["files_excluded"] == 0
        assert run_info["clonescout_version"] == "2026.05"
        assert "hostname" in run_info
        assert "timestamp" in run_info

        folder_parent = root.parent.relative_to("/").as_posix()
        fp_idx = vocabulary[folder_parent]
        fn_idx = vocabulary["scanme"]
        sf_idx = vocabulary[".txt"]
        stem_idx = vocabulary["a"]
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

        vocabulary, metadata, _ = read_zip(output)
        folder_parent = root.parent.relative_to("/").as_posix()
        leaf = metadata["test-node"][0][vocabulary[folder_parent]][vocabulary["scanme"]][
            vocabulary[".txt"]
        ][vocabulary["top"]]
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

        vocabulary, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2
        assert run_info["files_excluded"] == 0

        anchor_idx = vocabulary[archive.resolve().as_posix()]
        fn_idx = vocabulary["docs"]
        sf_idx = vocabulary[".pdf"]
        stem_idx = vocabulary["report"]
        leaf = metadata["test-node"][anchor_idx][vocabulary[""]][fn_idx][sf_idx][stem_idx]
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

        vocabulary, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2

        anchor_idx = vocabulary[archive.resolve().as_posix()]
        fn_idx = vocabulary["docs"]
        sf_idx = vocabulary[".pdf"]
        stem_idx = vocabulary["report"]
        leaf = metadata["test-node"][anchor_idx][vocabulary[""]][fn_idx][sf_idx][stem_idx]
        assert leaf[0] == "PDF"

    def test_zip_and_tar_produce_equivalent_metadata(self, tmp_path: Path) -> None:
        zip_archive = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_archive, "w") as zf:
            zf.writestr("docs/report.pdf", b"pdf content")
            zf.writestr("README.md", b"readme content")

        tar_archive = tmp_path / "test.tar.gz"
        with tarfile.open(tar_archive, "w:gz") as tf:
            _add_tar_member(tf, "./docs/report.pdf", b"pdf content")
            _add_tar_member(tf, "./README.md", b"readme content")

        zip_out = tmp_path / "zip_out.zip"
        zip_cfg = ScanConfig(
            node="test-node", root=[str(zip_archive)], output=str(zip_out)
        )
        run_scan(zip_cfg)

        tar_out = tmp_path / "tar_out.zip"
        tar_cfg = ScanConfig(
            node="test-node", root=[str(tar_archive)], output=str(tar_out)
        )
        run_scan(tar_cfg)

        zip_vocabulary, zip_meta, _ = read_zip(zip_out)
        tar_vocabulary, tar_meta, _ = read_zip(tar_out)

        for name in ("docs", "report", ".pdf", "README", ".md"):
            assert name in zip_vocabulary
            assert name in tar_vocabulary

        zip_anchor = zip_vocabulary[zip_archive.resolve().as_posix()]
        tar_anchor = tar_vocabulary[tar_archive.resolve().as_posix()]

        zip_leaf = zip_meta["test-node"][zip_anchor][zip_vocabulary[""]][
            zip_vocabulary["docs"]
        ][zip_vocabulary[".pdf"]][zip_vocabulary["report"]]
        tar_leaf = tar_meta["test-node"][tar_anchor][tar_vocabulary[""]][
            tar_vocabulary["docs"]
        ][tar_vocabulary[".pdf"]][tar_vocabulary["report"]]
        assert zip_leaf[0] == tar_leaf[0] == "PDF"
        assert zip_leaf[1] == tar_leaf[1] == len(b"pdf content")
        assert isinstance(zip_leaf[2], int)
        assert isinstance(tar_leaf[2], int)

        zip_leaf2 = zip_meta["test-node"][zip_anchor][zip_vocabulary[""]][
            zip_vocabulary[""]
        ][zip_vocabulary[".md"]][zip_vocabulary["README"]]
        tar_leaf2 = tar_meta["test-node"][tar_anchor][tar_vocabulary[""]][
            tar_vocabulary[""]
        ][tar_vocabulary[".md"]][tar_vocabulary["README"]]
        assert zip_leaf2[0] == tar_leaf2[0] == "MD"
        assert zip_leaf2[1] == tar_leaf2[1] == len(b"readme content")
        assert isinstance(zip_leaf2[2], int)
        assert isinstance(tar_leaf2[2], int)


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

        vocabulary, metadata, run_info = read_zip(output)
        assert run_info["files_scanned"] == 2

        folder_parent = root.parent.relative_to("/").as_posix()
        leaf1 = metadata["test-node"][0][vocabulary[folder_parent]][vocabulary["scanme"]][
            vocabulary[".txt"]
        ][vocabulary["a"]]
        assert leaf1[0] == "TXT"

        anchor_idx = vocabulary[archive.resolve().as_posix()]
        leaf2 = metadata["test-node"][anchor_idx][vocabulary[""]][vocabulary["data"]][
            vocabulary[".log"]
        ][vocabulary["b"]]
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

        vocabulary, _, _ = read_zip(output)
        assert "b" not in vocabulary

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
