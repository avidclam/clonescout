# Blueprint — `analysis.py`

> Specification for the duplicate directory detection module in CloneScout.
> Implements LSH + MinHash with tiered matching (T1 → T2 → T3).
> Read alongside `PROJECT.md` and `AGENTS.md` before implementing.
>
> **Authoritative reference:** `analysis_snippet.py` in the project root.
> This blueprint describes the same logic in prose.  When in doubt, the
> snippet takes precedence.

---

## Responsibilities

`analysis.py` takes a merged (or single-scan) metadata ZIP and produces a list
of duplicate/near-duplicate folder pairs with tier labels, Jaccard scores, and
shared sizes.

It does **not** read or write ZIP files — that is `storage.py`'s job.
It **does** own folder materialisation from the decoded metadata dict.

---

## Public API

```python
def build_folders(
    vocab: list[str],
    metadata: dict[Any, Any],
) -> dict[str, FolderRecord]:
    ...

def find_duplicates(
    folders: dict[str, FolderRecord],
    tier_components: dict[str, tuple[str, ...]],
    tier_order: list[str],
    thresholds: dict[str, float],
    get_signature: Callable[[frozenset[Any]], list[tuple[int, ...]]],
) -> list[MatchCandidate]:
    ...
```

`find_duplicates` is the single entry point called by `commands/report.py`.
It runs the full T1 → T2 → T3 tiered loop and returns all matched pairs.

`commands/report.py` is responsible for constructing the `get_signature`
closure via `signature_fabric()` and passing it in, along with
`TIER_COMPONENTS`, `TIER_ORDER`, and `TIER_THRESHOLDS` from `constants.py`.

---

## Data Flow

```
read_zip(path)
    │  returns (vocabulary: Vocabulary, metadata: dict, info: dict)
    │
    │  vocabulary.as_list() → list[str]
    ▼
build_folders(vocab, metadata)
    │  Decodes nested index dict → dict[folder_id, FolderRecord]
    ▼
find_duplicates(folders, tier_components, tier_order, thresholds, get_signature)
    │
    ├─ T1 pass: run_tier(active_folders, T1_COMPONENTS, get_signature, threshold_t1)
    │       │  returns list[(folder_id_a, folder_id_b, jaccard, shared_size)]
    │       │
    │       └─ excluded |= all folder_ids that appear in any returned pair
    │
    ├─ T2 pass: same, over (folders − excluded)
    │
    └─ T3 pass: same, over (folders − excluded)
         │
         ▼
    list[MatchCandidate]  (tiers in order, within each tier sorted by
                           descending shared_size)
```

---

## Folder Materialisation

`build_folders` traverses the metadata nested dict and reconstructs
`FolderRecord` instances using the vocabulary list for index → string lookups.

The function accepts `vocab: list[str]` directly (as returned by
`Vocabulary.as_list()` / `storage.read_zip()`), not a `Vocabulary` object.
This avoids an unnecessary dependency on `storage.py`.

### Traversal order

