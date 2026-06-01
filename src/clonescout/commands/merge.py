from __future__ import annotations

import logging
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clonescout.constants import CLONESCOUT_VERSION, EXIT_RUNTIME_ERROR
from clonescout.storage import (
    Vocabulary,
    merge_metadata,
    read_zip,
    write_merge_zip,
)

if TYPE_CHECKING:
    from clonescout.config import MergeConfig


def run_merge(config: MergeConfig) -> None:
    """Orchestrate the merge command.

    Args:
        config: Fully validated merge configuration.
    """
    vocabs: list[Vocabulary] = []
    metadatas: list[dict[Any, Any]] = []
    run_records: list[list[dict[str, Any]]] = []

    for input_path in config.input:
        path = Path(input_path)
        try:
            vocab, metadata, info = read_zip(path)
        except FileNotFoundError:
            print(f"error: input file not found: {input_path}", file=sys.stderr)
            raise SystemExit(EXIT_RUNTIME_ERROR)
        except zipfile.BadZipFile:
            print(f"error: not a valid ZIP file: {input_path}", file=sys.stderr)
            raise SystemExit(EXIT_RUNTIME_ERROR)

        vocabs.append(vocab)
        metadatas.append(metadata)

        if "runs" in info:
            run_records.append(info["runs"])
        elif info:
            run_records.append([info])
        else:
            run_records.append([])

    result = Vocabulary.merge(*vocabs)

    sources = [(meta, result.index_maps[i]) for i, meta in enumerate(metadatas)]
    merged_metadata = merge_metadata(sources)

    merge_doc: dict[str, Any] = {
        "merge_info": {
            "clonescout_version": CLONESCOUT_VERSION,
            "timestamp": datetime.now(tz=UTC).astimezone().isoformat(),
            "inputs": [str(Path(p).resolve()) for p in config.input],
        },
        "runs": [run for sublist in run_records for run in sublist],
    }

    try:
        write_merge_zip(
            Path(config.output),
            result.vocabulary,
            merged_metadata,
            merge_doc,
            force=config.force,
            indent=2 if config.verbosity == "DEBUG" else None,
        )
    except FileExistsError:
        print(
            f"error: output file already exists: {config.output}"
            " (use --force to overwrite)",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_RUNTIME_ERROR)

    logging.info(
        "Merge complete: %d inputs → %s", len(config.input), config.output
    )
