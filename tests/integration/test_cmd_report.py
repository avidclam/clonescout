"""Integration tests for the report command — run_report()."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from clonescout.commands.report import run_report
from clonescout.config import ReportConfig
from clonescout.constants import EXIT_RUNTIME_ERROR
from clonescout.storage import Vocabulary, write_zip
from tests.conftest import SMOKE_METADATA, SMOKE_VOCAB

if TYPE_CHECKING:
    from typing import Any


def _make_report_zip(
    path: Path,
    vocab_list: list[str] | None = None,
    metadata: dict[Any, Any] | None = None,
) -> None:
    """Write a metadata ZIP from the given vocab list and metadata dict."""
    vocab = Vocabulary.from_list(vocab_list if vocab_list is not None else SMOKE_VOCAB)
    meta = metadata if metadata is not None else SMOKE_METADATA
    run_info: dict[str, Any] = {"clonescout_version": "2026.05"}
    write_zip(path, vocab, meta, run_info, force=False)


class TestReportToStdout:
    def test_output_contains_expected_content(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "data.zip"
        _make_report_zip(zip_path)

        config = ReportConfig(input=str(zip_path), output=None)
        captured = StringIO()
        original = sys.stdout
        sys.stdout = captured
        try:
            run_report(config)
        finally:
            sys.stdout = original

        output = captured.getvalue()
        assert "## Tier: T3" in output
        assert "linux:/smoke/backup/photos/2021_copy" in output
        assert "windows:C:/smoke/Users/alice/photos/2021" in output


class TestReportToFile:
    def test_creates_file_with_content(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "data.zip"
        output_path = tmp_path / "report.md"
        _make_report_zip(zip_path)

        config = ReportConfig(input=str(zip_path), output=str(output_path))
        run_report(config)

        assert output_path.exists()
        text = output_path.read_text()
        assert "## Tier: T3" in text
        assert "Jaccard:" in text


class TestForce:
    def test_force_false_raises_on_existing_output(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "data.zip"
        output_path = tmp_path / "report.md"
        _make_report_zip(zip_path)

        config = ReportConfig(input=str(zip_path), output=str(output_path), force=False)
        run_report(config)

        with pytest.raises(SystemExit) as exc:
            run_report(config)
        assert exc.value.code == EXIT_RUNTIME_ERROR

    def test_force_true_overwrites(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "data.zip"
        output_path = tmp_path / "report.md"
        _make_report_zip(zip_path)

        config = ReportConfig(input=str(zip_path), output=str(output_path), force=True)
        run_report(config)
        mtime_first = output_path.stat().st_mtime

        run_report(config)
        mtime_second = output_path.stat().st_mtime

        assert mtime_second >= mtime_first


class TestNoDuplicates:
    def test_exits_cleanly_without_output(self, tmp_path: Path) -> None:
        vocab: list[str] = ["", "A:", "B:", "C:", "D:", "E:", "F:", "G:",
                             "H:", "I:", "J:", "K:", "L:", "M:", "N:", "O:",
                             "P:", "Q:", "R:", "S:", "T:", "U:", "V:", "W:",
                             "X:", "Y:", "Z:", "docs"]
        metadata: dict[Any, Any] = {
            "host-a": {0: {27: {27: {27: {27: ("TXT", 100, 1234567890)}}}}}
        }
        zip_path = tmp_path / "data.zip"
        output_path = tmp_path / "report.md"

        vocabulary = Vocabulary.from_list(vocab)
        write_zip(zip_path, vocabulary, metadata, {"clonescout_version": "2026.05"}, force=False)

        config = ReportConfig(input=str(zip_path), output=str(output_path))
        run_report(config)

        assert not output_path.exists()


class TestBadInput:
    def test_non_zip_file_raises_system_exit(self, tmp_path: Path) -> None:
        not_zip = tmp_path / "not.zip"
        not_zip.write_text("not a zip file")

        config = ReportConfig(input=str(not_zip))
        with pytest.raises(SystemExit) as exc:
            run_report(config)
        assert exc.value.code == EXIT_RUNTIME_ERROR

    def test_missing_input_raises_system_exit(self, tmp_path: Path) -> None:
        config = ReportConfig(input=str(Path("/nonexistent/path.zip")))
        with pytest.raises(SystemExit) as exc:
            run_report(config)
        assert exc.value.code == EXIT_RUNTIME_ERROR
