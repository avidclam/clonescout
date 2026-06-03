# feat: implement scanners — `scanner.py` and `archive.py`

## Context

This is the second of three issues implementing the `scan` command.
It covers filesystem and archive scanning:

- `scanner.py` — `classify_path()`, `BaseScanner`, `FSScanner`
- `archive.py` — `ZipScanner`, `TarScanner`

**Prerequisite:** Issue 1 (data layer) must be merged first.
`FileRecord` from `models.py` and `ScanConfig` from `config.py` are used throughout.

The full specification lives in `docs/blueprints/scan-blueprint.md`.
Read `AGENTS.md` and `PROJECT.md` before starting.

---

## Deliverables

### `src/clonescout/scanner.py`

#### `classify_path(path: Path) -> str`

Called once per root before any scanning begins. Returns one of six string literals:

| Return value | Condition |
|---|---|
| `"DIR"` | Path exists and is a directory |
| `"ZIP"` | Regular file, ZIP format |
| `"TAR"` | Regular file, tar / tar.gz / tgz format |
| `"FILE"` | Regular file, unrecognised format |
| `"NONEXISTENT"` | Path does not exist |
| `"UNSUPPORTED"` | Symlink, socket, device node, or other special file |

A "regular file" means: exists, `is_file()` is `True`, `is_symlink()` is `False`,
and is not a socket, device node, or other special file
(i.e. `stat.S_ISREG(st.st_mode)` is `True`).
Format detection uses `zipfile.is_zipfile()` and `tarfile.is_tarfile()` — do not
rely on file extension alone.

#### `BaseScanner`

```python
class BaseScanner:
    def __init__(self, root: Path, config: ScanConfig) -> None: ...
    def __iter__(self) -> Iterator[FileRecord]: ...
```

Pure interface — no logic in the base class beyond storing `self.root` and
`self.config`. Subclasses implement `__iter__`.

#### `FSScanner(BaseScanner)`

Walks a local directory tree with `os.walk(root, followlinks=False)`.

**skip logic:** at each directory node, before descending, remove from `os.walk`'s
`dirnames` list **in-place** any name present in `config.skip`. This prunes the
entire subtree.

**File filtering:** yield only regular files — check with `stat.S_ISREG(st.st_mode)`.
Skip symlinks, sockets, FIFOs, and device files silently.

**`FileRecord` construction:**

```python
filepath = (Path(dirpath) / filename).resolve()
anchor_path = Path(filepath.anchor)
anchor = anchor_path.as_posix().rstrip("/")        # "" on POSIX, "C:" on Windows
folder_name = filepath.parent.name
folder_parent = filepath.relative_to(anchor_path).parent.parent.as_posix().strip("/")
folder_parent = "" if folder_parent == "." else folder_parent
stem = Path(filename).stem
suffix = Path(filename).suffix
ext = suffix.lstrip(".").upper()
size = st.st_size
mtime = int(st.st_mtime)
```

**Error handling:** wrap `os.stat()` and directory descent in `try/except OSError`.
On `PermissionError` or any `OSError`: `logging.warning()`, continue.

---

### `src/clonescout/archive.py`

Both scanners share the same skip and path-derivation logic; factor out a
module-level helper if it reduces duplication, but keep it private (`_`-prefixed).

#### `ZipScanner(BaseScanner)`

Iterates over members of a ZIP archive using `zipfile.ZipFile`, without extraction.

**anchor:** the fully resolved Posix path of the archive file itself:

```python
archive_path = root.resolve()
anchor = archive_path.as_posix()   # e.g. "/backups/archive.zip"
```

**Member filtering:**
- Skip directory entries (`ZipInfo.is_dir()`).
- Apply skip logic: split member name on `"/"`, check every component against
  `config.skip`. If any component matches, skip the member silently.

**`FileRecord` construction** from the member's Posix path
(e.g. `photos/2021/IMG_001.jpg`):

```python
parts = member_path.split("/")
filename = parts[-1]
folder_name = parts[-2] if len(parts) >= 2 else ""
folder_parent = "/".join(parts[:-2]) if len(parts) >= 3 else ""
stem = Path(filename).stem
suffix = Path(filename).suffix
ext = suffix.lstrip(".").upper()
size = zip_info.file_size
mtime = int(datetime(*zip_info.date_time).timestamp())
```

**Error handling:** wrap the entire iteration in `try/except Exception`. On a corrupt
or unreadable member: `logging.warning()`, continue. On a completely unreadable
archive: `logging.warning()`, yield nothing.

#### `TarScanner(BaseScanner)`

Iterates over members of a tar / tar.gz / tgz archive using `tarfile.open()`,
without extraction.

**anchor:** same rule as `ZipScanner`:

```python
archive_path = root.resolve()
anchor = archive_path.as_posix()
```

**Member filtering:**
- Skip non-regular-file members (`not member.isfile()`).
- Apply skip logic: split `member.name` on `"/"`, check every component against
  `config.skip`. If any component matches, skip the member silently.

**`FileRecord` construction:**

```python
parts = member.name.split("/")
filename = parts[-1]
folder_name = parts[-2] if len(parts) >= 2 else ""
folder_parent = "/".join(parts[:-2]) if len(parts) >= 3 else ""
stem = Path(filename).stem
suffix = Path(filename).suffix
ext = suffix.lstrip(".").upper()
size = member.size
mtime = int(member.mtime)
```

**Error handling:** same strategy as `ZipScanner`.

---

## Tests

### `tests/units/test_scanner.py`

**`classify_path` tests** (use `tmp_path`):
- Returns `"DIR"` for an existing directory.
- Returns `"ZIP"` for a valid ZIP file.
- Returns `"TAR"` for a valid `.tar.gz` file.
- Returns `"FILE"` for a regular file with unrecognised format.
- Returns `"NONEXISTENT"` for a path that does not exist.
- Returns `"UNSUPPORTED"` for a symlink.

**`FSScanner` tests** (build a small directory tree in `tmp_path`):
- Yields the correct `FileRecord` fields for a simple file.
- A file at the filesystem root produces `folder_name = ""` and `folder_parent = ""`.
- `skip` prunes a matching subdirectory and all its contents.
- Non-regular files (symlinks) are not yielded.
- A directory with a permission error on a subdirectory logs a warning and
  continues yielding records from the rest of the tree.

### `tests/units/test_archive.py`

Build archives on the fly in `tmp_path` — no binary fixtures.

**`ZipScanner` tests:**
- Yields the correct `FileRecord` fields for a member inside a subdirectory.
- A member directly at the archive root (no containing folder) produces
  `folder_name = ""` and `folder_parent = ""`.
- `skip` suppresses members whose path contains a matching component.
- A corrupt ZIP logs a warning and yields nothing (does not raise).

**`TarScanner` tests:** mirror the `ZipScanner` tests for tar.gz archives.

---

## Out of scope for this issue

- `cmd_scan` wiring, exclude pattern application, counter tracking, ZIP output —
  covered in Issue 3.
- `merge` and `report` commands.

---

## Definition of done

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/
.venv/bin/python -m pytest tests/ -v
```

All three pass clean.
