"""Unit tests for cli.py."""

from __future__ import annotations

import argparse
import re
import socket
import sys
import tempfile
from pathlib import Path

import pytest

from clonescout.cli import (
    _merge_overrides,
    _strip_comments,
    build_parser,
    main,
    setup_logging,
)
from clonescout.config import (
    BaseConfig,
    ConfigError,
    MergeConfig,
    ReportConfig,
    ScanConfig,
)
from clonescout.constants import EXIT_BAD_ARGS, EXIT_SUCCESS


class TestBuildParser:
    def test_no_args_produces_no_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        assert args.command is None

    def test_help_flag(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["--help"])
        assert exc.value.code == 0

    def test_global_config_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-c", "/path/to/config.toml"])
        assert args.config == Path("/path/to/config.toml")

    def test_force_flag_provided(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-f"])
        assert args.force is True

    def test_force_flag_absent(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        # _UNSET sentinel — not False, not None
        assert args.force is not True

    def test_verbosity_v(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-v"])
        assert args.verbosity == "INFO"

    def test_verbosity_vv(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-vv"])
        assert args.verbosity == "DEBUG"

    def test_verbosity_q(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["-q"])
        assert args.verbosity == "ERROR"

    def test_verbosity_absent(self) -> None:
        parser = build_parser()
        args = parser.parse_args([])
        # _UNSET sentinel
        assert args.verbosity is not "WARNING"

    def test_verbosity_mutually_exclusive(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["-v", "-q"])

    def test_scan_parser_sets_command(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["scan"])
        assert args.command == "scan"

    def test_scan_root_append(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["scan", "-r", "/a", "-r", "/b"])
        assert args.root == ["/a", "/b"]

    def test_scan_root_absent(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["scan"])
        assert args.root == []

    def test_scan_all_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "scan",
            "-n", "laptop",
            "-r", "/data",
            "-s", ".git",
            "-e", "test",
            "-o", "out.zip",
        ])
        assert args.node == "laptop"
        assert args.root == ["/data"]
        assert args.skip == [".git"]
        assert args.exclude == ["test"]
        assert args.output == "out.zip"

    def test_merge_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "merge",
            "-i", "a.zip",
            "-i", "b.zip",
            "-o", "merged.zip",
        ])
        assert args.command == "merge"
        assert args.input == ["a.zip", "b.zip"]
        assert args.output == "merged.zip"

    def test_report_parser(self) -> None:
        parser = build_parser()
        args = parser.parse_args([
            "report",
            "-i", "merged.zip",
            "-o", "report.md",
        ])
        assert args.command == "report"
        assert args.input == "merged.zip"
        assert args.output == "report.md"

    def test_sample_config(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sample", "config"])
        assert args.command == "sample"
        assert args.sample_command == "config"
        assert args.minimal is False

    def test_sample_config_minimal(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sample", "config", "--minimal"])
        assert args.sample_command == "config"
        assert args.minimal is True

    def test_sample_report(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["sample", "report"])
        assert args.command == "sample"
        assert args.sample_command == "report"


class TestSuggestingParser:
    def test_suggests_for_long_form_unknown_arg(self, capsys) -> None:  # type: ignore[no-untyped-def]
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["scan", "--rrot"])
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "unrecognized arguments" in captured.err
        assert "did you mean" in captured.err

    def test_no_suggest_for_short_form_unknown_arg(self, capsys) -> None:  # type: ignore[no-untyped-def]
        parser = build_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["scan", "-x"])
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "unrecognized arguments" in captured.err
        assert "did you mean" not in captured.err


class TestSetupLogging:
    def test_setup_logging_debug(self) -> None:
        import logging
        setup_logging("DEBUG")
        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_setup_logging_warning(self) -> None:
        import logging
        setup_logging("WARNING")
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_setup_logging_error(self) -> None:
        import logging
        setup_logging("ERROR")
        root = logging.getLogger()
        assert root.level == logging.ERROR


class TestMergeOverrides:
    def test_scalar_override_force(self) -> None:
        cfg = BaseConfig(force=False)
        ns = argparse.Namespace(force=True)
        _merge_overrides(cfg, ns)
        assert cfg.force is True

    def test_scalar_override_verbosity(self) -> None:
        cfg = BaseConfig(verbosity="WARNING")
        ns = argparse.Namespace(verbosity="DEBUG")
        _merge_overrides(cfg, ns)
        assert cfg.verbosity == "DEBUG"

    def test_force_not_provided_keeps_config(self) -> None:
        cfg = BaseConfig(force=True)
        ns = argparse.Namespace()
        _merge_overrides(cfg, ns)
        assert cfg.force is True

    def test_list_replaces_config_root(self) -> None:
        cfg = ScanConfig(root=["/old"], output="out.zip")
        ns = argparse.Namespace(root=["/new"])
        _merge_overrides(cfg, ns)
        assert cfg.root == ["/new"]

    def test_list_empty_keeps_config_root(self) -> None:
        cfg = ScanConfig(root=["/old"], output="out.zip")
        ns = argparse.Namespace(root=[])
        _merge_overrides(cfg, ns)
        assert cfg.root == ["/old"]

    def test_list_replaces_config_merge_input(self) -> None:
        cfg = MergeConfig(input=["a.zip", "b.zip"], output="out.zip")
        ns = argparse.Namespace(input=["c.zip", "d.zip", "e.zip"])
        _merge_overrides(cfg, ns)
        assert cfg.input == ["c.zip", "d.zip", "e.zip"]

    def test_cli_exclude_compiles_patterns(self) -> None:
        cfg = ScanConfig(root=["/tmp"], output="out.zip")
        ns = argparse.Namespace(exclude=["test.*"])
        _merge_overrides(cfg, ns)
        assert len(cfg.exclude) == 1
        assert isinstance(cfg.exclude[0], re.Pattern)

    def test_cli_invalid_exclude_raises(self) -> None:
        cfg = ScanConfig(root=["/tmp"], output="out.zip")
        ns = argparse.Namespace(exclude=["[invalid"])
        with pytest.raises(ConfigError, match="invalid regex"):
            _merge_overrides(cfg, ns)

    def test_post_merge_validation_empty_root(self) -> None:
        cfg = ScanConfig(root=[], output="out.zip")
        ns = argparse.Namespace(root=[])
        with pytest.raises(ConfigError, match="at least one root"):
            _merge_overrides(cfg, ns)

    def test_post_merge_validation_few_inputs(self) -> None:
        cfg = MergeConfig(input=["only_one"], output="out.zip")
        ns = argparse.Namespace(input=[])
        with pytest.raises(ConfigError, match="at least two input"):
            _merge_overrides(cfg, ns)

    def test_report_output_override(self) -> None:
        cfg = ReportConfig(input="merged.zip", output=None)
        ns = argparse.Namespace(output="custom.md")
        _merge_overrides(cfg, ns)
        assert cfg.output == "custom.md"


