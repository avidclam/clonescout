# Blueprint: Report Command — CloneScout

> Specification for `commands/report.py` and the report-formatting module
> `src/clonescout/report.py`.  Read alongside `PROJECT.md`, `AGENTS.md`,
> `analysis-blueprint.md`, `merge-blueprint.md`, and ADR 002 before
> implementing.

---

## Overview

The `report` command consumes a single metadata ZIP (produced by `scan`
or by `merge`), runs the tiered duplicate detection from `analysis.py`,
and writes a prioritised Markdown report to either stdout or a file.

Core flow:

```
config.input (path to a metadata ZIP)
  → read_zip(path)             → (vocab, metadata, info)
  → build_folders(vocab, metadata) → folders
  → signature_fabric(LSH_NUM_BANDS, LSH_BAND_SIZE, LSH_SEED) → get_signature
  → find_duplicates(folders, TIER_COMPONENTS, TIER_ORDER, TIER_THRESHOLDS, get_signature)
                                → list[MatchCandidate]
  → format_report_markdown(matches, folders, source_path) → str
  → write to config.output (or stdout if None)
```

---

## Module Responsibilities

| Module | Responsibility |
|---|---|
| `commands/report.py` | `run_report(config)` — orchestration: read ZIP, call into `analysis`, call into `report`, write output |
| `src/clonescout/report.py` | `format_report_markdown(...)` — pure function: matches + folders + source path → Markdown string. No I/O, no logging, no config. |
| `analysis.py` | `build_folders`, `signature_fabric`, `find_duplicates` (per `analysis-blueprint.md`) |
| `storage.py` | `read_zip` (per `merge-blueprint.md`) |
| `data/sample_report.md` | Static example of the report format, printed by `sample report` |

`report.py` does **not** call `read_zip`, write to disk, or know about
`ReportConfig`.  It is a pure formatter.  This keeps it trivially testable
and reusable.

`analysis.py` knows only what it needs to produce `MatchCandidate`s.
It does not see `info` or `source_path` — those are report-layer concerns.

`info` (the third value returned by `read_zip`) is currently used for
debugging only.  `run_report` keeps the binding so the data is not
lost if future debugging needs arise, but it is not rendered into
the report.

---

## Public API

### `report.py`

```python
def format_report_markdown(
    matches: list[MatchCandidate],
    folders: dict[str, FolderRecord],
    source_path: Path,
) -> str:
    """Render duplicate-detection results as a Markdown report.

    Args:
        matches: MatchCandidate instances from analysis.find_duplicates().
            Already grouped by tier (T1 first) and sorted by descending
            shared_size within each tier — find_duplicates guarantees this.
        folders: All FolderRecords from analysis.build_folders(), keyed by
            folder_id.  Used to look up each folder's total_size.
        source_path: Path of the input ZIP.  Echoed in the report header
            for traceability.

    Returns:
        A Markdown string.  Always non-empty: the header is always
        present, even when there are no matches.  No trailing newline
        beyond what Markdown rendering conventions require.
    """
```

### `commands/report.py`

```python
def run_report(config: ReportConfig) -> None:
    """Orchestrate the report command.

    Args:
        config: Fully validated report configuration.
    """
```

---

## Markdown Report Format

### Header (always present)

```markdown
# CloneScout Duplicate Report

| Field | Value |
|---|---|
| **Source** | `/path/to/merged.zip` |
| **Generated** | 2026-06-05T14:00:00+02:00 |
| **Folders analyzed** | 12 345 |
| **Matches found** | 27 |

## Tier thresholds

| Tier | Criterion | Jaccard ≥ |
|---|---|---|
| T1 | folder name + stem + ext + size | 0.80 |
| T2 | stem + ext + size + mtime | 0.70 |
| T3 | stem + ext + size | 0.60 |
```

- `Source` is `Path(config.input).resolve()`.
- `Generated` is the current local time in ISO 8601 with offset
  (`datetime.now(tz=UTC).astimezone().isoformat()`).
- `Folders analyzed` is `len(folders)`.
- `Matches found` is `len(matches)`.
- The thresholds table is informational and shows the constants from
  `analysis-blueprint.md`.  They are hardcoded, not from the input
  ZIP (ADR 002).

### Per-tier section (only if the tier has ≥ 1 match)

