# Blueprint: Merge Operation — CloneScout

> Specification for `commands/merge.py` and the merge path in `storage.py`.

---

## Overview

The `merge` command takes two or more metadata ZIP archives (produced by `scan` or by
a previous `merge`) and produces a single combined ZIP archive with a unified vocabulary,
merged metadata, and a consolidated run history.

Core flow:

```
config.input (list of ZIP paths)
  → read each ZIP → (vocabulary_i, metadata_i, run_info_i)
  → Vocabulary.merge(*vocabularies) → merged_vocabulary + index_maps
  → recode each metadata_i using index_maps[i]
  → merge recoded metadata dicts (conflict resolution: larger mtime wins)
  → collect run history entries
  → write output ZIP (vocab.json, metadata.json, merge.json)
```

---

## Module Responsibility

`commands/merge.py` owns the orchestration: reading inputs, calling helpers,
writing output, error handling.

`storage.py` gains one new public function: `merge_metadata` (see below),
a new parallel function `write_merge_zip` (analogous to `write_zip`),
and `read_zip` is extended to handle both `run.json` and `merge.json`.
`Vocabulary.merge` is already ready and used as-is.

---

## `storage.py` — `merge_metadata()`

```python
def merge_metadata(
    sources: list[tuple[dict[Any, Any], list[int]]],
) -> dict[Any, Any]:
    """Merge recoded metadata dicts into one, resolving leaf conflicts.

    Args:
        sources: A list of (metadata_dict, index_map) pairs, where
            index_map[old_index] = new_index in the merged vocabulary.
            Pairs are processed left-to-right; later entries win on
            equal mtime.

    Returns:
        A single merged metadata dict using the merged vocabulary indices.
    """
```

### Recoding

Before merging, each source metadata dict must have its integer keys translated
from the source vocabulary to the merged vocabulary. Given `index_map` for source `i`:

```python
def _recode(d: dict[Any, Any], index_map: list[int]) -> dict[Any, Any]:
    """Recursively recode integer keys using index_map; leave str keys and leaf tuples intact."""
```

By the time `_recode` is called, `read_zip` has already applied `_keys_to_int`,
so all vocabulary-indexed keys are already `int` and only `node` remains a `str`.
`_recode` therefore does not need to handle string-to-int conversion — it only
translates existing `int` keys to their new positions in the merged vocabulary.

Rules:
- Keys that are `str` (i.e. `node` at level 1) are copied unchanged.
- Keys that are `int` (vocabulary indices at levels 2–6) are replaced with
  `index_map[old_key]`.
- Leaf values are `(ext, size, mtime)` tuples — copied unchanged (ext is a raw string,
  size and mtime are not vocabulary indices).

`_recode` is a private helper; it is called inside `merge_metadata` for each source
before the merge loop.

### Conflict Resolution

Merging two recoded metadata dicts proceeds by deep-walking both simultaneously.
At each non-leaf level, `dict.setdefault` opens the corresponding subtree. At the
leaf level:

- If the leaf position is vacant: insert.
- If the leaf position is occupied: keep the entry with the larger `mtime`
  (index 2 of the tuple). On equal `mtime`, the new entry overwrites the existing
  one (same rule as `insert_record`).
- Log a `DEBUG` message for every leaf collision.

This is identical to the conflict resolution in `insert_record`.

---

## `run.json` vs `merge.json`

Scan ZIPs contain `run.json` — a single dict describing one scan run.

Merge ZIPs contain `merge.json` — a dict with two keys:

```json
{
  "merge_info": {
    "clonescout_version": "2026.05",
    "timestamp": "2026-05-29T14:00:00+02:00",
    "inputs": ["home.zip", "work.zip", "nas.zip"]
  },
  "runs": [
    { ... run.json from home.zip ... },
    { ... run.json from work.zip ... },
    { ... }
  ]
}
```

`merge_info` describes this merge operation itself. `runs` is the ordered list of
all run records collected from all inputs, in input order.

### Collecting `runs` from inputs

When reading an input ZIP, `read_zip` inspects the ZIP member list and applies
the following priority order:

- If the ZIP contains `merge.json`: read it, extend `runs` with its `"runs"` list
  (flatten one level — do not nest). If `run.json` is also present, log a `WARNING`
  about the unexpected member and ignore it.
