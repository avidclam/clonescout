"""Integration tests for CLI and config working together."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from clonescout.cli import main
from clonescout.constants import EXIT_BAD_ARGS
from clonescout.models import FileRecord
from clonescout.storage import init_vocabulary, insert_record, reset_counters, write_zip

if TYPE_CHECKING:
    from pathlib import Path


class TestIntegration:
    def test_scalar_cli_overrides_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """CLI --node overrides TOML [scan] node."""
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        output = tmp_path / "out.zip"
        config_file = tmp_path / "clonescout.toml"
        config_file.write_text(
            f"[scan]\nroot = ['{root}']\noutput = '{output}'\nnode = 'config-node'\n"
        )
        main(["-c", str(config_file), "scan", "-n", "cli-node"])
        captured = capsys.readouterr()
        assert "error" not in captured.err.lower()
        assert output.exists()

    def test_list_cli_replaces_config(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """CLI --root replaces TOML root list entirely."""
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        output = tmp_path / "out.zip"
        config_file = tmp_path / "clonescout.toml"
        config_file.write_text(
            f"[scan]\nroot = ['/old1', '/old2']\noutput = '{output}'\n"
        )
        main(["-c", str(config_file), "scan", "-r", str(root)])
        captured = capsys.readouterr()
        assert "error" not in captured.err.lower()
        assert output.exists()

    def test_unknown_toml_key_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Unknown key in [scan] section exits with code 1 and suggests correction."""
        config_file = tmp_path / "clonescout.toml"
        config_file.write_text(
            "[scan]\nroot = ['/data']\noutput = 'out.zip'\nrrot = 'typo'\n"
        )
        with pytest.raises(SystemExit) as exc:
            main(["-c", str(config_file), "scan"])
        assert exc.value.code == EXIT_BAD_ARGS
        captured = capsys.readouterr()
        assert "unknown config key" in captured.err.lower()
        assert "did you mean 'root'" in captured.err

    def test_missing_config_file_default_is_ok(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No default clonescout.toml → proceed with CLI args and defaults."""
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        output = tmp_path / "out.zip"
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            main(["scan", "-r", str(root), "-o", str(output)])
            captured = capsys.readouterr()
            assert "error" not in captured.err.lower()
            assert output.exists()
        finally:
            os.chdir(old_cwd)

    def test_explicit_config_missing_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Explicit --config to nonexistent file exits with code 1."""
        nonexistent = tmp_path / "nonexistent.toml"
        with pytest.raises(SystemExit) as exc:
            main(["-c", str(nonexistent), "scan"])
        assert exc.value.code == EXIT_BAD_ARGS

    def test_scan_invalid_regex_in_cli_exits_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """CLI --exclude with invalid regex exits with code 1."""
        root = tmp_path / "scanme"
        root.mkdir()
        output = tmp_path / "out.zip"
        with pytest.raises(SystemExit) as exc:
            main(["scan", "-r", str(root), "-o", str(output), "-e", "[invalid"])
        assert exc.value.code == EXIT_BAD_ARGS

    def test_merge_fewer_than_two_inputs_exits_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Merge with only one input exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            main(["merge", "-i", "only_one.zip", "-o", "merged.zip"])
        assert exc.value.code == EXIT_BAD_ARGS

    def test_merge_with_two_inputs_works(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Merge with two inputs should not error."""
        zip_a = tmp_path / "a.zip"
        zip_b = tmp_path / "b.zip"
        output = tmp_path / "merged.zip"

        for path in (zip_a, zip_b):
            vocabulary = init_vocabulary()
            metadata: dict = {}
            reset_counters()
            insert_record(
                metadata, vocabulary, "test",
                FileRecord("", "", "", "f", ".txt", "TXT", 0, 0),
            )
            write_zip(path, vocabulary, metadata, {"clonescout_version": "1"}, force=False)

        main(["merge", "-i", str(zip_a), "-i", str(zip_b), "-o", str(output)])
        assert output.exists()

    def test_sample_config_prints_unchanged(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """sample config prints the full TOML file."""
        import importlib.resources

        main(["sample", "config"])
        captured = capsys.readouterr()
        expected = (
            importlib.resources.files("clonescout.data")
            .joinpath("sample_config.toml")
            .read_text()
        )
        assert captured.out == expected

    def test_sample_config_minimal_removes_comments(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """sample config --minimal strips comments and collapses blanks."""
        main(["sample", "config", "--minimal"])
        captured = capsys.readouterr()
        # No full-line comments
        assert "# Sample CloneScout" not in captured.out
        # No inline comments
        assert "# CLI flag:" not in captured.out
        # No runs of multiple blank lines
        assert "\n\n\n" not in captured.out

    def test_report_no_input_exits_1(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Report with no input exits with code 1."""
        with pytest.raises(SystemExit) as exc:
            main(["report"])
        assert exc.value.code == EXIT_BAD_ARGS