class TestStripComments:
    def test_removes_full_line_comments(self) -> None:
        text = "# comment\nkey = value\n"
        result = _strip_comments(text)
        assert "# comment" not in result
        assert "key = value" in result

    def test_removes_inline_comments(self) -> None:
        text = "key = value  # inline comment\n"
        result = _strip_comments(text)
        assert result.rstrip() == "key = value"

    def test_collapses_blank_lines(self) -> None:
        text = "key = value\n\n\n\nother = true\n"
        result = _strip_comments(text)
        assert "\n\n\n" not in result
        lines = result.split("\n")
        assert lines == ["key = value", "", "other = true", ""]

    def test_strips_trailing_blank_lines(self) -> None:
        text = "key = value\n\n\n"
        result = _strip_comments(text)
        assert result == "key = value\n"

    def test_strips_leading_blank_lines(self) -> None:
        text = "\n\n\nkey = value\n"
        result = _strip_comments(text)
        assert result == "key = value\n"

    def test_preserves_section_headers(self) -> None:
        text = "[scan]\nkey = value\n"
        result = _strip_comments(text)
        assert "[scan]" in result
        assert "key = value" in result

    def test_preserves_hash_in_double_quoted_value(self) -> None:
        text = 'name = "hello#world"\n'
        result = _strip_comments(text)
        assert 'name = "hello#world"' in result

    def test_preserves_hash_in_single_quoted_value(self) -> None:
        text = "name = 'hello#world'\n"
        result = _strip_comments(text)
        assert "name = 'hello#world'" in result

    def test_strips_trailing_comment_after_quoted_value(self) -> None:
        text = 'output = "file.zip" # trailing comment\n'
        result = _strip_comments(text)
        assert result.rstrip() == 'output = "file.zip"'

    def test_preserves_hash_in_array_value(self) -> None:
        text = 'exclude = ["(?i)/\\.tmp/", "color=#ff0000"]\n'
        result = _strip_comments(text)
        assert "color=#ff0000" in result

    def test_preserves_hash_in_value_with_trailing_comment(self) -> None:
        text = 'name = "hello#world" # comment\n'
        result = _strip_comments(text)
        assert 'name = "hello#world"' in result
        assert "# comment" not in result

    def test_handles_escaped_quote_in_double_quoted_value(self) -> None:
        text = 'pattern = "she said \\"hello#world\\"" # note\n'
        result = _strip_comments(text)
        assert 'hello#world' in result
        assert "# note" not in result

    def test_preserves_hash_after_escaped_backslash(self) -> None:
        text = 'value = "path\\\\#notacomment"\n'
        result = _strip_comments(text)
        assert "#notacomment" in result


class TestMain:
    def test_help_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as exc:
            main(["--help"])
        assert exc.value.code == 0

    def test_no_command_prints_help(self, capsys) -> None:  # type: ignore[no-untyped-def]
        main([])
        captured = capsys.readouterr()
        assert "usage:" in captured.out or "usage:" in captured.err

    def test_sample_config_prints_content(self, capsys) -> None:  # type: ignore[no-untyped-def]
        main(["sample", "config"])
        captured = capsys.readouterr()
        assert "force = true" in captured.out

    def test_sample_config_minimal_strips_comments(self, capsys) -> None:  # type: ignore[no-untyped-def]
        main(["sample", "config", "--minimal"])
        captured = capsys.readouterr()
        assert "# Sample CloneScout" not in captured.out
        assert "force = true" in captured.out

    def test_sample_report_prints_content(self, capsys) -> None:  # type: ignore[no-untyped-def]
        main(["sample", "report"])
        captured = capsys.readouterr()
        assert "Not implemented" in captured.out

    def test_scan_writes_output_zip(self, tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
        root = tmp_path / "scanme"
        root.mkdir()
        (root / "a.txt").write_text("data")
        output = tmp_path / "out.zip"
        main(["scan", "-r", str(root), "-o", str(output)])
        captured = capsys.readouterr()
        assert "error" not in captured.err.lower()
        assert output.exists()
