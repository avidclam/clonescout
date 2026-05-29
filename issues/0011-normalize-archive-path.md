# refactor: Normalize Archive Entry Paths in `archive.py`

## Context

During manual testing against real-world archives, a structural inconsistency was
discovered between ZIP and TAR path handling:

- ZIP entries use bare paths: `data/csv/inventory.csv`
- TAR entries carry a `./` prefix: `./data/csv/inventory.csv`

Beyond this specific difference, TAR as a format presents additional cases
that the current implementation does not account for. Left unaddressed,
these will cause silent mismatches during metadata comparison and merge, or
produce incorrect folder trees in the analysis stage.

## Problems

**1. Inconsistent path representation across archive types.**
A file stored as `data/csv/inventory.csv` in a ZIP and `./data/csv/inventory.csv`
in a TAR will be treated as two different files during merge and analysis. This
directly undermines the cross-machine deduplication goal.

**2. Non-regular entries are not explicitly filtered in TAR.**
TAR archives can contain symlinks, hard links, block devices, character devices,
and FIFOs alongside regular files. Only `isfile()` entries should be processed;
passing others through silently produces incorrect size and mtime values (symlinks
report `size=0`, hard links are inconsistent across implementations).

**3. ZIP entries can carry the same path prefixes.**
Depending on the tool that created the archive, ZIP entries may also start with
`./` or `/`. Applying normalization only to TAR and not to ZIP leaves a latent
inconsistency.

## Recommended Changes

### Add a shared `_normalize_entry_path` helper

Place this in `archive.py` and apply it to every entry from both ZIP and TAR
before the path is used anywhere. Archives may contain absolute paths depending
on how they were created; for duplicate detection purposes this is irrelevant —
we simply strip leading `/` so equivalent paths from different archives produce
identical metadata keys.

```python
import posixpath

def _normalize_entry_path(name: str) -> str:
    """Strip leading './' and '/' from an archive entry name.

    Both ZIP and TAR can produce paths with these prefixes depending on
    how the archive was created. Stripping them ensures that equivalent
    paths from different archive types produce identical metadata keys.

    Args:
        name: Raw entry name from ZipInfo.filename or TarInfo.name.

    Returns:
        Clean relative POSIX path (empty string for root-level entries).
        Returns ``""`` for empty-string and ``"."`` inputs.
    """
    cleaned = posixpath.normpath(name)
    if cleaned == ".":
        return ""
    return cleaned.lstrip("/")
```

### Filter TAR entries to regular files only

`TarInfo.isfile()` returns `True` for ``REGTYPE``, ``AREGTYPE``, and **``CONTTYPE``**.
``CONTTYPE`` (GNU split-file continuation blocks) must be excluded explicitly —
they are fragments of a split file, not standalone entries. All other non-regular
types (``LNKTYPE``, ``SYMTYPE``, ``CHRTYPE``, ``BLKTYPE``, ``DIRTYPE``, ``FIFOTYPE``)
are correctly excluded by ``isfile()``.

```python
import tarfile

for member in tf:
    if not member.isfile() or member.type == tarfile.CONTTYPE:
        continue
    yield _normalize_entry_path(member.name), member.size, int(member.mtime)
```

### Apply the same normalization to ZIP entries

Normalize raw entry names **before** any downstream processing (skip-component
checks, path splitting for folder/stem/suffix extraction). Otherwise a `./`
prefix produces an extraneous `"."` component in path splits.

```python
for info in zf.infolist():
    if info.is_dir():
        continue
    normalized = _normalize_entry_path(info.filename)
    # ... skip check, path splitting, etc. all use normalized
```

## Acceptance Criteria

- [ ] `_normalize_entry_path` returns `""` for both empty string and `"."` inputs.
- [ ] `_normalize_entry_path` is present in `archive.py` and has unit tests covering:
  bare path, `./` prefix, `/` prefix, nested `./`, empty string, `"."`.
- [ ] TAR iteration skips symlinks, hard links, directories, devices, FIFOs,
  and ``CONTTYPE`` (GNU split-file continuation blocks).
- [ ] ZIP iteration applies the same normalization as TAR.
- [ ] Normalization is applied as the first operation on the raw entry name,
  before skip-component matching or path-component splitting.
- [ ] Metadata produced from equivalent ZIP and TAR archives is byte-identical
  (integration test using `tmp_path`-built archives).

## References

- Discovered during scan testing on `archives/archive.zip` and `archives/archive.tgz`
- `archive.py` — module under change
- `AGENTS.md` — error handling table (symlinks ignored via `followlinks=False`;
  same philosophy applies inside archives)