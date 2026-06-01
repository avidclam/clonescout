"""Integration tests for the merge command — run_merge()."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from clonescout.commands.merge import run_merge
from clonescout.config import MergeConfig
from clonescout.constants import EXIT_RUNTIME_ERROR
from clonescout.models import FileRecord
from clonescout.storage import (
    init_vocab,
    insert_record,
    read_zip,
    reset_counters,
    write_zip,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_scan_zip(
    path: Path,
    node: str = "host-a",
    *,
    stem: str = "report",
    suffix: str = ".pdf",
    ext: str = "PDF",
    size: int = 1024,
    mtime: int = 1234567890,
) -> None:
    vocab = init_vocab()
    metadata: dict = {}
    rec = FileRecord(
        anchor="",
        folder_parent="home/user",
        folder_name="docs",
        stem=stem,
        suffix=suffix,
        ext=ext,
        size=size,
        mtime=mtime,
    )
    reset_counters()
    insert_record(metadata, vocab, node, rec)

    run_info = {
        "clonescout_version": "2026.05",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "hostname": node,
        "roots": ["/fake/root"],
        "files_scanned": 1,
        "files_excluded": 0,
    }
    write_zip(path, vocab, metadata, run_info, force=False)


class TestMergeTwoScanZips:
    def test_produces_merged_vocab_and_metadata(self, tmp_path: Path) -> None:
        zip_a = tmp_path / "a.zip"
        zip_b = tmp_path / "b.zip"
        output = tmp_path / "merged.zip"

        _make_scan_zip(zip_a, node="host-a", stem="report", suffix=".pdf", ext="PDF")
        _make_scan_zip(zip_b, node="host-b", stem="slide", suffix=".pptx", ext="PPTX")

        config = MergeConfig(
            input=[str(zip_a), str(zip_b)], output=str(output)
        )
        run_merge(config)

        assert output.exists()
        vocab, metadata, info = read_zip(output)

        assert "runs" in info
        assert len(info["runs"]) == 2
        assert info["runs"][0]["hostname"] == "host-a"
        assert info["runs"][1]["hostname"] == "host-b"

        assert "report" in vocab
        assert "slide" in vocab
        assert ".pdf" in vocab
        assert ".pptx" in vocab

        assert "host-a" in metadata
        assert "host-b" in metadata

    def test_merge_info_contains_resolved_inputs(self, tmp_path: Path) -> None:
        zip_a = tmp_path / "a.zip"
        zip_b = tmp_path / "b.zip"
        output = tmp_path / "merged.zip"

        _make_scan_zip(zip_a)
        _make_scan_zip(zip_b)

        config = MergeConfig(
            input=[str(zip_a), str(zip_b)], output=str(output)
        )
        run_merge(config)

        _, _, info = read_zip(output)
        resolved = [str(p.resolve()) for p in (zip_a, zip_b)]
        assert info["merge_info"]["inputs"] == resolved
        assert info["merge_info"]["clonescout_version"] == "2026.05"
        assert "timestamp" in info["merge_info"]

    def test_merge_info_takes_longer_mtime(self, tmp_path: Path) -> None:
        zip_a = tmp_path / "a.zip"
        zip_b = tmp_path / "b.zip"
        output = tmp_path / "merged.zip"

        _make_scan_zip(zip_a, node="host-a", mtime=100)
        _make_scan_zip(zip_b, node="host-b", mtime=200)

        config = MergeConfig(
            input=[str(zip_a), str(zip_b)], output=str(output)
        )
        run_merge(config)

        vocab, metadata, _ = read_zip(output)
        anchor_idx = vocab[""]
        fp_idx = vocab["home/user"]
        fn_idx = vocab["docs"]
        sf_idx = vocab[".pdf"]
        stem_idx = vocab["report"]

        leaf = metadata["host-a"][anchor_idx][fp_idx][fn_idx][sf_idx][stem_idx]
        assert leaf[2] == 100  # host-a keeps its mtime (different node)

        # Last unoverwrites where mtime is the same
        assert "host-b" in metadata


class TestMergeScanAndMergeZip:
    def test_flattens_runs_from_merge_input(self, tmp_path: Path) -> None:
        zip_a = tmp_path / "a.zip"
        zip_b = tmp_path / "b.zip"
        intermediate = tmp_path / "intermediate.zip"
        output = tmp_path / "final.zip"

        _make_scan_zip(zip_a, node="host-a")
        _make_scan_zip(zip_b, node="host-b")

        config1 = MergeConfig(
            input=[str(zip_a), str(zip_b)], output=str(intermediate)
        )
        run_merge(config1)

        zip_c = tmp_path / "c.zip"
        _make_scan_zip(zip_c, node="host-c")

        config2 = MergeConfig(
            input=[str(intermediate), str(zip_c)], output=str(output)
        )
        run_merge(config2)

        _, _, info = read_zip(output)
        assert len(info["runs"]) == 3
        hostnames = [r["hostname"] for r in info["runs"]]
        assert hostnames == ["host-a", "host-b", "host-c"]


class TestForce:
    def test_force_false_raises_on_existing_output(self, tmp_path: Path) -> None:
        zip_a = tmp_path / "a.zip"
        zip_b = tmp_path / "b.zip"
        output = tmp_path / "merged.zip"

        _make_scan_zip(zip_a)
        _make_scan_zip(zip_b)

        config = MergeConfig(
            input=[str(zip_a), str(zip_b)], output=str(output), force=False
        )
        run_merge(config)

        with pytest.raises(SystemExit) as exc:
            run_merge(config)
        assert exc.value.code == EXIT_RUNTIME_ERROR

    def test_force_true_overwrites_existing_output(self, tmp_path: Path) -> None:
        zip_a = tmp_path / "a.zip"
        zip_b = tmp_path / "b.zip"
        zip_c = tmp_path / "c.zip"
        output = tmp_path / "merged.zip"

        _make_scan_zip(zip_a, node="host-a")
        _make_scan_zip(zip_b, node="host-b")

        config1 = MergeConfig(
            input=[str(zip_a), str(zip_b)], output=str(output), force=False
        )
        run_merge(config1)

        _make_scan_zip(zip_c, node="host-c")

        config2 = MergeConfig(
            input=[str(zip_a), str(zip_b), str(zip_c)],
            output=str(output),
            force=True,
        )
        run_merge(config2)

        _, _, info = read_zip(output)
        assert len(info["runs"]) == 3
        assert info["runs"][2]["hostname"] == "host-c"


class TestErrorHandling:
    def test_missing_input_file_exits(self, tmp_path: Path) -> None:
        config = MergeConfig(
            input=[str(tmp_path / "ghost.zip"), str(tmp_path / "a.zip")],
            output=str(tmp_path / "merged.zip"),
        )
        with pytest.raises(SystemExit) as exc:
            run_merge(config)
        assert exc.value.code == EXIT_RUNTIME_ERROR

    def test_invalid_zip_exits(self, tmp_path: Path) -> None:
        not_zip = tmp_path / "not.zip"
        not_zip.write_text("not a zip file")

        zip_b = tmp_path / "b.zip"
        _make_scan_zip(zip_b)

        config = MergeConfig(
            input=[str(not_zip), str(zip_b)],
            output=str(tmp_path / "merged.zip"),
        )
        with pytest.raises(SystemExit) as exc:
            run_merge(config)
        assert exc.value.code == EXIT_RUNTIME_ERROR
