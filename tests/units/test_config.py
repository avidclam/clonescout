"""Unit tests for config.py."""

from __future__ import annotations

import re
import socket
import tempfile
from pathlib import Path

import pytest

from clonescout.config import (
    BaseConfig,
    ConfigError,
    MergeConfig,
    ReportConfig,
    ScanConfig,
    _levenshtein,
    _suggest,
    load_config,
)
from clonescout.constants import EXIT_BAD_ARGS


class TestLevenshtein:
    def test_identical(self) -> None:
        assert _levenshtein("root", "root") == 0

    def test_one_insertion(self) -> None:
        assert _levenshtein("rrot", "root") == 1

    def test_one_substitution(self) -> None:
        assert _levenshtein("boot", "root") == 1

    def test_completely_different(self) -> None:
        assert _levenshtein("abc", "xyz") == 3

    def test_empty_string(self) -> None:
        assert _levenshtein("", "root") == 4
        assert _levenshtein("root", "") == 4


class TestBaseConfig:
    def test_defaults(self) -> None:
        cfg = BaseConfig()
        assert cfg.force is False
        assert cfg.verbosity == "WARNING"

    def test_custom_values(self) -> None:
        cfg = BaseConfig(force=True, verbosity="DEBUG")
        assert cfg.force is True
        assert cfg.verbosity == "DEBUG"

    def test_invalid_verbosity(self) -> None:
        with pytest.raises(ConfigError, match="invalid verbosity"):
            BaseConfig(verbosity="BLAH")


class TestScanConfig:
    def test_default_node_resolves_to_hostname(self) -> None:
        cfg = ScanConfig(root=["/tmp"], output="out.zip")
        assert cfg.node == socket.gethostname()

    def test_explicit_node_preserved(self) -> None:
        cfg = ScanConfig(node="laptop", root=["/tmp"], output="out.zip")
        assert cfg.node == "laptop"

    def test_empty_root_raises(self) -> None:
        cfg = ScanConfig(output="out.zip")
        cfg.root = []
        with pytest.raises(ConfigError, match="at least one root path"):
            cfg._validate_completeness()

    def test_empty_output_raises(self) -> None:
        cfg = ScanConfig(root=["/tmp"])
        cfg.output = ""
        with pytest.raises(ConfigError, match="output path is required"):
            cfg._validate_completeness()

    def test_valid_config(self) -> None:
        cfg = ScanConfig(root=["/tmp"], output="out.zip")
        assert cfg.root == ["/tmp"]
        assert cfg.output == "out.zip"
        assert cfg.skip == []
        assert cfg.exclude == []

    def test_exclude_patterns_are_compiled(self) -> None:
        cfg = ScanConfig(
            root=["/tmp"],
            output="out.zip",
            exclude=[re.compile(r"test")],
        )
        assert len(cfg.exclude) == 1
        assert isinstance(cfg.exclude[0], re.Pattern)
        assert cfg.exclude[0].pattern == "test"

    def test_skip_is_list(self) -> None:
        cfg = ScanConfig(
            root=["/tmp"],
            output="out.zip",
            skip=[".git", "__pycache__"],
        )
        assert cfg.skip == [".git", "__pycache__"]


class TestMergeConfig:
    def test_fewer_than_two_inputs_raises(self) -> None:
        cfg = MergeConfig(input=["only_one"], output="merged.zip")
        cfg.input = ["only_one"]
        with pytest.raises(ConfigError, match="at least two input"):
            cfg._validate_completeness()

    def test_empty_output_raises(self) -> None:
        cfg = MergeConfig(input=["a.zip", "b.zip"])
        cfg.output = ""
        with pytest.raises(ConfigError, match="output path is required"):
            cfg._validate_completeness()

    def test_valid_config(self) -> None:
        cfg = MergeConfig(input=["a.zip", "b.zip"], output="merged.zip")
        assert cfg.input == ["a.zip", "b.zip"]
        assert cfg.output == "merged.zip"


class TestReportConfig:
    def test_empty_input_raises(self) -> None:
        cfg = ReportConfig()
        with pytest.raises(ConfigError, match="input path is required"):
            cfg._validate_completeness()

    def test_output_can_be_none(self) -> None:
        cfg = ReportConfig(input="merged.zip", output=None)
        assert cfg.input == "merged.zip"
        assert cfg.output is None

    def test_output_can_be_string(self) -> None:
        cfg = ReportConfig(input="merged.zip", output="report.md")
        assert cfg.output == "report.md"


