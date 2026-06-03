# Blueprint — `analysis.py`

> Specification for the duplicate directory detection module in CloneScout.
> Implements LSH + MinHash with tiered matching (T1 → T2 → T3).
> Read alongside `PROJECT.md` and `AGENTS.md` before implementing.

---

## Responsibilities

`analysis.py` takes a merged (or single-scan) metadata ZIP and produces a list
of duplicate/near-duplicate folder pairs with tier labels and Jaccard scores.

It does **not** read or write ZIP files — that is `storage.py`'s job.
It **does** own folder materialisation from the decoded metadata dict.

---

## Public API

```python
def materialize_folders(
    vocab: Vocabulary,
    metadata: dict[Any, Any],
) -> dict[str, FolderRecord]:
    ...

def find_duplicates(
    folders: dict[str, FolderRecord],
    config: ReportConfig,
) -> list[MatchCandidate]:
    ...
```

`find_duplicates` is the single entry point called by `commands/report.py`.
It runs the full T1 → T2 → T3 tiered loop and returns all matched pairs.

---

## Data Flow

```
read_zip(path)
    │
    ▼
materialize_folders(vocab, metadata)
    │  Decodes nested index dict → dict[folder_id, FolderRecord]
    ▼
find_duplicates(folders, config)
    │
    ├─ T1 pass: run_tier(active_folders, T1_COMPONENTS, get_signature, threshold_t1)
    │       │  returns list[(folder_id_a, folder_id_b, jaccard)]
    │       │
    │       └─ excluded |= all folder_ids that appear in any returned pair
    │
    ├─ T2 pass: same, over (folders − excluded)
    │
    └─ T3 pass: same, over (folders − excluded)
         │
         ▼
    list[MatchCandidate]  (all tiers combined, ordered by total_size desc)
```

---

## Folder Materialisation

`materialize_folders` traverses the metadata nested dict and reconstructs
`FolderRecord` instances using the vocabulary for index → string lookups.

### Traversal order

```
metadata[node: str]
         [anchor_idx: int]       → strings[anchor_idx]
         [folder_parent_idx: int]→ strings[folder_parent_idx]
         [folder_name_idx: int]  → strings[folder_name_idx]
         [suffix_idx: int]       → strings[suffix_idx]
         [stem_idx: int]         → (ext: str, size: int, mtime: int)
```

For each `(node, anchor, folder_parent, folder_name)` combination, collect all
`FileRecord` leaves and build one `FolderRecord`. Key the result by
`FolderRecord.folder_id`.

### Edge cases

- Folders with zero files: skip (can arise from corrupt/partial scans).
- The same `folder_id` appearing twice: log `WARNING`, keep the first occurrence.

---

## LSH + MinHash

### Hash function

Universal hash family over a Mersenne prime field:

```
h(x, a, b, p) = (a * blake2b_int(repr(x)) + b) mod p
```

where `p = 2^61 − 1`, `a ∈ [1, p−1]`, `b ∈ [0, p−1]`.

`blake2b_int` is the 8-byte little-endian integer of `hashlib.blake2b(repr(x).encode(), digest_size=8).digest()`.

A feature can be any hashable Python value — tuples, strings, ints — because
`repr()` is applied before hashing.

### MinHash signature

For a feature set `F` and `num_hashes = num_bands × band_size` parameter pairs
`(a_i, b_i)`:

```
signature[i] = min(h(f, a_i, b_i, p) for f in F)
```

The signature is split into `num_bands` consecutive bands of `band_size`
integers each. Each band becomes one LSH bucket key: `(band_index, band_tuple)`.

### Default parameters

| Parameter | Default | Config key |
|---|---|---|
| `num_bands` | 15 | `analysis.lsh_num_bands` |
| `band_size` | 8 | `analysis.lsh_band_size` |
| `seed` | 42 | `analysis.lsh_seed` |

These default to `num_hashes = 120` total. With these settings, the
theoretical Jaccard threshold where the detection probability crosses 50% is
approximately 0.75. Adjust via config to trade recall vs precision.

### `get_signature` factory

`signature_fabric(num_bands, band_size, seed)` returns a closure
`get_signature(feature_set) → list[tuple[int, ...]]` of length `num_bands`.

The closure captures all `(a, b, p)` parameter triples, generated once from
`random.Random(seed)` — deterministic and reproducible.

---

## One Tier Pass — `run_tier`

```python
def run_tier(
    folders: dict[str, FolderRecord],
    components: tuple[str, ...],
    get_signature: Callable[[frozenset[tuple[Any, ...]]], list[tuple[int, ...]]],
    threshold: float,
) -> list[tuple[str, str, float]]:
```

### Steps

