# feat: wire `commands/report.py`, extend `ReportConfig`, and test the report pipeline

## Context

This is the final issue implementing the `report` command end-to-end.  It
wires together the modules built in Issues 0014–0015, extends `ReportConfig`
with LSH and threshold parameters, and adds tests covering the full pipeline.

**Prerequisites:** Issues 0014 and 0015 must be merged first.

---

## Deliverables

### `src/clonescout/config.py` — extend `ReportConfig`

Add LSH parameters and per-tier thresholds to `ReportConfig`:

```python
@dataclass
class ReportConfig(BaseConfig):
    input: str = ""
    output: str | None = None
    lsh_num_bands: int = LSH_NUM_BANDS      # default 15
    lsh_band_size: int = LSH_BAND_SIZE      # default 8
    lsh_seed: int = LSH_SEED               # default 42
    thresholds: dict[str, float] = field(
        default_factory=lambda: dict(TIER_THRESHOLDS)
    )
```

Do NOT extend `_build_report` to read LSH parameters and per-tier thresholds
from TOML.

Validation rules (raise `ConfigError` on violation):

- `lsh_num_bands` and `lsh_band_size` must be integers >= 2.
- `lsh_seed` must be a non-negative integer.
- `thresholds` values must be floats in `(0.0, 1.0]`.


### `src/clonescout/commands/report.py` — implement `run_report`

Replace the current stub with:

```python
def run_report(config: ReportConfig) -> None:
```

#### Step-by-step

1. **Read input ZIP:**
   ```python
   vocabulary, metadata, _ = read_zip(Path(config.input))
   ```
   On `FileNotFoundError` or `zipfile.BadZipFile`: print error to stderr,
   `raise SystemExit(EXIT_RUNTIME_ERROR)`.

2. **Materialise folders:**
   ```python
   folders = build_folders(vocabulary.as_list(), metadata)
   ```
   Log `INFO`: `"Materialised %d folders"`.

3. **Build signature closure:**
   ```python
   get_sig = signature_fabric(
       num_bands=config.lsh_num_bands,
       band_size=config.lsh_band_size,
       seed=config.lsh_seed,
   )
   ```

4. **Find duplicates:**
   ```python
   matches = find_duplicates(
       folders,
       TIER_COMPONENTS,
       TIER_ORDER,
       config.thresholds,
       get_sig,
   )
   ```
   Log `INFO`: `"Found %d duplicate pairs"`.

5. **Format and write report:**
   ```python
   text = format_report(matches, folders)
   ```
   - If `config.output` is `None`: write to stdout.
   - Otherwise: write to `Path(config.output)`.  If the file exists and
     `config.force` is `False`, print an error to stderr and
     `raise SystemExit(EXIT_RUNTIME_ERROR)`.
   - If `matches` is empty: log `INFO "No duplicate folders found"` and
     write nothing (not even an empty file).

#### Error handling

| Situation | Behaviour |
|---|---|
| Input file not found | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |
| Input file not a valid ZIP | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |
| Output exists and `force=False` | Print error to stderr, exit `EXIT_RUNTIME_ERROR` |
| No duplicates found | Log INFO, exit cleanly, write nothing |

---

## Tests

### `tests/units/test_analysis.py`

Use the `VOCAB` / `METADATA` literals from `analysis_snippet.py` directly as
fixtures — copy them into a `conftest.py` or inline them in the test file.

- **`test_build_folders_count`** — assert three folders are materialised from
  the smoke test data.
- **`test_build_folders_ids`** — assert the exact `folder_id` values:
  `"linux:/smoke/backup/photos/2021_copy"`,
  `"windows:C:/smoke/Users/alice/contracts"`,
  `"windows:C:/smoke/Users/alice/photos/2021"`.
- **`test_build_folders_file_count`** — assert `file_count` for each folder
  (6, 2, 5 respectively).
- **`test_build_folders_total_size`** — assert `total_size` for each folder
  (15872, 17408, 15360 bytes respectively).
- **`test_build_folders_skips_empty`** — insert a folder-level entry with no
  stem-level leaves into `METADATA`; assert it does not appear in the result.
- **`test_build_folders_duplicate_id_warning`** — duplicate a folder entry in
  `METADATA` under a different node; assert a `WARNING` is logged and only one
  record is returned.
- **`test_run_tier_finds_match`** — build two `FolderRecord`s sharing 4 of 5
  file feature tuples; run T3; assert one pair is returned with Jaccard = 4/5
  and `shared_size` equal to the sum of the four shared files' sizes.
- **`test_run_tier_no_match_below_threshold`** — same setup but threshold =
  0.99; assert empty result.
- **`test_run_tier_pair_order`** — assert `folder_id_a <= folder_id_b`
  lexicographically in every returned tuple.
- **`test_find_duplicates_exclusion`** — three folders: A and B match on T1,
  B and C match on T3.  Assert B appears only in the T1 result and not in T3.
- **`test_find_duplicates_sorted_by_shared_size`** — two T3 pairs with
  different `shared_size`; assert they appear in descending order.
- **`test_find_duplicates_smoke`** — run the full pipeline on the smoke test
  data; assert one match, tier T3, Jaccard ≈ 0.83, `shared_size` = 15360.

### `tests/units/test_report.py`

- **`test_fmt_size_bytes`** — `_fmt_size(512)` → `"512 B"`.
- **`test_fmt_size_kib`** — `_fmt_size(1536)` → `"1.5 KiB"`.
- **`test_fmt_size_mib`** — `_fmt_size(1_572_864)` → `"1.5 MiB"`.
- **`test_fmt_size_boundary`** — `_fmt_size(1024)` → `"1.0 KiB"` (not `"1024 B"`).
- **`test_format_report_empty`** — `format_report([], {})` returns `""`.
- **`test_format_report_structure`** — one `MatchCandidate` at T3 from the
  smoke test data; assert output contains `"## Tier: T3"`, the two folder IDs,
  `"Jaccard: 0.83"`, and `"Shared: 15.0 KiB"`.
- **`test_format_report_tier_order`** — matches list with T2 entry before T1
  entry; assert T2 heading appears before T1 heading (order follows input).
- **`test_format_report_folder_id_order`** — assert `folder_id_a` line appears
  before `folder_id_b` line within a pair.

### `tests/integration/test_cmd_report.py`

Build a real metadata ZIP in `tmp_path` using `write_zip` from `storage.py`,
then call `run_report(config)` directly.

- **`test_report_to_stdout`** — `config.output = None`; capture stdout; assert
  it contains the expected tier heading and folder IDs.
- **`test_report_to_file`** — `config.output` points to a file in `tmp_path`;
  assert the file exists and contains valid Markdown after the run.
- **`test_report_force_false`** — run twice with `force=False`; assert second
  run raises `SystemExit(EXIT_RUNTIME_ERROR)`.
- **`test_report_force_true`** — run twice with `force=True`; assert second
  run succeeds and overwrites.
- **`test_report_no_duplicates`** — ZIP with a single folder; assert no output
  file is created and exit code is 0.
- **`test_report_bad_input`** — non-ZIP file as input; assert `SystemExit`.
- **`test_report_missing_input`** — nonexistent path as input; assert
  `SystemExit`.

---

## Definition of done

```bash
.venv/bin/python -m ruff check src/ tests/
.venv/bin/python -m mypy src/
.venv/bin/python -m pytest tests/ -v
```

All three pass clean.
