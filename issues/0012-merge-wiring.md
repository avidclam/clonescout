# feat: implement `run_merge` in `src/clonescout/commands/merge.py`

## Context

This issue implements the `merge` command end-to-end. It creates the orchestration
in `commands/merge.py`, adds `_recode()` + `merge_metadata()` + `write_merge_zip()`
in `storage.py`, and extends `read_zip()` to handle both `run.json` and `merge.json`.

`MergeConfig`, `Vocabulary.merge`, and the CLI dispatch (`cmd_merge` in `cli.py`)
are already in place and used as-is.

The full specification lives in `docs/blueprints/merge-blueprint.md`.
Read `AGENTS.md` and `PROJECT.md` before starting.

---

## Deliverable

### `storage.py` — new and extended functions

#### `_recode(d, index_map)` (private helper)

Recursively deep-copy the metadata dict, translating integer keys via `index_map`:
- `str` keys (i.e. `node` at level 1) → copied unchanged.
- `int` keys (vocabulary indices at levels 2–6) → replaced with `index_map[old_key]`.
- Leaf values `(ext, size, mtime)` → copied unchanged.

Called inside `merge_metadata` once per source. By the time `_recode` runs,
`read_zip` has already applied `_keys_to_int`, so no string-to-int conversion is needed.

#### `merge_metadata(sources)` (new public function)

```python
def merge_metadata(
    sources: list[tuple[dict[Any, Any], list[int]]],
) -> dict[Any, Any]:
```

1. For each `(metadata_dict, index_map)` pair, call `_recode(metadata_dict, index_map)`.
2. Deep-walk all recoded dicts simultaneously using `dict.setdefault`.
3. At leaf level:
   - Vacant → insert.
   - Occupied → keep entry with larger `mtime` (index 2). Equal `mtime` → newer overwrites.
   - Log `DEBUG` for every collision (identical to `insert_record`).
4. Return the merged dict.

#### `write_merge_zip(path, vocab, metadata, merge_doc, force, indent)` (new public function)

Analogue of `write_zip` that writes `merge.json` instead of `run.json`. Same
signature except `merge_doc` replaces `run_info`. Same error handling
(`FileExistsError` if path exists and `force=False`).

`write_zip` is left **unchanged**.

#### `read_zip` (extended)

Signature unchanged: `(vocab, metadata, info)`. The third element is now whatever
was found in the ZIP:

| Member found | Returns |
|---|---|
| `merge.json` | The dict as-is |
| No `merge.json`, but `run.json` | The dict as-is |
| Neither | `{}` (logs `WARNING`) |
| Both `merge.json` and `run.json` | `merge.json` dict (logs `WARNING` about unexpected `run.json`) |

Callers distinguish merge-ZIP from scan-ZIP by checking for the `"runs"` key.

---

### `commands/merge.py` — `run_merge(config: MergeConfig) -> None`

#### Step-by-step

1. **Read all inputs.** For each path in `config.input`:
   - `vocab, metadata, info = read_zip(Path(path))`
   - Collect vocab, metadata, and extract run records:
     - If `info` has key `"runs"` → flatten that list into `run_records`.
     - Else if `info` is non-empty (single scan-ZIP) → append `info` wrapped in a list.
     - Else (`{}`) → contribute nothing.
   - On `FileNotFoundError` or `BadZipFile`: print error to stderr, `raise SystemExit(EXIT_RUNTIME_ERROR)`.

2. **Merge vocabularies:** `result = Vocabulary.merge(*vocabs)`

3. **Recode and merge metadata:**
   ```python
   sources = [(meta, result.index_maps[i]) for i, meta in enumerate(metadatas)]
   merged_metadata = merge_metadata(sources)
   ```

4. **Build merge.json payload:**
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

5. **Write output ZIP:**
   ```python
   try:
       write_merge_zip(
           Path(config.output),
           merged_vocab, merged_metadata, merge_doc,
           force=config.force,
       )
   except FileExistsError:
       print(
           f"error: output file already exists: {config.output} "
           "(use --force to overwrite)",
           file=sys.stderr,
       )
       raise SystemExit(EXIT_RUNTIME_ERROR)
   ```

#### Error handling

| Situation | Behavior |
|---|---|
| Input file not found | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |
| Input file not a valid ZIP | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |
| Input ZIP missing both `run.json` and `merge.json` | Warning logged by `read_zip`, continues |
| Output exists and `force=False` | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |

---

## Tests

### `tests/units/test_storage.py` — additions

- **`test_recode_remaps_int_keys`** — Build a small metadata dict, recode it with
  a known `index_map`, verify int keys are translated and str keys / leaf tuples
  are preserved.
- **`test_merge_metadata_merges_disjoint_sources`** — Two sources with no
  overlapping paths, verify all records appear.
- **`test_merge_metadata_overlapping_takes_larger_mtime`** — Same leaf in both
  sources, different mtimes, verify larger mtime wins.
- **`test_merge_metadata_equal_mtime_overwrites`** — Same leaf, equal mtime,
  verify later source wins.
- **`test_merge_metadata_collsion_logging`** — Verify `DEBUG` messages for collision.
- **`test_write_merge_zip_and_read_zip_roundtrip`** — Write a merge ZIP with
  `write_merge_zip`, read it back with `read_zip`, assert vocab/metadata/merge_doc
  survive the roundtrip.
- **`test_read_zip_falls_back_to_merge_json`** — Write a ZIP with `merge.json`
  but no `run.json`, read with `read_zip`, assert third element has `"runs"` key.
- **`test_read_zip_prefers_merge_json_over_run_json`** — Write ZIP with both,
  assert `merge.json` is returned and warning is logged.
- **`test_read_zip_returns_empty_dict_when_no_info`** — Write valid ZIP with only
  `vocab.json` and `metadata.json`, assert third element is `{}` and warning logged.

### `tests/integration/test_cmd_merge.py`

- **Happy path — two scan ZIPs:** Create two scan ZIPs via `write_zip`, merge them
  with `run_merge`, read the result back, assert:
  - Merged vocab contains all strings from both inputs.
  - All records from both inputs are present in merged metadata.
  - `merge_doc["runs"]` has exactly 2 entries.
  - `merge_doc["merge_info"]["inputs"]` contains resolved paths of both inputs.
- **Happy path — scan ZIP + merge ZIP:** Merge a scan ZIP and a previously merged
  ZIP, assert `runs` has the correct flattened count (1 + N from previous merge).
- **Force flag:** Run merge twice with `force=False` → `SystemExit`; with `force=True` → succeeds.
- **Bad input ZIP:** Pass a non-ZIP file → `SystemExit`.
- **Missing input file:** Pass a nonexistent path → `SystemExit`.

---

## Out of scope for this issue

- `cmd_report` — separate issue.
- LSH / MinHash / tiered matching — separate issue.

---

## Definition of done

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/
.venv/bin/python -m pytest tests/ -v
```

All three pass clean.
