# AGENTS — CloneScout

> Instructions for AI coding assistants working on this project.
> Read the full product spec at `PROJECT.md` before touching any module.

## Mission

CloneScout is a portable Python CLI tool that finds duplicate and near-duplicate
directories using only filesystem metadata — no file content reading. It scans
locally, stores metadata in portable archives, merges results from multiple
machines, and produces a tiered duplicate report.

## Tech Stack & Constraints

- **Python 3.11 exactly.** Zero external dependencies — standard library only.
- Permitted 3.11-specific: `tomllib`, `typing.Self / LiteralString / Never`, exception groups.
- **Forbidden (3.12+):** `itertools.batched`, PEP 695 type syntax, `pathlib.Path.walk` → use `os.walk`.

## Commands

All tooling runs from `.venv/` (Python 3.11 + dev deps):

```bash
.venv/bin/python -m ruff check src/ tests/  # lint (line-length 100, py311)
.venv/bin/python -m mypy src/               # type check (strict mode)
.venv/bin/python -m pytest tests/ -v        # test
.venv/bin/python scripts/build_zipapp.py    # build → dist/clonescout-YYYY.MM.pyz
```

Run in order: `lint` → `typecheck` → `test`.
Never install anything — the venv already exists and has all dependencies.

## Project Structure (planned — source modules do not yet exist)

```
├── src/clonescout/
│   ├── cli.py            # argparse: scan | merge | report | sample; dispatch only
│   ├── commands/
│   │   ├── __init__.py
│   │   ├── scan.py       # run_scan(config: ScanConfig) — scan orchestration
│   │   ├── merge.py      # run_merge(config: MergeConfig) — merge orchestration
│   │   └── report.py     # run_report(config: ReportConfig) — report orchestration
│   ├── scanner.py        # Recursive metadata collection (file system)
│   ├── archive.py        # .zip/.tar/.tar.gz reading without extraction
│   ├── storage.py        # Vocabulary + JSON + compressed pickle
│   ├── merge.py          # Cross-machine vocabulary merging
│   ├── analysis.py       # LSH + MinHash, tiered matching (T1→T2→T3)
│   ├── report.py         # Prioritized Markdown report
│   ├── config.py         # TOML config loading, defaults
│   ├── models.py         # Dataclasses: FileRecord, FolderRecord, MatchCandidate
│   └── constants.py      # Tier names, config keys, magic strings
├── tests/
│   ├── units/
│   └── integration/
├── snippets/             # Code fragments staged here before moving into src/
├── scripts/              # build_zipapp.py (not yet created)
├── docs/
│   ├── blueprints/
│   │   ├── cli-config.md     # Specification for `cli.py`, `__main__.py`, and `config.py`
│   │   └── scan-blueprint.md # Specification for the scan command and related modules
│   └── developer-guide.md
├── dist/                 # Build output (gitignored)
├── sandbox/              # Experiments — fully gitignored
└── PROJECT.md            # Full product specification
```

### CLI / Commands separation

`cli.py` owns argument parsing, config loading, CLI/config merging, and dispatch.
It does **not** contain business logic. Each `cmd_*` function in `cli.py` is a thin
wrapper that delegates to the corresponding `commands/` module:

```python
def cmd_scan(config: ScanConfig) -> None:
    from clonescout.commands.scan import run_scan
    run_scan(config)
```

`cmd_sample` is an exception — it is fully implemented in `cli.py` because it is
lightweight, already complete, and will not grow.

Business logic for each command lives in `commands/scan.py`, `commands/merge.py`,
and `commands/report.py` respectively.

Core flow: `cli → commands/scan → scanner/archive → storage` (local), then
`commands/merge → merge` (cross-machine), then `commands/report → analysis → report`.

## Coding Conventions

### Type Hints
Every function and method must be fully type-hinted. Use Python 3.11 features:
`|` unions, `list[X]`, `dict[K,V]`, `tuple[X,Y]`, `Self`, `Optional[X]`, `Callable`.

### Docstrings
Google style for all public functions, classes, and methods.
Sections: Args, Returns/Yields, Raises are highly desirable.

### Naming
- Modules: `snake_case` | Classes: `PascalCase` | Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE` (in `constants.py`) | Private internals: `_single_underscore`

### Formatting
PEP 8. Line length 100. Import order: stdlib first, then project modules, each block
alphabetically sorted.

### Abstractions
Prefer incremental integration over speculative abstractions. Abstract only after
repeated patterns emerge. Avoid base classes, factories, or DI unless explicitly requested.

## Error Handling

**Scanning must be resilient** — a single unreadable file must never abort the scan.
Collect everything possible, warn about the rest via `logging.warning()` to stderr.

| Situation | Behavior |
|---|---|
| Permission denied on a file/directory | Skip, log warning, continue |
| Broken/corrupt archive | Skip, log warning, continue |
| Non-UTF8 filename | Let `pathlib` handle it (surrogate escapes) |
| Symlink encountered | Ignore via `os.walk(followlinks=False)` |
| Socket, FIFO, device file | Ignore — only regular files are processed |

## Testing

- Framework: `pytest` (dev dependency).
- Integration tests build `.zip`/`.tar.gz` archives on the fly via `tmp_path` — no binary fixtures.
- Every module's public API should have at least a smoke test.
  See `docs/developer-guide.md` for full testing, build, and git workflow details.

## Git Conventions

Lightweight conventional commits:
`feat:` | `fix:` | `docs:` | `refactor:` | `test:` | `chore:`

Versioning: CalVer (`2026.05`, `2026.06`, etc.)

## Key Design Decisions (from PROJECT.md)

- Metadata model: (node, anchor, folder_parent, folder_name, stem, suffix) uniquely identifies a file.
- Features: (ext, size, mtime).
- Storage: nested dicts → vocabulary-indexed → JSON in compressed pickle.
- T1 = "folder_name + stem + ext + size", T2 = "stem + ext + size + mtime", T3 = "stem + ext + size".
- A folder matched at a tier is excluded from lower tiers.
