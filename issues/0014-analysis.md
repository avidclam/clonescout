# feat: implement `analysis.py` — folder materialisation and duplicate detection

## Context

This issue implements `src/clonescout/analysis.py`.  The full logic is
specified in `docs/blueprints/analysis-blueprint.md` and is available as a
running reference implementation in `analysis_snippet.py`.  Read both before
starting.

**Prerequisite:** `MatchCandidate` in `models.py` must be merged first.

## Deliverables

### `src/clonescout/constants.py` — additions

Add tier definitions:

```python
TIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "T1": ("folder_name", "stem", "ext", "size"),
    "T2": ("stem", "ext", "size", "mtime"),
    "T3": ("stem", "ext", "size"),
}
TIER_ORDER: list[str] = ["T1", "T2", "T3"]
TIER_THRESHOLDS: dict[str, float] = {"T1": 0.80, "T2": 0.70, "T3": 0.60}

LSH_NUM_BANDS: int = 15
LSH_BAND_SIZE: int = 8
LSH_SEED: int = 42
```

### `src/clonescout/analysis.py`

Implement the following, in this order.  The reference implementation in
`analysis_snippet.py` is authoritative for all details — use it directly,
adapting only the imports.

#### Private helpers

```python
_MERSENNE_PRIME: int = (1 << 61) - 1

def _gen_abp(p: int, seed: int | None = None) -> ...:
    """Infinite generator of (a, b, p) parameter dicts for the universal hash family."""

def _get_hash(feature: Any, a: int, b: int, p: int) -> int:
    """Hash one feature value: blake2b digest mapped into the hash field."""
```

#### `signature_fabric`

```python
def signature_fabric(
    num_bands: int,
    band_size: int,
    seed: int | None = None,
    p: int = _MERSENNE_PRIME,
) -> Callable[[frozenset[Any]], list[tuple[int, ...]]]:
```

Returns a `get_signature` closure that computes banded MinHash signatures.
Raises `ValueError` if `num_bands < 2` or `band_size < 2`.

#### `build_folders`

```python
def build_folders(
    vocab: list[str],
    metadata: dict[Any, Any],
) -> dict[str, FolderRecord]:
```

Reconstructs `FolderRecord` instances from vocabulary-indexed metadata.
Skips folders with zero files.  Logs `WARNING` and keeps the first occurrence
on duplicate `folder_id`.

#### `run_tier`

```python
def run_tier(
    folders: dict[str, FolderRecord],
    components: tuple[str, ...],
    get_signature: Callable[[frozenset[Any]], list[tuple[int, ...]]],
    threshold: float,
) -> list[tuple[str, str, float, int]]:
```

One LSH + exact-Jaccard pass.  Returns
`(folder_id_a, folder_id_b, jaccard, shared_size)` tuples where
`folder_id_a <= folder_id_b` lexicographically.

`shared_size` is computed from `FileRecord.size` independently of which
attributes appear in `components` — see the blueprint and snippet for the
`size_map` pattern.

#### `find_duplicates`

```python
def find_duplicates(
    folders: dict[str, FolderRecord],
    tier_components: dict[str, tuple[str, ...]],
    tier_order: list[str],
    thresholds: dict[str, float],
    get_signature: Callable[[frozenset[Any]], list[tuple[int, ...]]],
) -> list[MatchCandidate]:
```

Tiered loop over `tier_order`.  After each tier, all participating folder IDs
are added to `excluded`.  Within each tier, results are sorted by descending
`shared_size` before appending.  Tier order is preserved in the output.

## Imports

```python
from clonescout.models import FileRecord, FolderRecord, MatchCandidate
from clonescout.constants import (
    TIER_COMPONENTS, TIER_ORDER, TIER_THRESHOLDS,
    LSH_NUM_BANDS, LSH_BAND_SIZE, LSH_SEED,
)
```

## Acceptance criteria

- `from clonescout.analysis import build_folders, find_duplicates, signature_fabric`
  works without error.
- Running `analysis_snippet.py` directly (`python analysis_snippet.py`) still
  produces the same output — the snippet is an independent self-check.
- `ruff`, `mypy`, `pytest` all pass (tests come in forthcoming issues).
