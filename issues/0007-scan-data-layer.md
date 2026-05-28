# feat: implement data layer — `models.py` and `storage.py`

## Context

This is the first of three issues that implement the `scan` command end-to-end.
It covers the two modules that everything else depends on:

- `models.py` — the `FileRecord` dataclass
- `storage.py` — in-memory metadata structure, vocabulary management, ZIP serialisation

The full specification lives in `docs/blueprints/scan_blueprint.md`.
Read `AGENTS.md` and `PROJECT.md` before starting.

---

## Deliverables

### `src/clonescout/models.py`

A single frozen dataclass:

```python
@dataclass(frozen=True, slots=True)
class FileRecord:
    anchor: str         # "" on POSIX; "C:" / "D:" etc. on Windows;
                        # fully resolved archive path for zip/tar sources
    folder_parent: str  # Posix path to folder's parent, no leading/trailing slash
    folder_name: str    # name of the file's immediate folder
    stem: str           # filename stem (pathlib semantics)
    suffix: str         # filename suffix including leading dot (pathlib semantics)
    ext: str            # suffix without leading dot, uppercased (e.g. "JPG")
    size: int           # file size in bytes
    mtime: int          # modification time, integer (decimal part truncated)
```

Node is **not** stored in `FileRecord`; it is applied at the metadata-insertion stage.

---

### `src/clonescout/storage.py`

#### Vocabulary initialisation — `init_vocab() -> Vocabulary`

Creates a `Vocabulary` pre-populated with the POSIX anchor and all Windows drive letters:

```python
vocab = Vocabulary()
vocab.add("")           # index 0 — POSIX anchor
for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    vocab.add(f"{letter}:")
```

Returns the `Vocabulary` instance.

#### Metadata insertion — `insert_record(metadata, vocab, node, record) -> None`

Signature:

```python
def insert_record(
    metadata: dict,
    vocab: Vocabulary,
    node: str,
    record: FileRecord,
) -> None:
```

Inserts one `FileRecord` into the nested metadata dict using vocabulary indices for
all string dimensions except `node` and `ext`:

```
metadata[node][anchor_idx][folder_parent_idx][folder_name_idx][suffix_idx][stem_idx]
    = (ext, size, mtime)
```

`suffix_idx` comes before `stem_idx` — intentional (groups by extension for analysis locality).

**Conflict resolution:** if the leaf position is already occupied, keep the record
with the larger `mtime`. If both have the same `mtime`, overwrite. Log a `DEBUG`
message for any collision.

**Progress logging:** after each insertion, check whether the total number of
successfully inserted records (across all nodes) is a multiple of
`SCAN_PROGRESS_INTERVAL` (from `constants.py`). If so, emit:

```python
logging.info("Scanned %d files so far...", total_inserted)
```

The function must track `total_inserted` across calls. Make `total_inserted` 
a module-level counter reset by a dedicated `reset_counters()` function.

#### ZIP serialisation — `write_zip(path, vocab, metadata, run_info, force) -> None`

```python
def write_zip(
    path: Path,
    vocab: Vocabulary,
    metadata: dict,
    run_info: dict,
    force: bool,
) -> None:
```

Writes a `ZIP_DEFLATED` archive containing three JSON members:

**`vocab.json`** — the vocabulary as a plain list:
```json
["", "A:", "B:", ..., "photos", "IMG_001", ...]
```

**`metadata.json`** — the nested metadata dict. All dict keys are serialised as
strings (JSON does not support integer keys). The leaf payload `(ext, size, mtime)`
is serialised as a JSON list `[ext, size, mtime]` with `size` and `mtime` as
integers, not strings.

**`run.json`** — the `run_info` dict as-is (caller is responsible for its contents).

If `path` already exists and `force` is `False`, raise `FileExistsError`.

#### ZIP deserialisation — `read_zip(path) -> tuple[Vocabulary, dict, dict]`

```python
def read_zip(path: Path) -> tuple[Vocabulary, dict, dict]:
```

Reads a ZIP written by `write_zip`. Returns `(vocab, metadata, run_info)`.
Restores integer dict keys from their string serialisation.

---

### `src/clonescout/constants.py` — additions

Add:

```python
SCAN_PROGRESS_INTERVAL: int = 10_000  # emit progress log every N files inserted
```

(Other existing constants in the file are unchanged.)

---

### Tests

`tests/units/test_models.py` — smoke tests for `FileRecord`: instantiation,
immutability (frozen), field access.

`tests/units/test_storage.py`:
- `init_vocab()` seeds correct entries at correct indices (index 0 is `""`, index 1
  is `"A:"`, ..., index 26 is `"Z:"`).
- `insert_record()` builds the correct nested structure for a single record.
- Conflict resolution: same leaf, lower `mtime` → existing record wins; same
  `mtime` → overwrite occurs.
- `write_zip()` + `read_zip()` round-trip: write several records, read back,
  assert vocab and metadata are identical.
- `write_zip()` raises `FileExistsError` when output exists and `force=False`.
- `write_zip()` overwrites successfully when `force=True`.

---

## Out of scope for this issue

- `scanner.py`, `archive.py`, `cli.py` changes — covered in Issues 2 and 3.
- `merge` command storage logic — separate issue.

---

## Definition of done

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/
.venv/bin/python -m pytest tests/ -v
```

All three pass clean.