"""TOML config loading and the Config class hierarchy for CloneScout."""

from __future__ import annotations

import re
import socket
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeAlias

from clonescout.constants import DEFAULT_CONFIG_FILENAME, EXIT_BAD_ARGS, VERBOSITY_LEVELS

_SectionDict: TypeAlias = dict[str, Any]

_TOP_KEYS = frozenset({"force", "verbosity"})
_SCAN_KEYS = frozenset({"node", "root", "skip", "exclude", "output"})
_MERGE_KEYS = frozenset({"input", "output"})
_REPORT_KEYS = frozenset({"input", "output"})

_SECTION_KEYS: dict[str, frozenset[str]] = {
    "scan": _SCAN_KEYS,
    "merge": _MERGE_KEYS,
    "report": _REPORT_KEYS,
}


class ConfigError(Exception):
    """Raised when configuration validation fails."""


def _levenshtein(a: str, b: str) -> int:
    """Return the Levenshtein edit distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(
                min(
                    prev[j + 1] + 1,
                    curr[j] + 1,
                    prev[j] + (ca != cb),
                )
            )
        prev = curr
    return prev[-1]


def _suggest(key: str, known: frozenset[str]) -> str:
    """Return a 'did you mean?' hint for an unknown key, or an empty string."""
    if not known:
        return ""
    closest = min(known, key=lambda k: _levenshtein(key.lower(), k.lower()))
    if _levenshtein(key.lower(), closest.lower()) <= 3:
        return f" — did you mean '{closest}'?"
    return ""


def _check_unknown_keys(
    section: _SectionDict,
    known: frozenset[str],
    section_label: str,
) -> None:
    """Raise ConfigError for any key in *section* that is not in *known*."""
    for key in section:
        if key not in known:
            hint = _suggest(key, known)
            raise ConfigError(f"unknown config key '{key}' in {section_label}{hint}")


def _resolve_config_path(explicit: Path | None) -> Path | None:
    """Resolve the config file path.

    Args:
        explicit: Explicit path from --config, or None.

    Returns:
        Resolved Path to the config file, or None if no file should be loaded.

    Raises:
        SystemExit: If *explicit* is given but the file does not exist.
    """
    if explicit is not None:
        if not explicit.exists():
            print(f"error: config file not found: {explicit}", file=sys.stderr)
            raise SystemExit(EXIT_BAD_ARGS)
        return explicit

    default = Path.cwd() / DEFAULT_CONFIG_FILENAME
    if default.exists():
        return default
    return None


def _parse_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML config file.

    Raises:
        SystemExit: On TOML syntax errors.
    """
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        print(f"error: invalid TOML in {path}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_BAD_ARGS) from exc


def _extract_globals(toml: dict[str, Any]) -> _SectionDict:
    """Extract and validate top-level (non-section) keys."""
    result: _SectionDict = {}

    for key in list(toml):
        if isinstance(toml[key], dict):
            continue
        if key not in _TOP_KEYS:
            hint = _suggest(key, _TOP_KEYS)
            raise ConfigError(f"unknown config key '{key}'{hint}")
        result[key] = toml[key]

    if "force" in result and not isinstance(result["force"], bool):
        raise ConfigError("config key 'force' must be a boolean")
    if "verbosity" in result and not isinstance(result["verbosity"], str):
        raise ConfigError("config key 'verbosity' must be a string")

    return result


def _compile_patterns(raw: list[str]) -> list[re.Pattern[str]]:
    """Compile a list of regex strings into compiled patterns.

    Raises:
        ConfigError: If any pattern is invalid.
    """
    compiled: list[re.Pattern[str]] = []
    for pat in raw:
        try:
            compiled.append(re.compile(pat))
        except re.error as exc:
            raise ConfigError(f"invalid regex pattern '{pat}': {exc}") from exc
    return compiled


@dataclass
class BaseConfig:
    """Common configuration shared by all commands."""

    force: bool = False
    verbosity: str = "WARNING"

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        """Validate base configuration fields."""
        if self.verbosity not in VERBOSITY_LEVELS:
            valid = ", ".join(sorted(VERBOSITY_LEVELS))
            raise ConfigError(
                f"invalid verbosity '{self.verbosity}' — must be one of: {valid}"
            )

    def _validate_completeness(self) -> None:
        """Check that all required fields are present (no-op for base)."""


@dataclass
class ScanConfig(BaseConfig):
    """Configuration for the 'scan' command."""

    node: str = ""
    root: list[str] = field(default_factory=list)
    skip: list[str] = field(default_factory=list)
    exclude: list[re.Pattern[str]] = field(default_factory=list)
    output: str = ""

    def _validate(self) -> None:
        super()._validate()
        if not self.node:
            self.node = socket.gethostname()

    def _validate_completeness(self) -> None:
        if not self.root:
            raise ConfigError("at least one root path is required")
        if not self.output:
            raise ConfigError("output path is required for scan")


@dataclass
class MergeConfig(BaseConfig):
    """Configuration for the 'merge' command."""

    input: list[str] = field(default_factory=list)
    output: str = ""

    def _validate_completeness(self) -> None:
        if len(self.input) < 2:
            raise ConfigError("at least two input paths are required for merge")
        if not self.output:
            raise ConfigError("output path is required for merge")


@dataclass
class ReportConfig(BaseConfig):
    """Configuration for the 'report' command."""

    input: str = ""
    output: str | None = None

    def _validate_completeness(self) -> None:
        if not self.input:
            raise ConfigError("input path is required for report")


def load_config(path: Path | None, command: str) -> BaseConfig:
    """Parse TOML config file and return the appropriate Config subclass.

    Args:
        path: Path to the TOML file from --config, or None.
        command: Active command name ('scan', 'merge', 'report').

    Returns:
        A fully populated and validated Config subclass instance.

    Raises:
        SystemExit(1): On unknown keys, type errors, or invalid values.
    """
    resolved = _resolve_config_path(path)

    globals_dict: _SectionDict = {}
    toml_data: dict[str, Any] = {}

    if resolved is not None:
        toml_data = _parse_toml(resolved)
        globals_dict = _extract_globals(toml_data)

    try:
        if command == "scan":
            return _build_scan(toml_data, globals_dict)
        if command == "merge":
            return _build_merge(toml_data, globals_dict)
        if command == "report":
            return _build_report(toml_data, globals_dict)
        # No command or unknown — return base with defaults
        return BaseConfig(**globals_dict)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_BAD_ARGS) from exc


