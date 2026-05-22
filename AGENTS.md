# AGENTS — CloneScout

> Instructions for AI coding assistants working on this project.
> Read this file first, then consult the relevant blueprint before touching any module.

---

## 1. Mission

CloneScout is a portable Python CLI tool that finds duplicate and near-duplicate
directories using only filesystem metadata — no file content reading. It scans
locally, stores metadata in portable archives, merges results from multiple
machines, and produces a tiered duplicate report.

Full product specification: `PROJECT.md`.

---

## 2. Tech Stack & Constraints

- **Python 3.11 exactly.** Zero external dependencies — standard library only.
- Permitted 3.11-specific: `tomllib`, `typing.Self / LiteralString / Never`, exception groups.
- **Forbidden (3.12+):** `itertools.batched`, PEP 695 type syntax, `pathlib.Path.walk` → use `os.walk`.

---

## 3. Project Structure

    clonescout/
    ├── PROJECT.md
    ├── AGENTS.md
    ├── README.md
    ├── LICENSE
    │
    ├── docs/
    │   ├── blueprints/
    │   │   ├── cli.md               # CLI commands, flags, verbosity, config file
    │   │   ├── archive-handling.md  # Archive scanning rules and constraints
    │   │   └── analysis.md          # Metadata model, storage format, LSH/MinHash tiers
    │   ├── user-guide.md            # Usage instructions and tips
    │   ├── developer-guide.md       # Testing, git, versioning, build, dev workflow
    │   └── changelog.md
    │
    ├── snippets/                    # Code fragments before integration into src/
    │
    ├── src/
    │   └── clonescout/
    │       ├── __init__.py
    │       ├── __main__.py          # Entry point
    │       ├── cli.py               # argparse: scan | merge | report | sample
    │       ├── scanner.py           # Recursive metadata collection (file system)
    │       ├── archive.py           # .zip/.tar/.tar.gz reading without extraction
    │       ├── storage.py           # Vocabulary + JSON + compressed pickle
    │       ├── merge.py             # Cross-machine vocabulary merging
    │       ├── analysis.py          # LSH + MinHash, tiered matching (T1→T2→T3)
    │       ├── report.py            # Prioritized Markdown report
    │       ├── config.py            # TOML config loading, defaults
    │       ├── models.py            # Dataclasses: FileRecord, FolderRecord, MatchCandidate
    │       └── constants.py         # Tier names, config keys, magic strings
    │
    ├── tests/
    │   ├── conftest.py
    │   ├── unit/
    │   └── integration/
    │
    ├── scripts/
    │   └── build_zipapp.py
    │
    ├── dist/
    ├── sandbox/                     # Experiments — fully gitignored
    ├── .github/workflows/ci.yml
    ├── .gitignore
    ├── .python-version              # 3.11
    └── pyproject.toml

---

## 4. Coding Conventions

### Abstractions

Prefer incremental integration over speculative abstractions.
Abstract only after repeated patterns emerge.

Avoid introducing layers, base classes, factories,
or dependency injection unless explicitly requested.

### Type Hints
Every function and method must be fully type-hinted. Use Python 3.11 features:
`|` unions, `list[X]`, `dict[K,V]`, `tuple[X,Y]`, `Self`, `Optional[X]`, `Callable`.

### Docstrings
Google style for all public functions, classes, and methods. 
Treat these sections - Args, Returns or Yields", Raises - as highly desirable.

### Naming
- Modules: `snake_case` | Classes: `PascalCase` | Functions & methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE` (in `constants.py`) | Private internals: `_single_underscore`

### Formatting
PEP 8. Line length 100. Import order: stdlib first, then project modules, each block
alphabetically sorted.

---

## 5. Error Handling

**Scanning must be resilient** — a single unreadable file must never abort the scan.
Collect everything possible, warn about the rest via `logging.warning()` to stderr.

| Situation | Behavior |
|---|---|
| Permission denied on a file/directory | Skip, log warning, continue |
| Broken/corrupt archive | Skip, log warning, continue |
| Non-UTF8 filename | Let `pathlib` handle it (surrogate escapes) |
| Symlink encountered | Ignore via `os.walk(followlinks=False)` |
| Socket, FIFO, device file | Ignore — only regular files are processed |

---

## 6. Module → Blueprint Map

Before writing or modifying a module, read the corresponding blueprint:

| Module(s) | Blueprint |
|---|---|
| `cli.py`, `__main__.py`, `config.py` | `docs/blueprints/cli.md` |
| `archive.py` | `docs/blueprints/archive-handling.md` |
| `analysis.py`, `storage.py`, `merge.py`, `models.py` | `docs/blueprints/analysis.md` |
| Testing, git, build | `docs/developer-guide.md` |
