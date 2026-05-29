# feat: pretty-print JSON with indent=2 when verbosity is DEBUG

## Problem

The scan output ZIP contains three JSON files (`vocab.json`, `metadata.json`,
`run.json`) all written with compact single-line formatting. When debugging a
scan, inspecting these files — especially `metadata.json` with its deeply nested
structure — is painful without pretty-printing.

## Fix

Add an `indent` parameter to `write_zip()` in `storage.py`. When `config.verbosity`
is `"DEBUG"`, the caller in `commands/scan.py` passes `indent=2`, producing
human-readable JSON inside the ZIP.

## Change

- `src/clonescout/storage.py` — `write_zip()` gains `indent: int | None = None`;
  all three `json.dumps()` calls forward the indent value.
- `src/clonescout/commands/scan.py` — call `write_zip()` with
  `indent=2 if config.verbosity == "DEBUG" else None`.

No changes to `read_zip()` — `json.loads()` accepts both formats.

## Out of scope

- `merge` and `report` commands — they produce their own output and are not
  affected by this change.

## Acceptance criteria

- Scan with default verbosity (`WARNING`) → compact JSON in ZIP (unchanged).
- Scan with `-vv` (DEBUG) → JSON in ZIP is indented with 2 spaces.
- `read_zip()` roundtrips both compact and indented output correctly.
- Ruff, mypy, pytest all pass.
