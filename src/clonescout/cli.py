"""CLI argument parsing and command dispatch for CloneScout."""

from __future__ import annotations

import argparse
import importlib.resources
import logging
import re
import sys
from pathlib import Path
from typing import Any, TypeVar

from clonescout.config import (
    BaseConfig,
    ConfigError,
    MergeConfig,
    ReportConfig,
    ScanConfig,
    _suggest,
    load_config,
)
from clonescout.constants import EXIT_BAD_ARGS

_UNSET: Any = object()

_P = TypeVar("_P", bound=argparse.ArgumentParser)


def _collect_option_strings(parser: argparse.ArgumentParser) -> set[str]:
    """Collect all option strings and command names from a parser and its subparsers."""
    strings: set[str] = set()
    for action in parser._actions:
        for opt in action.option_strings:
            strings.add(opt)
        if isinstance(action, argparse._SubParsersAction):
            for name in action.choices:
                strings.add(name)
                sub = action.choices[name]
                strings |= _collect_option_strings(sub)
    return strings


class _SuggestingParser(argparse.ArgumentParser):
    """ArgumentParser that suggests corrections for unrecognized arguments."""

    def error(self, message: str) -> None:  # type: ignore[override]
        if message.startswith("unrecognized arguments:"):
            bad = message[len("unrecognized arguments:"):].strip().split()[0]
            known = frozenset(_collect_option_strings(self))
            hint = ""
            if bad.startswith("--"):
                hint = _suggest(bad, known)
            if hint:
                message = f"unrecognized arguments: {bad}{hint}"
        super().error(message)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the top-level ArgumentParser."""
    parser = _SuggestingParser(
        prog="clonescout",
        description="Find duplicate and near-duplicate directories using filesystem metadata.",
    )

    parser.add_argument(
        "-c",
        "--config",
        dest="config",
        type=Path,
        default=None,
        help="Path to the TOML config file (default: clonescout.toml in CWD)",
    )
    parser.add_argument(
        "-f",
        "--force",
        dest="force",
        action="store_true",
        default=_UNSET,
        help="Overwrite existing output files",
    )

    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v",
        dest="verbosity",
        action="store_const",
        const="INFO",
        default=_UNSET,
        help="Set verbosity to INFO",
    )
    verbosity.add_argument(
        "-vv",
        dest="verbosity",
        action="store_const",
        const="DEBUG",
        default=_UNSET,
        help="Set verbosity to DEBUG",
    )
    verbosity.add_argument(
        "-q",
        dest="verbosity",
        action="store_const",
        const="ERROR",
        default=_UNSET,
        help="Set verbosity to ERROR (quiet)",
    )

    subparsers = parser.add_subparsers(dest="command", title="commands")

    _build_scan_subparser(subparsers)
    _build_merge_subparser(subparsers)
    _build_report_subparser(subparsers)
    _build_sample_subparser(subparsers)

    return parser


def _build_scan_subparser(
    subparsers: argparse._SubParsersAction[_P],
) -> None:
    scan = subparsers.add_parser("scan", help="Collect metadata, write ZIP")
    scan.add_argument(
        "-n",
        "--node",
        dest="node",
        default=_UNSET,
        help="Machine name for this scan (default: hostname)",
    )
    scan.add_argument(
        "-r",
        "--root",
        dest="root",
        action="append",
        default=[],
        help="Directory or archive to scan (repeatable)",
    )
    scan.add_argument(
        "-s",
        "--skip",
        dest="skip",
        action="append",
        default=[],
        help="Directory name to skip (repeatable)",
    )
    scan.add_argument(
        "-e",
        "--exclude",
        dest="exclude",
        action="append",
        default=[],
        help="Regex pattern to exclude paths (repeatable)",
    )
    scan.add_argument(
        "-o",
        "--output",
        dest="output",
        default=_UNSET,
        help="Output ZIP file path",
    )


def _build_merge_subparser(
    subparsers: argparse._SubParsersAction[_P],
) -> None:
    merge = subparsers.add_parser("merge", help="Merge metadata ZIPs")
    merge.add_argument(
        "-i",
        "--input",
        dest="input",
        action="append",
        default=[],
        help="Metadata ZIP to merge (repeatable)",
    )
    merge.add_argument(
        "-o",
        "--output",
        dest="output",
        default=_UNSET,
        help="Output merged ZIP file path",
    )


def _build_report_subparser(
    subparsers: argparse._SubParsersAction[_P],
) -> None:
    report = subparsers.add_parser("report", help="Analyze and report duplicates")
    report.add_argument(
        "-i",
        "--input",
        dest="input",
        default=_UNSET,
        help="Input metadata ZIP file",
    )
    report.add_argument(
        "-o",
        "--output",
        dest="output",
        default=_UNSET,
        help="Output Markdown report path (default: stdout)",
    )


def _build_sample_subparser(
    subparsers: argparse._SubParsersAction[_P],
) -> None:
    sample = subparsers.add_parser(
        "sample", help="Print sample output (config or report)"
    )
    sample_subs = sample.add_subparsers(dest="sample_command", title="sample commands")

    config_parser = sample_subs.add_parser(
        "config", help="Print sample configuration file"
    )
    config_parser.add_argument(
        "--minimal",
        action="store_true",
        default=False,
        help="Strip comments and collapse blank lines",
    )

    sample_subs.add_parser("report", help="Print sample Markdown report")


def setup_logging(verbosity: str) -> None:
    """Configure logging to stderr with the given verbosity level."""
    level_map: dict[str, int] = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    level = level_map.get(verbosity, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
        force=True,
    )


def _merge_overrides(config: BaseConfig, args: argparse.Namespace) -> None:
    """Apply CLI overrides to *config* in-place, then re-validate."""
    force: Any = getattr(args, "force", _UNSET)
    if force is not _UNSET:
        config.force = force

    verbosity: Any = getattr(args, "verbosity", _UNSET)
    if verbosity is not _UNSET:
        config.verbosity = verbosity

    if isinstance(config, ScanConfig):
        _merge_scan_overrides(config, args)
    elif isinstance(config, MergeConfig):
        _merge_merge_overrides(config, args)
    elif isinstance(config, ReportConfig):
        _merge_report_overrides(config, args)

    config._validate()
    config._validate_completeness()


def _merge_scan_overrides(config: ScanConfig, args: argparse.Namespace) -> None:
    node: Any = getattr(args, "node", _UNSET)
    if node is not _UNSET:
        config.node = node

    roots: list[str] = getattr(args, "root", [])
    if roots:
        config.root = roots

    skips: list[str] = getattr(args, "skip", [])
    if skips:
        config.skip = skips

    excludes: list[str] = getattr(args, "exclude", [])
    if excludes:
        compiled: list[re.Pattern[str]] = []
        for pat in excludes:
            try:
                compiled.append(re.compile(pat))
            except re.error as exc:
                raise ConfigError(
                    f"invalid regex pattern '{pat}': {exc}"
                ) from exc
        config.exclude = compiled

    output: Any = getattr(args, "output", _UNSET)
    if output is not _UNSET:
        config.output = output


def _merge_merge_overrides(config: MergeConfig, args: argparse.Namespace) -> None:
    inputs: list[str] = getattr(args, "input", [])
    if inputs:
        config.input = inputs

    output: Any = getattr(args, "output", _UNSET)
    if output is not _UNSET:
        config.output = output


def _merge_report_overrides(config: ReportConfig, args: argparse.Namespace) -> None:
    input_val: Any = getattr(args, "input", _UNSET)
    if input_val is not _UNSET:
        config.input = input_val

    output_val: Any = getattr(args, "output", _UNSET)
    if output_val is not _UNSET:
        config.output = output_val


def main(argv: list[str] | None = None) -> None:
    """Entry point for the CloneScout CLI."""
    parser = build_parser()

    args = parser.parse_args(argv) if argv is not None else parser.parse_args()

    if not args.command:
        parser.print_help()
        print("\nTip: run 'clonescout sample config' to see a sample configuration file.")
        return

    config_path: Path | None = getattr(args, "config", None)

    try:
        config = load_config(config_path, args.command)
    except SystemExit:
        raise

    setup_logging(config.verbosity)

    try:
        _merge_overrides(config, args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_BAD_ARGS) from exc
    except SystemExit:
        raise

    setup_logging(config.verbosity)

    if config.verbosity == "DEBUG":
        logging.debug(repr(config))

    if args.command == "scan":
        assert isinstance(config, ScanConfig)
        cmd_scan(config)
    elif args.command == "merge":
        assert isinstance(config, MergeConfig)
        cmd_merge(config)
    elif args.command == "report":
        assert isinstance(config, ReportConfig)
        cmd_report(config)
    elif args.command == "sample":
        cmd_sample(args)


def cmd_scan(config: ScanConfig) -> None:
    """Scan directories and produce a metadata ZIP."""
    print("Not implemented.", file=sys.stderr)


def cmd_merge(config: MergeConfig) -> None:
    """Merge multiple metadata ZIPs into one."""
    print("Not implemented.", file=sys.stderr)


def cmd_report(config: ReportConfig) -> None:
    """Analyze metadata and produce a Markdown duplicate report."""
    print("Not implemented.", file=sys.stderr)


def cmd_sample(args: argparse.Namespace) -> None:
    """Handle the 'sample' command and its subcommands."""
    subcmd: str | None = getattr(args, "sample_command", None)

    if subcmd == "config":
        _cmd_sample_config(args)
    elif subcmd == "report":
        _cmd_sample_report()
    else:
        print("error: 'sample' requires a subcommand: config or report", file=sys.stderr)
        raise SystemExit(EXIT_BAD_ARGS)


def _cmd_sample_config(args: argparse.Namespace) -> None:
    """Print the sample configuration file."""
    minimal: bool = getattr(args, "minimal", False)

    data_dir = importlib.resources.files("clonescout.data")
    text = data_dir.joinpath("sample_config.toml").read_text()

    if minimal:
        text = _strip_comments(text)

    sys.stdout.write(text)


def _cmd_sample_report() -> None:
    """Print the sample Markdown report."""
    data_dir = importlib.resources.files("clonescout.data")
    text = data_dir.joinpath("sample_report.md").read_text()
    sys.stdout.write(text)


def _strip_comments(text: str) -> str:
    """Strip comments from TOML text and collapse blank lines.

    Removes:
    - Full-line comments (lines where # is the first non-whitespace character).
    - Inline comments (trailing # … on a key = value line).
    - Collapses runs of blank lines into a single blank line.
    """
    lines = text.split("\n")
    result: list[str] = []
    prev_blank = False

    for line in lines:
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            if not prev_blank:
                result.append("")
                prev_blank = True
            continue
        if "#" in line:
            line = line.split("#", 1)[0].rstrip()
        result.append(line)
        prev_blank = False

    while result and result[-1] == "":
        result.pop()
    while result and result[0] == "":
        result.pop(0)

    return "\n".join(result) + "\n"