class TestLoadConfig:
    def _write_toml(self, content: str) -> Path:
        """Write *content* to a temp TOML file and return its path."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".toml", delete=False
        ) as tmp:
            tmp.write(content)
        return Path(tmp.name)

    def test_missing_explicit_path(self) -> None:
        with pytest.raises(SystemExit) as exc:
            load_config(Path("/nonexistent/config.toml"), "scan")
        assert exc.value.code == EXIT_BAD_ARGS

    def test_missing_default_file_returns_defaults(self, monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.chdir(tmp_path)
        cfg = load_config(None, "scan")
        assert isinstance(cfg, ScanConfig)
        # Without a config file, completeness is not validated here —
        # it will fail later in _merge_overrides if CLI doesn't provide required fields.
        assert cfg.root == []
        assert cfg.output == ""

    def test_unknown_top_level_key(self) -> None:
        path = self._write_toml("[scan]\nroot = ['/tmp']\noutput = 'out.zip'\nbadkey = 1\n")
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS

    def test_unknown_key_in_scan_section(self) -> None:
        path = self._write_toml("[scan]\nroot = ['/tmp']\noutput = 'out.zip'\nbadkey = 1\n")
        try:
            load_config(path, "scan")
        except SystemExit as exc:
            assert exc.code == EXIT_BAD_ARGS

    def test_scan_config_from_toml(self) -> None:
        path = self._write_toml(
            "force = true\nverbosity = 'DEBUG'\n"
            "[scan]\nnode = 'server'\nroot = ['/a', '/b']\n"
            "skip = ['.git']\nexclude = ['test.*']\noutput = 'scan.zip'\n"
        )
        cfg = load_config(path, "scan")
        assert isinstance(cfg, ScanConfig)
        assert cfg.force is True
        assert cfg.verbosity == "DEBUG"
        assert cfg.node == "server"
        assert cfg.root == ["/a", "/b"]
        assert cfg.skip == [".git"]
        assert len(cfg.exclude) == 1
        assert cfg.exclude[0].pattern == "test.*"
        assert cfg.output == "scan.zip"

    def test_merge_config_from_toml(self) -> None:
        path = self._write_toml(
            "[merge]\ninput = ['a.zip', 'b.zip']\noutput = 'merged.zip'\n"
        )
        cfg = load_config(path, "merge")
        assert isinstance(cfg, MergeConfig)
        assert cfg.input == ["a.zip", "b.zip"]
        assert cfg.output == "merged.zip"

    def test_report_input_falls_back_to_merge_output(self) -> None:
        path = self._write_toml(
            "[merge]\noutput = 'merged.zip'\n"
            "[report]\noutput = 'report.md'\n"
        )
        cfg = load_config(path, "report")
        assert isinstance(cfg, ReportConfig)
        assert cfg.input == "merged.zip"

    def test_report_explicit_input_overrides_fallback(self) -> None:
        path = self._write_toml(
            "[merge]\noutput = 'merged.zip'\n"
            "[report]\ninput = 'other.zip'\n"
        )
        cfg = load_config(path, "report")
        assert cfg.input == "other.zip"

    def test_report_no_input_and_no_merge_output_raises(self) -> None:
        # load_config returns a ReportConfig — completeness checked in _merge_overrides
        path = self._write_toml("[report]\n")
        cfg = load_config(path, "report")
        assert isinstance(cfg, ReportConfig)
        # without input and without merge.output, input is empty
        with pytest.raises(ConfigError, match="input path is required"):
            cfg._validate_completeness()

    def test_invalid_toml_syntax(self) -> None:
        path = self._write_toml("this is not valid toml = = =\n")
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS

    def test_root_wrong_type_in_toml(self) -> None:
        path = self._write_toml(
            "[scan]\nroot = 'not-a-list'\noutput = 'out.zip'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS

    def test_invalid_regex_in_exclude(self) -> None:
        path = self._write_toml(
            "[scan]\nroot = ['/tmp']\noutput = 'out.zip'\nexclude = ['[invalid'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS

    def test_unknown_section_with_typo(self, capsys) -> None:  # type: ignore[no-untyped-def]
        path = self._write_toml(
            "[scna]\nroot = ['/tmp']\noutput = 'out.zip'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS
        captured = capsys.readouterr()
        assert "unknown config section '[scna]'" in captured.err
        assert "did you mean '[scan]'?" in captured.err

    def test_unknown_section_no_suggestion(self, capsys) -> None:  # type: ignore[no-untyped-def]
        path = self._write_toml(
            "[bogus]\nkey = 'value'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS
        captured = capsys.readouterr()
        assert "unknown config section '[bogus]'" in captured.err
        assert "did you mean" not in captured.err

    def test_known_sections_accepted(self) -> None:
        path = self._write_toml(
            "[scan]\nroot = ['/tmp']\noutput = 'out.zip'\n"
            "[merge]\ninput = ['a.zip']\n"
            "[report]\ninput = 'm.zip'\n"
        )
        cfg = load_config(path, "scan")
        assert isinstance(cfg, ScanConfig)

    def test_known_section_irrelevant_to_command_accepted(self) -> None:
        path = self._write_toml(
            "[scan]\nroot = ['/tmp']\noutput = 'out.zip'\n"
            "[merge]\ninput = ['a.zip', 'b.zip']\noutput = 'm.zip'\n"
        )
        cfg = load_config(path, "scan")
        assert isinstance(cfg, ScanConfig)

    def test_no_command_returns_base_config(self) -> None:
        path = self._write_toml("force = true\n")
        cfg = load_config(path, "")
        assert isinstance(cfg, BaseConfig)
        assert cfg.force is True

    def test_suggests_for_toml_scan_typo(self, capsys) -> None:  # type: ignore[no-untyped-def]
        path = self._write_toml(
            "[scan]\nrrot = ['/tmp']\nroot = ['/tmp']\noutput = 'out.zip'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS
        captured = capsys.readouterr()
        assert "unknown config key 'rrot' in [scan]" in captured.err
        assert "did you mean 'root'" in captured.err

    def test_suggests_for_toml_merge_typo(self, capsys) -> None:  # type: ignore[no-untyped-def]
        path = self._write_toml(
            "[merge]\noutptu = 'merged.zip'\ninput = ['a.zip', 'b.zip']\noutput = 'merged.zip'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "merge")
        assert exc.value.code == EXIT_BAD_ARGS
        captured = capsys.readouterr()
        assert "unknown config key 'outptu' in [merge]" in captured.err
        assert "did you mean 'output'" in captured.err

    def test_suggest_long_form_key(self, capsys) -> None:  # type: ignore[no-untyped-def]
        path = self._write_toml(
            "[scan]\n--rrot = ['/tmp']\nroot = ['/tmp']\noutput = 'out.zip'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS
        captured = capsys.readouterr()
        assert "unknown config key" in captured.err.lower()
        assert "did you mean" in captured.err.lower()

    def test_toml_key_with_dash_gets_suggestion(self, capsys) -> None:  # type: ignore[no-untyped-def]
        path = self._write_toml(
            "[scan]\n-root = ['/tmp']\nroot = ['/tmp']\noutput = 'out.zip'\n"
        )
        with pytest.raises(SystemExit) as exc:
            load_config(path, "scan")
        assert exc.value.code == EXIT_BAD_ARGS
        captured = capsys.readouterr()
        assert "unknown config key" in captured.err.lower()
        assert "did you mean" in captured.err.lower()


class TestSuggest:
    def test_suggests_for_close_match(self) -> None:
        hint = _suggest("rrot", frozenset({"root", "node", "skip"}))
        assert "did you mean" in hint
        assert "root" in hint

    def test_no_suggest_for_distant_key(self) -> None:
        hint = _suggest("-x", frozenset({"root", "node", "skip"}))
        assert hint == ""

    def test_no_suggest_for_empty_known(self) -> None:
        hint = _suggest("rrot", frozenset())
        assert hint == ""

    def test_suggests_for_long_form_key(self) -> None:
        hint = _suggest("--rrot", frozenset({"root", "node", "skip"}))
        assert "did you mean" in hint
