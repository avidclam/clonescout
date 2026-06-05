# feat: implement `report.py` — duplicate report formatting

## Context

This issue implements `src/clonescout/report.py`, which renders a
`list[MatchCandidate]` as a human-readable Markdown report.  The full logic
is in `analysis_snippet.py` (`format_report` and `_fmt_size`).

**Prerequisits:** 

- `MatchCandidate` must be present in `models.py`
- `analysis.py` does not need to be merged — `report.py` only depends on `models.py`

## Deliverables

### `src/clonescout/report.py`

#### `_fmt_size(n: int) -> str`

Private helper.  Formats a byte count as a human-readable string using binary
prefixes (1 KiB = 1024 bytes), analogous to `du -sh`:

- Below 1024 B: `"892 B"`
- 1024 B and above: one decimal place with unit suffix — `"1.5 MiB"`, `"3.2 GiB"`
- Units in ascending order: KiB, MiB, GiB, TiB

#### `format_report`

```python
def format_report(
    matches: list[MatchCandidate],
    folders: dict[str, FolderRecord],
) -> str:
```

Renders the report as a Markdown string.  Returns an empty string if `matches`
is empty.

Output structure:

```markdown
## Tier: T1

1. Shared: 10.0 KiB  Jaccard: 0.83
   linux:/smoke/backup/photos/2021_copy        15.5 KiB
   windows:C:/smoke/Users/alice/photos/2021    15.0 KiB

## Tier: T2

1. ...
```

Rules:

- Tiers appear as `## Tier: T1` headings, in the order they first appear in
  `matches` (normally T1, T2, T3).
- Pairs are numbered within each tier, in the order they arrive in `matches`
  (`find_duplicates` already sorted them by descending `shared_size`).
- Within each pair, `folder_id_a` is printed first — `run_tier` guarantees
  `folder_id_a <= folder_id_b` lexicographically.
- Jaccard is rounded to two decimal places.
- All sizes (shared, and per-folder total) are formatted with `_fmt_size`.
- A blank line separates the last entry of one tier from the next tier heading.

## Imports

```python
from clonescout.models import FolderRecord, MatchCandidate
```

No other project imports needed.

## Acceptance criteria

- `from clonescout.report import format_report` works without error.
- `format_report([], {})` returns `""`.
- `ruff`, `mypy`, `pytest` all pass (tests come in forthcoming issues).