- Else if the ZIP contains `run.json`: read it, append that single dict to `runs`.
- If neither file is present: `read_zip` logs a `WARNING` and returns `{}` as the
  third element of its return tuple. `run_merge` treats an empty dict as contributing
  zero entries to `runs` — no special-casing needed in the caller.

This means re-merging a previously merged ZIP simply concatenates its run history
into the new `runs` list, preserving full provenance.

---

## `commands/merge.py` — `run_merge()`

```python
def run_merge(config: MergeConfig) -> None:
    """Orchestrate the merge command.

    Args:
        config: Fully validated merge configuration.
    """
```

### Step-by-step

1. **Read all inputs.** For each path in `config.input`:
   - Call `read_zip(path)` → `(vocabulary_i, metadata_i, run_info_or_merge_i)`.
   - Collect into parallel lists: `vocabularies`, `metadatas`, `run_records` (list of lists,
     one inner list per input, flattened as described above).
   - On `FileNotFoundError` or `zipfile.BadZipFile`: print error to stderr, exit with
     `EXIT_RUNTIME_ERROR`.

2. **Merge vocabularies.**
   ```python
   result = Vocabulary.merge(*vocabularies)  # → MergeResult
   ```

3. **Recode and merge metadata.**
   ```python
   sources = [(meta_i, result.index_maps[i]) for i, meta_i in enumerate(metadatas)]
   merged_metadata = merge_metadata(sources)
   ```

4. **Build `merge.json` payload.**
   ```python
   merge_doc = {
       "merge_info": {
           "clonescout_version": CLONESCOUT_VERSION,
           "timestamp": datetime.now(tz=UTC).astimezone().isoformat(),
           "inputs": [str(Path(p).resolve()) for p in config.input],
       },
       "runs": [run for sublist in run_records for run in sublist],
   }
   ```

5. **Write output ZIP.**  
   Call `write_merge_zip(Path(config.output), merged_vocabulary, merged_metadata, merge_doc, force=config.force, indent=...)`.

### Error Handling

| Situation | Behavior |
|---|---|
| Input file not found | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |
| Input file is not a valid ZIP | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |
| Input ZIP missing both `run.json` and `merge.json` | `logging.warning()`, continue |
| Output file exists and `force=False` | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |

---

## `storage.py` — `write_merge_zip()` (new) and `read_zip()` (extended)

`write_zip` is left **unchanged** — the scan call path is not touched.

A new parallel function handles merge output:

```python
def write_merge_zip(
    path: Path,
    vocabulary: Vocabulary,
    metadata: dict[str, Any],
    merge_doc: dict[str, Any],
    force: bool,
    indent: int | None = None,
) -> None:
    """Write a merge-result ZIP archive.

    Identical to write_zip except it writes merge.json instead of run.json.

    Args:
        path: Destination path for the output ZIP file.
        vocabulary: The merged Vocabulary to serialise.
        metadata: The merged nested metadata dict.
        merge_doc: The merge document (merge_info + runs list).
        force: If True, overwrite path when it already exists.
        indent: If a positive integer, pretty-print JSON members.

    Raises:
        FileExistsError: If path exists and force is False.
    """
```

`read_zip` is extended to handle both ZIP types. Its signature is unchanged:

```python
def read_zip(path: Path) -> tuple[Vocabulary, dict[Any, Any], dict[str, Any]]:
```

The third return value is now whichever of `merge.json` or `run.json` was found
(the dict as-is), or `{}` if neither was present (with a `WARNING` logged).
Callers distinguish the two cases by checking for the `"runs"` key.

---

## Output ZIP Contents

| Member | Present in scan ZIP | Present in merge ZIP |
|---|---|---|
| `vocab.json` | ✓ | ✓ |
| `metadata.json` | ✓ | ✓ |
| `run.json` | ✓ | — |
| `merge.json` | — | ✓ |

---

## Module Responsibilities Summary

| Module | Responsibility |
|---|---|
| `storage.py` | `merge_metadata()`, `_recode()`, new `write_merge_zip()`, extended `read_zip()` |
| `commands/merge.py` | Orchestration: read → merge vocabularies → recode → merge metadata → write |
| `config.py` | `MergeConfig` — already complete |
| `cli.py` | `cmd_merge()` dispatch — already complete |