```markdown
## Tier: T3

### 1. Jaccard 0.83 · Shared 10.5 KiB

| Folder | Total size |
|---|---:|
| `linux:/smoke/backup/photos/2021_copy` | 12.0 KiB |
| `windows:C:/smoke/Users/alice/photos/2021` | 15.0 KiB |
```

#### Section heading

- `## Tier: T1` (T1 / T2 / T3 — no other text).
- The thresholds table in the header already documents what each tier
  matches on; the report does not repeat or interpret it.
- Tiers with zero matches are **omitted entirely** — no placeholder.

#### Per-match entry

- Numbered `1.`, `2.`, … within each tier (matches the sort order
  from `find_duplicates`, which is descending `shared_size`).
- Jaccard: two decimal places, e.g. `0.83`.
- Shared size: human-readable via `_fmt_size` (see "Helpers" below).
- A two-row Markdown table with the two folder paths (in backticks
  for monospace alignment) and each folder's `total_size`.
- Within each pair, `folder_id_a` is in the first row —
  `run_tier` guarantees `folder_id_a <= folder_id_b` lexicographically.

#### Tier separator

A blank line between matches, and a horizontal rule `---` between
tier sections.  Renders cleanly in GitHub-flavoured Markdown and
stays skimmable in raw form.

### Empty result

When `matches == []`, the report still has the header and the tier
thresholds table, plus a single line:

```markdown
## No duplicates detected.
```

Below the thresholds table.  This makes a zero-match output
self-explanatory when piped to a file or `less`.

---

## Helpers

### `_fmt_size(n: int) -> str`

Port of `_fmt_size` from `analysis_snippet.py` into `report.py`
(not exported publicly):

- `< 1024 B` → `"892 B"`
- `≥ 1024 B` → one decimal place + binary unit (`KiB`, `MiB`,
  `GiB`, `TiB`), e.g. `"1.5 MiB"`.

Both folders' `total_size` and the `shared_size` use this helper.

---

## `commands/report.py` — `run_report()`

### Step-by-step

1. **Read the input ZIP.**
   ```python
   try:
       vocab, metadata, info = read_zip(Path(config.input))
   except FileNotFoundError:
       print(f"error: input file not found: {config.input}", file=sys.stderr)
       raise SystemExit(EXIT_RUNTIME_ERROR)
   except zipfile.BadZipFile:
       print(f"error: not a valid ZIP file: {config.input}", file=sys.stderr)
       raise SystemExit(EXIT_RUNTIME_ERROR)
   ```

   `info` is bound but currently unused.  It is retained for future
   debugging needs (e.g. logging scan provenance at DEBUG) — do not
   drop the binding.

2. **Materialise folders.**
   ```python
   folders = build_folders(vocab, metadata)
   ```

3. **Construct the signature closure.**
   ```python
   get_signature = signature_fabric(
       num_bands=LSH_NUM_BANDS,
       band_size=LSH_BAND_SIZE,
       seed=LSH_SEED,
   )
   ```
   All three names live in `constants.py` (per ADR 002).

4. **Run tiered detection.**
   ```python
   matches = find_duplicates(
       folders,
       TIER_COMPONENTS,
       TIER_ORDER,
       TIER_THRESHOLDS,
       get_signature,
   )
   ```

5. **Format the report.**
   ```python
   text = format_report_markdown(
       matches,
       folders,
       Path(config.input).resolve(),
   )
   ```

6. **Write the report.**
   ```python
   if config.output is None:
       sys.stdout.write(text)
   else:
       out_path = Path(config.output)
       if out_path.exists() and not config.force:
           print(
               f"error: output file already exists: {out_path}"
               " (use --force to overwrite)",
               file=sys.stderr,
           )
           raise SystemExit(EXIT_RUNTIME_ERROR)
       out_path.write_text(text, encoding="utf-8")
   ```

7. **Log a summary.**
   ```python
   logging.info(
       "Report complete: %d folders, %d matches → %s",
       len(folders),
       len(matches),
       config.output or "stdout",
   )
   ```

### Exit codes

| Situation | Exit code |
|---|---|
| Success — matches found | `EXIT_SUCCESS` (0) |
| Success — no matches found | `EXIT_SUCCESS` (0) |
| Input file not found | `EXIT_RUNTIME_ERROR` (2) |
| Input file is not a valid ZIP | `EXIT_RUNTIME_ERROR` (2) |
| Output file exists and `force=False` | `EXIT_RUNTIME_ERROR` (2) |

