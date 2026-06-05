"""Orchestration for the report command — read a metadata ZIP and produce a Markdown report."""

from __future__ import annotations

import logging
import sys
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

from clonescout.analysis import build_folders, find_duplicates, signature_fabric
from clonescout.constants import (
    EXIT_RUNTIME_ERROR,
    LSH_BAND_SIZE,
    LSH_NUM_BANDS,
    LSH_SEED,
    TIER_COMPONENTS,
    TIER_ORDER,
    TIER_THRESHOLDS,
)
from clonescout.report import format_report
from clonescout.storage import read_zip

if TYPE_CHECKING:
    from clonescout.config import ReportConfig


def run_report(config: ReportConfig) -> None:
    """Orchestrate the report command.

    Reads a metadata ZIP, materialises FolderRecords, runs tiered duplicate
    detection and writes a human-readable Markdown report.

    Args:
        config: Fully validated report configuration.

    Raises:
        SystemExit: On missing/ corrupt input, or existing output with force=False.
    """
    input_path = Path(config.input)

    try:
        vocabulary, metadata, _ = read_zip(input_path)
    except FileNotFoundError:
        print(f"error: input file not found: {config.input}", file=sys.stderr)
        raise SystemExit(EXIT_RUNTIME_ERROR)
    except zipfile.BadZipFile:
        print(f"error: input file is not a valid ZIP: {config.input}", file=sys.stderr)
        raise SystemExit(EXIT_RUNTIME_ERROR)

    folders = build_folders(vocabulary.as_list(), metadata)
    logging.info("Materialised %d folders", len(folders))

    get_sig = signature_fabric(
        num_bands=LSH_NUM_BANDS,
        band_size=LSH_BAND_SIZE,
        seed=LSH_SEED,
    )

    matches = find_duplicates(
        folders,
        TIER_COMPONENTS,
        TIER_ORDER,
        TIER_THRESHOLDS,
        get_sig,
    )
    logging.info("Found %d duplicate pairs", len(matches))

    if not matches:
        logging.info("No duplicate folders found")
        return

    text = format_report(matches, folders)

    if config.output is None:
        sys.stdout.write(text + "\n")
    else:
        output_path = Path(config.output)
        if output_path.exists() and not config.force:
            print(
                f"error: output file already exists: {config.output}",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_RUNTIME_ERROR)
        output_path.write_text(text + "\n")
