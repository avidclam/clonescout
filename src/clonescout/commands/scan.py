from __future__ import annotations

import itertools
import logging
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clonescout.archive import TarScanner, ZipScanner
from clonescout.constants import CLONESCOUT_VERSION, EXIT_BAD_ARGS, EXIT_RUNTIME_ERROR
from clonescout.scanner import BaseScanner, FSScanner, classify_path
from clonescout.storage import init_vocab, insert_record, reset_counters, write_zip

if TYPE_CHECKING:
    from clonescout.config import ScanConfig


def run_scan(config: ScanConfig) -> None:
    """Orchestrate the scan command.

    Args:
        config: Fully validated scan configuration.
    """
    kinds = [classify_path(Path(r)) for r in config.root]

    bad = [
        (r, k)
        for r, k in zip(config.root, kinds)
        if k in ("NONEXISTENT", "UNSUPPORTED", "FILE")
    ]
    if bad:
        for root, kind in bad:
            print(f"error: root {root}: {kind}", file=sys.stderr)
        raise SystemExit(EXIT_BAD_ARGS)

    vocab = init_vocab()
    reset_counters()
    metadata: dict[Any, Any] = {}

    scanners: list[BaseScanner] = []
    for root, kind in zip(config.root, kinds):
        if kind == "DIR":
            scanners.append(FSScanner(Path(root), config))
        elif kind == "ZIP":
            scanners.append(ZipScanner(Path(root), config))
        elif kind == "TAR":
            scanners.append(TarScanner(Path(root), config))

    records = itertools.chain(*scanners)

    files_scanned = 0
    files_excluded = 0

    for record in records:
        name = f"{record.stem}{record.suffix}"
        components = [p for p in (record.folder_parent, record.folder_name, name) if p]
        candidate = "/".join(components)

        if any(p.search(candidate) for p in config.exclude):
            files_excluded += 1
            logging.debug("Excluded: %s", candidate)
            continue

        insert_record(metadata, vocab, config.node, record)
        files_scanned += 1

    now = datetime.now(tz=UTC).astimezone()
    run_info = {
        "clonescout_version": CLONESCOUT_VERSION,
        "timestamp": now.isoformat(),
        "hostname": socket.gethostname(),
        "roots": [str(Path(r).resolve()) for r in config.root],
        "files_scanned": files_scanned,
        "files_excluded": files_excluded,
    }

    try:
        write_zip(Path(config.output), vocab, metadata, run_info, force=config.force)
    except FileExistsError:
        print(
            f"error: output file already exists: {config.output}"
            " (use --force to overwrite)",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_RUNTIME_ERROR)