```
metadata[node: str]
         [anchor_idx: int]        → vocab[anchor_idx]
         [folder_parent_idx: int] → vocab[folder_parent_idx]
         [folder_name_idx: int]   → vocab[folder_name_idx]
         [suffix_idx: int]        → vocab[suffix_idx]
         [stem_idx: int]          → (ext: str, size: int, mtime: int)
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

`blake2b_int` is the 8-byte little-endian integer of
`hashlib.blake2b(repr(x).encode(), digest_size=8).digest()`.

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

| Parameter | Default | Constant name |
|---|---|---|
| `num_bands` | 15 | `LSH_NUM_BANDS` |
| `band_size` | 8 | `LSH_BAND_SIZE` |
| `seed` | 42 | `LSH_SEED` |

These default to `num_hashes = 120` total. With these settings, the
theoretical Jaccard threshold where the detection probability crosses 50% is
approximately 0.75.

### `signature_fabric` factory

`signature_fabric(num_bands, band_size, seed)` returns a closure
`get_signature(feature_set) → list[tuple[int, ...]]` of length `num_bands`.

The closure captures all `(a, b, p)` parameter triples, generated once from
`random.Random(seed)` — deterministic and reproducible.

Raises `ValueError` if `num_bands < 2` or `band_size < 2`.

---

## One Tier Pass — `run_tier`

```python
def run_tier(
    folders: dict[str, FolderRecord],
    components: tuple[str, ...],
    get_signature: Callable[[frozenset[tuple[Any, ...]]], list[tuple[int, ...]]],
    threshold: float,
) -> list[tuple[str, str, float, int]]:
```

Returns `list[(folder_id_a, folder_id_b, jaccard, shared_size)]` where
`folder_id_a <= folder_id_b` lexicographically.

---

### Feature tuple collisions within a folder

When two files in the same folder produce identical feature tuples — for
example, two files with the same stem, extension, and size — they collapse
into a single entry in the `frozenset`.  The `size_map` retains the size of
whichever file was processed last.

This is an intentional approximation, not a bug.  Such collisions are so rare 
in practice, their effect on duplicate detection is negligible.

---


### Steps

1. **Build feature sets and size maps.**  For each folder, compute a feature
   tuple per file from the attributes named in `components`.  Alongside,
   record `FileRecord.size` keyed by feature tuple — used in step 5 to
   compute `shared_size` independently of which attributes appear in
   `components`.
   ```python
   size_map: dict[tuple, int] = {}
   for f in folder.files:
       ft = tuple(getattr(f, c) for c in components)
       size_map[ft] = f.size   # last writer wins on collision (rare)
   feature_set = frozenset(size_map)
   ```

2. **Compute signatures.** For each folder call `get_signature(feature_set)`.

3. **Build buckets.** For each folder and each `(band_index, band_tuple)` pair:
   ```python
   bucket_key = (band_index, band_tuple)
   buckets[bucket_key].add(folder_id)
   ```

4. **Enumerate candidate pairs.** Collect all unique `frozenset({a, b})` pairs
   from buckets with `len > 1`. Use a `set[frozenset[str]]` to deduplicate.

5. **Compute exact Jaccard and shared_size.** For each candidate pair `(a, b)`:
   ```python
   intersection = fs_a & fs_b
   jaccard = len(intersection) / len(fs_a | fs_b)
   shared_size = sum(size_map_a[ft] for ft in intersection)
   ```
   Skip pairs where union is empty.  For all current tiers, `size` is a
   component, so `size_map_a[ft]` equals `size_map_b[ft]` by construction —
   taking it from folder A is exact, not an approximation.

6. **Filter by threshold.** Keep pairs where `jaccard >= threshold`.

7. **Return** `list[(folder_id_a, folder_id_b, jaccard, shared_size)]`,
   unordered, with `folder_id_a <= folder_id_b`.

### Empty feature sets

A folder with only one distinct feature tuple is a valid feature set of size 1.
Two such folders produce a Jaccard of 0.0 or 1.0 — correct, no special case needed.

---

## Tiered Loop — `find_duplicates`

### Tier definitions (live in `constants.py`)

```python
TIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "T1": ("folder_name", "stem", "ext", "size"),
    "T2": ("stem", "ext", "size", "mtime"),
    "T3": ("stem", "ext", "size"),
}
TIER_ORDER: list[str] = ["T1", "T2", "T3"]
TIER_THRESHOLDS: dict[str, float] = {"T1": 0.80, "T2": 0.70, "T3": 0.60}
```

### Exclusion rule

After each tier, every `folder_id` that participates in **at least one pair
above the Jaccard threshold** is added to `excluded`. It will not be considered
in subsequent tiers.

Rationale: a folder already confidently matched at T1 (tight criteria) should
not be re-matched at T3 (looser criteria) as if it were unrecognised.

### Jaccard thresholds

| Tier | Default threshold |
|---|---|
| T1 | 0.80 |
| T2 | 0.70 |
| T3 | 0.60 |

### Output ordering

Within each tier, `MatchCandidate` instances are sorted by descending
`shared_size` before being appended to the result list.  Tier order (T1, then
T2, then T3) is preserved — all T1 matches appear before any T2 matches.

`shared_size` is used rather than `max(total_size)` because it directly
represents the recoverable space from deduplication, making it a more
actionable sort key for the user.

---

## Error handling

| Situation | Behaviour |
|---|---|
| Folder has 0 files after materialisation | Skip silently |
| Duplicate `folder_id` in metadata | Log `WARNING`, keep first occurrence |
| `jaccard` denominator is zero | Skip pair silently |
| `num_bands < 2` or `band_size < 2` | `ValueError` raised by `signature_fabric` |

---

## Module layout

```
analysis.py
├── _gen_abp(p, seed)               # infinite generator of (a, b, p) dicts
├── _get_hash(feature, a, b, p)     # universal hash → int
├── signature_fabric(...)           # returns get_signature closure
├── build_folders(...)              # vocab + metadata → dict[str, FolderRecord]
├── run_tier(...)                   # one LSH+Jaccard pass
└── find_duplicates(...)            # tiered loop, returns list[MatchCandidate]
```

Private helpers (`_gen_abp`, `_get_hash`) are not part of the public API.
`signature_fabric` is public because `commands/report.py` constructs it once
and passes it into `find_duplicates`.

---

## Testing notes

- `build_folders`: use the `VOCAB` / `METADATA` literals from the smoke test
  in `analysis_snippet.py` as a ready-made fixture; assert correct `folder_id`
  keys, `file_count`, and `total_size`.
- `run_tier`: create two `FolderRecord`s sharing 80% of their file feature
  tuples; assert they appear in the output with Jaccard ≥ 0.8 and correct
  `shared_size`.
- `find_duplicates`: construct three folders where two match on T1 and the
  third only matches one of them on T3; assert the T1 pair is excluded from
  T3 analysis.
- LSH false-negative rate: not tested in unit tests — covered by the Jaccard
  exact check (false negatives from banding are acceptable).
