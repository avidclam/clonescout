**refactor: extract command orchestration into `commands/` subpackage**

## Context

`cli.py` currently contains stub implementations of `cmd_scan`, `cmd_merge`, and
`cmd_report`. As the project grows, these functions will accumulate substantial
business logic (root validation, scanner instantiation, metadata assembly, ZIP
writing, etc.). Keeping that logic in `cli.py` — alongside argument parsing and
config merging — would make the file hard to read and test.

This refactoring establishes a clean boundary **before** any business logic is
written: `cli.py` owns the CLI surface; `commands/` owns the work.

## What to change

### 1. Create `src/clonescout/commands/` subpackage

```
src/clonescout/commands/
    __init__.py   # empty
    scan.py       # run_scan(config: ScanConfig) -> None
    merge.py      # run_merge(config: MergeConfig) -> None
    report.py     # run_report(config: ReportConfig) -> None
```

Each module contains a single public function that is a stub for now:

```python
# commands/scan.py
from clonescout.config import ScanConfig


def run_scan(config: ScanConfig) -> None:
    """Orchestrate the scan command.

    Args:
        config: Fully validated scan configuration.
    """
    print("Not implemented.", file=__import__("sys").stderr)
```

Same pattern for `run_merge` / `run_report` with their respective config types.

### 2. Update `cmd_scan`, `cmd_merge`, `cmd_report` in `cli.py`

Replace the current `print("Not implemented.", ...)` stubs with delegation calls:

```python
def cmd_scan(config: ScanConfig) -> None:
    """Scan directories and produce a metadata ZIP."""
    from clonescout.commands.scan import run_scan
    run_scan(config)


def cmd_merge(config: MergeConfig) -> None:
    """Merge multiple metadata ZIPs into one."""
    from clonescout.commands.merge import run_merge
    run_merge(config)


def cmd_report(config: ReportConfig) -> None:
    """Analyze metadata and produce a Markdown duplicate report."""
    from clonescout.commands.report import run_report
    run_report(config)
```

Local imports are intentional: they keep the top-level `cli.py` import surface
minimal and avoid circular-import risk as modules fill in.

### 3. `cmd_sample` — no change

`cmd_sample` is fully implemented, lightweight, and will not grow. It stays in
`cli.py` as-is.

## What NOT to change

- Argument parsing (`build_parser`, `_build_*_subparser` functions) — stays in `cli.py`.
- Config merging (`_merge_overrides` and helpers) — stays in `cli.py`.
- `main()`, `setup_logging()` — stays in `cli.py`.
- All existing tests must continue to pass without modification.

## Acceptance criteria

- [ ] `src/clonescout/commands/__init__.py` exists and is empty.
- [ ] `src/clonescout/commands/scan.py` exists with `run_scan(config: ScanConfig) -> None`.
- [ ] `src/clonescout/commands/merge.py` exists with `run_merge(config: MergeConfig) -> None`.
- [ ] `src/clonescout/commands/report.py` exists with `run_report(config: ReportConfig) -> None`.
- [ ] `cmd_scan`, `cmd_merge`, `cmd_report` in `cli.py` delegate to the above; no business logic remains in them.
- [ ] `cmd_sample` is unchanged.
- [ ] `ruff`, `mypy`, `pytest` all pass.
