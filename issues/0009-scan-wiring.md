# feat: implement `run_scan` in `src/clonescout/commands/scan.py`

## Context

This is the third and final issue implementing the `scan` command.
It creates `src/clonescout/commands/scan.py` with `run_scan()`, which connects
all previously built pieces together.

`cli.py` already contains the dispatch:

```python
def cmd_scan(config: ScanConfig) -> None:
    from clonescout.commands.scan import run_scan
    run_scan(config)
```

No changes to `cli.py` are needed.

**Prerequisite:** Issues 1 and 2 (data layer and scanners) must be merged first.

The full specification lives in `docs/blueprints/scan-blueprint.md`.
Read `AGENTS.md` and `PROJECT.md` before starting.

---

## Deliverable

### `run_scan(config: ScanConfig) -> None`

#### 1. Validate all roots

For each path string in `config.root`, call `classify_path(Path(root))`.
Collect the results. If **any** root produces `"NONEXISTENT"`, `"UNSUPPORTED"`,
or `"FILE"`, print an error message to stderr for each offending root and exit
with code `EXIT_BAD_ARGS` (1). All roots are checked before exiting — report all
errors at once, not just the first.

#### 2. Initialise storage

```python
vocabulary = init_vocabulary()
reset_counters()
metadata: dict = {}
```

#### 3. Instantiate scanners and chain them

```python
import itertools

scanners = []
for root, kind in zip(config.root, kinds):
    if kind == "DIR":
        scanners.append(FSScanner(Path(root), config))
    elif kind == "ZIP":
        scanners.append(ZipScanner(Path(root), config))
    elif kind == "TAR":
        scanners.append(TarScanner(Path(root), config))

records: Iterator[FileRecord] = itertools.chain(*scanners)
```

#### 4. Apply exclude patterns and insert records

For each `FileRecord` from the chained iterator:

Build the candidate path string:
```python
candidate = f"{record.folder_parent}/{record.folder_name}/{record.stem}{record.suffix}"
```

If any pattern in `config.exclude` matches (`pattern.search(candidate)`):
- increment `files_excluded`
- `logging.debug("Excluded: %s", candidate)`
- continue

Otherwise call `insert_record(metadata, vocabulary, config.node, record)` and increment
`files_scanned`.

#### 5. Build `run_info` and write ZIP

```python
import socket
from datetime import datetime, timezone

now = datetime.now(tz=timezone.utc).astimezone()
run_info = {
    "clonescout_version": CLONESCOUT_VERSION,
    "timestamp": now.isoformat(),
    "hostname": socket.gethostname(),
    "roots": [str(Path(r).resolve()) for r in config.root],
    "files_scanned": files_scanned,
    "files_excluded": files_excluded,
}

try:
    write_zip(Path(config.output), vocabulary, metadata, run_info, force=config.force)
except FileExistsError:
    print(
        f"error: output file already exists: {config.output} (use --force to overwrite)",
        file=sys.stderr,
    )
    raise SystemExit(EXIT_RUNTIME_ERROR)
```

`EXIT_BAD_ARGS` (1), `EXIT_RUNTIME_ERROR` (2), and `CLONESCOUT_VERSION` come from
`constants.py`.

---

## Tests

### `tests/integration/test_cmd_scan.py`

Build real directory trees and archives in `tmp_path`. Call `run_scan(config)`
directly (do not invoke via subprocess).

- **Happy path — directory:** scan a small tree, verify the output ZIP exists,
  read it back with `read_zip`, assert `run_info["files_scanned"]` matches the
  number of files created, and spot-check one record's fields in the metadata dict.

- **Happy path — ZIP archive:** same as above but with a `.zip` root.

- **Happy path — tar.gz archive:** same as above but with a `.tar.gz` root.

- **Mixed roots:** one directory root and one ZIP root in the same scan; assert
  both contribute records to the metadata.

- **skip:** create a tree with a subdirectory named `skip_me`; pass
  `config.skip = ["skip_me"]`; assert no records from that subtree appear

- **exclude:** pass a pattern that matches one file by name; assert that file is
  absent from metadata and `run_info["files_excluded"]` is 1.

- **force=False:** run scan once successfully, run again without `--force`, assert
  `SystemExit` with code `EXIT_RUNTIME_ERROR` is raised.

- **force=True:** same setup, second run with `force=True`, assert it succeeds.

- **Invalid root:** pass a nonexistent path as root, assert `SystemExit` with
  code `EXIT_BAD_ARGS` is raised.

---

## Out of scope for this issue

- `cmd_merge` and `cmd_report` — separate issues.

---

## Definition of done

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/
.venv/bin/python -m pytest tests/ -v
```

All three pass clean.