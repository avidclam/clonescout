# Blueprint: Scan Operation — CloneScout

> Specification for `scanner.py`, `archive.py`, `models.py` (FileRecord), and the scan path in `cli.py`.

---

## Overview

The `scan` command collects filesystem metadata from one or more roots, encodes it into a
vocabulary-indexed nested dictionary, and writes the result to a ZIP archive.

Core flow:

```
config.roots
  → classify each root
  → instantiate scanners (FSScanner / ZipScanner / TarScanner)
  → chain into one iterator of FileRecord
  → apply exclude patterns
  → insert into metadata structure
  → serialize to output ZIP
```

---

## `models.py` — FileRecord

```python
@dataclass(frozen=True, slots=True)
class FileRecord:
    anchor: str          # "" on POSIX, "C:" / "D:" etc. on Windows;
                         # fully resolved archive path for zip/tar sources
    folder_parent: str   # resolved Posix path to folder's parent, no leading/trailing slash
    folder_name: str     # name of the file's immediate folder
    stem: str            # filename stem (pathlib semantics)
    suffix: str          # filename suffix including leading dot (pathlib semantics)
    ext: str             # suffix without leading dot, uppercased (e.g. "JPG")
    size: int            # file size in bytes
    mtime: int           # modification time, integer (decimal part truncated)
```

**Node is not stored in FileRecord.** It is a property of the scan run and is applied
at the metadata-insertion stage.

---

## Root Validation — `classify_path()`

Lives in `scanner.py`. Called once per root before any scanning begins.
If any root is invalid, the command exits with code 1 (hard error).

```python
def classify_path(path: Path) -> str:
    """Classify a candidate scan root.

    Returns one of: "DIR", "ZIP", "TAR", "FILE", "NONEXISTENT", "UNSUPPORTED"
    """
```

| Result | Meaning |
|---|---|
| `"DIR"` | Existing directory → FSScanner |
| `"ZIP"` | Regular file, ZIP format → ZipScanner |
| `"TAR"` | Regular file, tar/tar.gz/tgz format → TarScanner |
| `"FILE"` | Regular file, unrecognised format → hard error |
| `"NONEXISTENT"` | Path does not exist → hard error |
| `"UNSUPPORTED"` | Symlink, socket, device, etc. → hard error |

A regular file is one that exists, `is_file()` is True, and is neither a symlink nor a socket.

---

## Scanner Classes — `scanner.py` and `archive.py`

### Base class

```python
class BaseScanner:
    def __init__(self, root: Path, config: ScanConfig) -> None: ...
    def __iter__(self) -> Iterator[FileRecord]: ...
```

All scanners are iterators of `FileRecord`. The chain is assembled with `itertools.chain`.

### `FSScanner` — `scanner.py`

Walks a local directory tree using `os.walk(root, followlinks=False)`.

**skip logic:** at each directory node, before descending, remove from `os.walk`'s
`dirnames` list in-place any name that appears in `config.skip`. This prunes the
subtree entirely.

For each regular file (skip sockets, FIFOs, symlinks, devices — only `stat.S_ISREG`):
- extract anchor from `path.anchor` (`""` on POSIX, `"C:"` etc. on Windows)
- build folder_parent as the Posix representation of the folder's parent relative to anchor
- yield a `FileRecord`

Permission errors on individual files or directories: `logging.warning()`, continue.

### `ZipScanner` and `TarScanner` — `archive.py`

Iterate over archive members without extraction.

**skip logic:** for each member path (e.g. `photos/2021/IMG_001.jpg`), split on `/`
and check every component against `config.skip`. If any component matches, skip the
member. This produces the same result as extracting the archive and running `FSScanner`
over the resulting tree.

**anchor:** the Posix path string of the archive file itself (e.g. `/backups/archive.zip`).

**folder_parent / folder_name:** derived by splitting the member's Posix path.
- `folder_parent`: all components except the last two, joined with `/`
- `folder_name`: second-to-last component (the immediate parent directory)
- `stem` / `suffix`: from the final component, pathlib semantics

Members that are directories (no file content) are skipped silently.
Corrupt or unreadable members: `logging.warning()`, continue.

---

## Metadata Structure

### Vocabulary initialisation

Before scanning begins, a `Vocabulary` instance is created and pre-populated:

```python
vocabulary = Vocabulary()
vocabulary.add("")          # POSIX anchor (index 0)
for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    vocabulary.add(f"{letter}:")   # Windows drive anchors
```

### Nested dict layout

```python
metadata: dict = {}
# metadata[node][anchor_idx][folder_parent_idx][folder_name_idx][suffix_idx][stem_idx]
#     = (ext, size, mtime)
```

- `node` (str) and `ext` (str) are **not** replaced by vocabulary indices.
- All other string dimensions (anchor, folder_parent, folder_name, suffix, stem)
  are stored as their integer vocabulary index.
- `suffix_idx` appears before `stem_idx` — this is intentional (grouping by extension
  before individual file name improves analysis locality).

### Conflict resolution

If two `FileRecord`s map to the same leaf position, keep the one with the larger `mtime`.
If two colliding `FileRecord`s have the same `mtime`, overwrite the leaf position.
Log a `DEBUG` message for the collision.

This handles the case where two roots overlap and the same inode is visited twice.

---

## exclude Pattern Application

Before inserting a `FileRecord` into metadata, build the candidate path string:

```
{folder_parent}/{folder_name}/{stem}{suffix}
```

Empty components (folder_parent and folder_name can both be "") are omitted from the join — 
no leading or consecutive slashes are inserted.

Apply all compiled regex patterns from `config.exclude`. If any pattern matches,
skip the file and emit `logging.debug()`.

---

## Output ZIP — `storage.py`

The output file is a ZIP archive containing three JSON members:

### `vocab.json`

```json
["", "A:", "B:", ..., "photos", "IMG_001", ...]
```

The vocabulary as a plain list (output of `vocabulary.as_list()`). Index position = vocabulary index.

### `metadata.json`

The nested metadata dict, serialised as JSON. Keys at all levels are strings
(JSON does not support integer keys — indices are serialised as strings and
parsed back to int on load).
Metadata payload - (ext, size, mtime) tuple - is serialised as a JSON list 
with integer values not converted to strings.

### `run.json`

```json
{
  "clonescout_version": "2026.05",
  "timestamp": "2026-05-27T14:32:00+02:00",
  "hostname": "myhost",
  "roots": ["/data/photos", "/backups/archive.zip"],
  "files_scanned": 18423,
  "files_excluded": 47
}
```

| Field | Notes |
|---|---|
| `clonescout_version` | CalVer string from `constants.py` |
| `timestamp` | ISO 8601 with local timezone offset |
| `hostname` | `socket.gethostname()` — always actual hostname, independent of `node` config |
| `roots` | Resolved absolute paths as given to the scanners |
| `files_scanned` | FileRecords successfully inserted into metadata |
| `files_excluded` | Skipped due to `exclude` regex match |

The ZIP is written with `compression=ZIP_DEFLATED`.

---

## Module Responsibilities Summary

| Module | Responsibility |
|---|---|
| `scanner.py` | `classify_path()`, `BaseScanner`, `FSScanner` |
| `archive.py` | `ZipScanner`, `TarScanner` |
| `models.py` | `FileRecord` dataclass |
| `storage.py` | Vocabulary init, metadata dict management, ZIP read/write |
| `cli.py` | Root validation loop, scanner instantiation, `itertools.chain`, counter tracking, dispatch to storage |