No matches is **not** an error condition.  A clean report is a
successful run.

### Imports

```python
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
from clonescout.storage import read_zip

if TYPE_CHECKING:
    from clonescout.config import ReportConfig
```

`MatchCandidate` and `FolderRecord` are imported where used
inside `format_report_markdown` (type hints only).

---

## Constants to add to `constants.py`

```python
# LSH + MinHash parameters (per ADR 002 — not configurable).
LSH_NUM_BANDS: int = 15
LSH_BAND_SIZE: int = 8
LSH_SEED: int = 42

# Tier definitions for analysis.find_duplicates (per analysis-blueprint.md).
TIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "T1": ("folder_name", "stem", "ext", "size"),
    "T2": ("stem", "ext", "size", "mtime"),
    "T3": ("stem", "ext", "size"),
}
TIER_ORDER: list[str] = ["T1", "T2", "T3"]
TIER_THRESHOLDS: dict[str, float] = {"T1": 0.80, "T2": 0.70, "T3": 0.60}
```

These replace the in-snippet copies and become the single source of
truth.  The snippet keeps its own copies for standalone-run
diagnostics, as agreed.

---

## `data/sample_report.md`

This file is printed verbatim by `clonescout sample report`
(`cli.py:_cmd_sample_report`).  Replace the current placeholder with
a representative example matching the format above.  Use the same
fixture as the `__main__` block in `analysis_snippet.py` (the
windows/linux `photos/2021` case) as the basis for the sample data.

---

## Module layout

```
src/clonescout/
├── analysis.py        # build_folders, signature_fabric, find_duplicates (per analysis-blueprint)
├── report.py          # format_report_markdown (this blueprint, new)
└── commands/
    └── report.py      # run_report orchestration (this blueprint)
```

```
tests/
├── units/
│   ├── test_analysis.py    # build_folders, run_tier, find_duplicates (per analysis-blueprint)
│   └── test_report.py      # format_report_markdown: empty, single-tier, multi-tier, header
└── integration/
    └── test_cmd_report.py  # end-to-end: write a scan ZIP, run_report, assert Markdown output
```

---

## Testing notes

### `format_report_markdown` unit tests

- **Empty matches**: assert header is present, thresholds table is
  present, "No duplicates detected." line is present, no tier
  sections.
- **Single T1 match**: build one `MatchCandidate`, call
  `format_report_markdown`, assert the `## Tier: T1` heading, match
  numbering, Jaccard format (two decimals), shared size, both
  folder paths in backticks, both total sizes.
- **Multi-tier**: construct matches across all three tiers, assert
  T1 section appears before T2 before T3, tiers with zero matches
  are omitted, horizontal rules between tier sections.
- **Folder ID ordering**: `folder_id_a` is the lexicographically
  smaller of the two — verify that the table's first row is
  always `folder_id_a`.
- **Shared size formatting**: a pair with `shared_size = 15_360`
  renders as `"15.0 KiB"`.
- **No interpretation**: assert the tier heading is exactly
  `"## Tier: T1"` with no trailing blurb or interpretation text.

### `run_report` integration tests

- **Happy path — stdout**: write a scan ZIP to `tmp_path` via
  `write_zip`, call `run_report` with `output=None` (capture
  stdout); assert output contains the expected tier heading and at
  least one expected folder ID.
- **Happy path — file**: run with `output=<tmp_path/report.md>`;
  assert the file exists, is valid UTF-8, and contains the expected
  Markdown headings.
- **Force false**: run with an existing output file and
  `force=False`; assert `SystemExit(EXIT_RUNTIME_ERROR)`.
- **Force true**: same setup with `force=True`; assert success and
  file is overwritten.
- **No duplicates**: ZIP with a single folder; assert exit is clean
  and report contains "No duplicates detected.".
- **Missing input**: nonexistent path; assert `SystemExit` and
  error message on stderr.
- **Bad input**: non-ZIP file as input; assert `SystemExit`.

### `data/sample_report.md` test

- `clonescout sample report` prints the file contents verbatim.
  An integration test reads `data/sample_report.md`, invokes
  `cli.main(["sample", "report"])` capturing stdout, and asserts
  equality.