1. **Build feature sets.** For each folder, compute a feature tuple per file.
   All tier components (`folder_name`, `stem`, `ext`, `size`, `mtime`) are
   attributes of `FileRecord` — no special handling needed.
   ```python
   feature_set = frozenset(
       tuple(getattr(file, c) for c in components)
       for file in folder.files
   )
   ```
   Store as `dict[folder_id, frozenset]` — reused in step 4.

2. **Compute signatures.** For each folder call `get_signature(feature_set)`.
   Store as `dict[folder_id, list[tuple[int, ...]]]`.

3. **Build buckets.** For each folder and each `(band_index, band_tuple)` pair:
   ```python
   bucket_key = (band_index, band_tuple)
   buckets[bucket_key].add(folder_id)
   ```

4. **Enumerate candidate pairs.** Collect all unique `frozenset({a, b})` pairs
   from buckets with `len > 1`. Use a `set[frozenset[str]]` to deduplicate.

5. **Compute exact Jaccard.** For each candidate pair `(a, b)`:
   ```python
   jaccard = len(fs_a & fs_b) / len(fs_a | fs_b)
   ```
   Skip pairs where union is empty (both folders have no files).

6. **Filter by threshold.** Keep pairs where `jaccard >= threshold`.

7. **Return** `list[(folder_id_a, folder_id_b, jaccard)]`, unordered.

### Empty feature sets

A folder with only one distinct feature tuple is still a valid feature set of
size 1. Two such folders will produce a Jaccard of either 0.0 or 1.0 —
correct behaviour, no special case needed.

---

## Tiered Loop — `find_duplicates`

```python
def find_duplicates(
    folders: dict[str, FolderRecord],
    config: ReportConfig,
) -> list[MatchCandidate]:
```

### Tier definitions

```python
TIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "T1": ("folder_name", "stem", "ext", "size"),
    "T2": ("stem", "ext", "size", "mtime"),
    "T3": ("stem", "ext", "size"),
}
TIER_ORDER: list[str] = ["T1", "T2", "T3"]
```

These live in `constants.py`.

### Exclusion rule

After each tier, every `folder_id` that participates in **at least one pair
above the Jaccard threshold** is added to `excluded`. It will not be considered
in subsequent tiers.

Rationale: a folder already confidently matched at T1 (tight criteria) should
not be re-matched at T3 (looser criteria) as if it were unrecognised.

### Jaccard thresholds

Per-tier thresholds are read from `ReportConfig`. Suggested defaults:

| Tier | Default threshold |
|---|---|
| T1 | 0.80 |
| T2 | 0.70 |
| T3 | 0.60 |

### Output ordering

All collected `MatchCandidate` instances are sorted by descending
`max(folder_a.total_size, folder_b.total_size)` before return,
so the report leads with the highest-impact duplicates.

---

## `MatchCandidate` model (add to `models.py`)

```python
@dataclass(frozen=True, slots=True)
class MatchCandidate:
    tier: str            # "T1", "T2", or "T3"
    folder_id_a: str
    folder_id_b: str
    jaccard: float
```

---

## Configuration additions (add to `config.py` / `ReportConfig`)

```toml
[report]
output = "report.md"
input  = "merged.zip"

[report.lsh]
num_bands = 15
band_size  = 8
seed       = 42

[report.thresholds]
T1 = 0.80
T2 = 0.70
T3 = 0.60
```

---

## Error handling

| Situation | Behaviour |
|---|---|
| Folder has 0 files after materialisation | Skip, no warning |
| `jaccard` denominator is zero | Skip pair silently |
| `num_bands < 2` or `band_size < 2` in config | Raise `ValueError` at config load time |

---

## Module layout

```
analysis.py
├── _gen_abp(p, seed)               # infinite generator of (a, b, p) dicts
├── _get_hash(feature, a, b, p)     # universal hash → int
├── signature_fabric(...)           # returns get_signature closure
├── materialize_folders(...)        # vocab + metadata → dict[str, FolderRecord]
├── run_tier(...)                   # one LSH+Jaccard pass
└── find_duplicates(...)            # tiered loop, returns list[MatchCandidate]
```

Private helpers (`_gen_abp`, `_get_hash`) are not part of the public API.
`signature_fabric` is public because `commands/report.py` constructs it once
and passes it into `find_duplicates`.

---

## Testing notes

- `materialize_folders`: build a small synthetic metadata dict with known
  folder structure; assert correct `folder_id` keys and `file_count`.
- `run_tier`: create two `FolderRecord`s sharing 80% of their file feature
  tuples; assert they appear in the output with Jaccard ≥ 0.8.
- `find_duplicates`: construct three folders where two match on T1 and the
  third only matches one of them on T3; assert the T1 pair is excluded from
  T3 analysis.
- LSH false-negative rate: not tested in unit tests — covered by the Jaccard
  exact check (false negatives from banding are acceptable).