def _build_scan(toml: dict[str, Any], globals_dict: _SectionDict) -> ScanConfig:
    section = toml.get("scan", {})
    if not isinstance(section, dict):
        raise ConfigError("[scan] must be a TOML table")
    _check_unknown_keys(section, _SCAN_KEYS, "[scan]")

    kwargs: dict[str, Any] = {**globals_dict}

    if "node" in section:
        if not isinstance(section["node"], str):
            raise ConfigError("config key 'node' in [scan] must be a string")
        kwargs["node"] = section["node"]

    if "root" in section:
        if not isinstance(section["root"], list) or not all(
            isinstance(v, str) for v in section["root"]
        ):
            raise ConfigError("config key 'root' in [scan] must be a list of strings")
        kwargs["root"] = section["root"]

    if "skip" in section:
        if not isinstance(section["skip"], list) or not all(
            isinstance(v, str) for v in section["skip"]
        ):
            raise ConfigError("config key 'skip' in [scan] must be a list of strings")
        kwargs["skip"] = section["skip"]

    if "exclude" in section:
        if not isinstance(section["exclude"], list) or not all(
            isinstance(v, str) for v in section["exclude"]
        ):
            raise ConfigError(
                "config key 'exclude' in [scan] must be a list of strings"
            )
        kwargs["exclude"] = _compile_patterns(section["exclude"])

    if "output" in section:
        if not isinstance(section["output"], str):
            raise ConfigError("config key 'output' in [scan] must be a string")
        kwargs["output"] = section["output"]

    return ScanConfig(**kwargs)


def _build_merge(toml: dict[str, Any], globals_dict: _SectionDict) -> MergeConfig:
    section = toml.get("merge", {})
    if not isinstance(section, dict):
        raise ConfigError("[merge] must be a TOML table")
    _check_unknown_keys(section, _MERGE_KEYS, "[merge]")

    kwargs: dict[str, Any] = {**globals_dict}

    if "input" in section:
        if not isinstance(section["input"], list) or not all(
            isinstance(v, str) for v in section["input"]
        ):
            raise ConfigError(
                "config key 'input' in [merge] must be a list of strings"
            )
        kwargs["input"] = section["input"]

    if "output" in section:
        if not isinstance(section["output"], str):
            raise ConfigError("config key 'output' in [merge] must be a string")
        kwargs["output"] = section["output"]

    return MergeConfig(**kwargs)


def _build_report(toml: dict[str, Any], globals_dict: _SectionDict) -> ReportConfig:
    section = toml.get("report", {})
    if not isinstance(section, dict):
        raise ConfigError("[report] must be a TOML table")
    _check_unknown_keys(section, _REPORT_KEYS, "[report]")

    kwargs: dict[str, Any] = {**globals_dict}

    if "input" in section:
        if not isinstance(section["input"], str):
            raise ConfigError("config key 'input' in [report] must be a string")
        kwargs["input"] = section["input"]
    else:
        # Fallback to merge.output
        merge_section = toml.get("merge", {})
        if isinstance(merge_section, dict):
            fallback = merge_section.get("output", "")
            if fallback and isinstance(fallback, str):
                kwargs["input"] = fallback

    if "output" in section:
        if not isinstance(section["output"], str):
            raise ConfigError("config key 'output' in [report] must be a string")
        kwargs["output"] = section["output"]
    else:
        kwargs["output"] = None

    return ReportConfig(**kwargs)
