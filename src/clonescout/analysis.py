"""LSH + MinHash duplicate detection for CloneScout.

Folder materialisation, signature computation, and tiered matching.
See docs/blueprints/analysis-blueprint.md for the full specification.
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import random
from typing import TYPE_CHECKING, Any

from clonescout.models import FileRecord, FolderRecord, MatchCandidate

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator


# ---------------------------------------------------------------------------
# Folder materialisation
# ---------------------------------------------------------------------------


def build_folders(
    vocab: list[str],
    metadata: dict[Any, Any],
) -> dict[str, FolderRecord]:
    """Reconstruct FolderRecords from vocabulary-indexed metadata.

    The metadata dict uses the nested layout produced by storage.py::

        metadata[node: str]
                [anchor_idx: int]
                [folder_parent_idx: int]
                [folder_name_idx: int]
                [suffix_idx: int]
                [stem_idx: int]  →  (ext: str, size: int, mtime: int)

    String dimensions (anchor, folder_parent, folder_name, suffix, stem)
    are stored as integer indices into *vocab*.  Node and the leaf tuple
    (ext, size, mtime) are stored as raw values.

    For each unique (node, anchor, folder_parent, folder_name) combination,
    all FileRecord leaves are collected into one FolderRecord.  The result
    is keyed by FolderRecord.folder_id.

    Edge cases:

    - Folders with zero files are skipped (can arise from partial scans).
    - Duplicate folder_id values log a WARNING; the first occurrence is kept.

    Args:
        vocab: Ordered list of strings, as produced by Vocabulary.as_list().
            Index 0 is always "" (POSIX anchor); indices 1-26 are Windows
            drive letters "A:" through "Z:".
        metadata: Nested metadata dict with integer keys, as returned by
            storage.read_zip() after _keys_to_int() conversion.

    Returns:
        A dict mapping folder_id → FolderRecord for every non-empty folder
        found in the metadata.
    """
    result: dict[str, FolderRecord] = {}

    for node, node_dict in metadata.items():
        for anchor_idx, anchor_dict in node_dict.items():
            anchor = vocab[anchor_idx]
            for fp_idx, fp_dict in anchor_dict.items():
                folder_parent = vocab[fp_idx]
                for fn_idx, fn_dict in fp_dict.items():
                    folder_name = vocab[fn_idx]

                    files: list[FileRecord] = []
                    for suffix_idx, suffix_dict in fn_dict.items():
                        suffix = vocab[suffix_idx]
                        for stem_idx, leaf in suffix_dict.items():
                            stem = vocab[stem_idx]
                            ext, size, mtime = leaf
                            files.append(
                                FileRecord(
                                    anchor=anchor,
                                    folder_parent=folder_parent,
                                    folder_name=folder_name,
                                    stem=stem,
                                    suffix=suffix,
                                    ext=ext,
                                    size=size,
                                    mtime=mtime,
                                )
                            )

                    if not files:
                        continue

                    fr = FolderRecord(
                        node=node,
                        anchor=anchor,
                        folder_parent=folder_parent,
                        folder_name=folder_name,
                        files=tuple(files),
                    )
                    if fr.folder_id in result:
                        logging.warning(
                            "Duplicate folder_id encountered, keeping first"
                            " occurrence: %s",
                            fr.folder_id,
                        )
                    else:
                        result[fr.folder_id] = fr

    return result


# ---------------------------------------------------------------------------
# LSH + MinHash
# ---------------------------------------------------------------------------

_MERSENNE_PRIME: int = (1 << 61) - 1


def _gen_abp(p: int, seed: int | None = None) -> Iterator[dict[str, int]]:
    """Yield an infinite stream of (a, b, p) parameter dicts.

    Each dict parameterises one member of the universal hash family:
        h(x) = (a * x + b) mod p

    a is drawn from [1, p-1] (must be non-zero to avoid the trivial hash).
    b is drawn from [0, p-1].
    p is passed through unchanged so callers can unpack a single dict.

    Args:
        p: The prime modulus.  Should be _MERSENNE_PRIME in production.
        seed: Optional RNG seed for reproducibility.

    Yields:
        Dicts with keys "a", "b", "p".
    """
    rng = random.Random(seed)
    while True:
        yield {
            "a": rng.randint(1, p - 1),
            "b": rng.randint(0, p - 1),
            "p": p,
        }


def _get_hash(feature: Any, a: int, b: int, p: int) -> int:
    """Hash one feature value using a single (a, b, p) parameter triple.

    The feature is first serialised to bytes via repr() so it can be
    anything hashable — tuples, strings, ints, nested structures.
    A 64-bit Blake2b digest is then mapped into the hash field:

        h = (a * int_from_digest + b) mod p

    Args:
        feature: Any Python value.  repr() must be deterministic for it.
        a: Multiplier in [1, p-1].
        b: Addend in [0, p-1].
        p: Prime modulus.

    Returns:
        An integer in [0, p-1].
    """
    data = repr(feature).encode()
    digest = hashlib.blake2b(data, digest_size=8).digest()
    int_hash = int.from_bytes(digest, "little")
    return (a * int_hash + b) % p


def signature_fabric(
    num_bands: int,
    band_size: int,
    seed: int | None = None,
    p: int = _MERSENNE_PRIME,
) -> Callable[[frozenset[Any]], list[tuple[int, ...]]]:
    """Build a get_signature closure with fixed random parameters.

    The closure captures num_bands * band_size (a, b, p) triples — one per
    slot, generated once from seed.  Calling the closure on a feature set
    returns a MinHash signature already split into bands, ready for LSH
    bucketing.

    Why a closure?  The parameters are expensive to generate and must be
    identical for every folder in a tier pass.  Generating once and closing
    over them avoids re-seeding on every call.

    Args:
        num_bands: Number of LSH bands.  More bands → higher recall,
            more buckets, more candidate pairs to verify.
        band_size: Number of MinHash values per band.  Larger band_size →
            higher precision (harder to land in the same bucket by chance).
        seed: RNG seed.  Use a fixed value (e.g. 42) for reproducibility.
        p: Prime modulus.  Defaults to _MERSENNE_PRIME.

    Returns:
        A closure ``get_signature(feature_set) → list[tuple[int, ...]]``.
        The returned list has length num_bands; each element is a tuple of
        band_size integers — the MinHash values for that band.

    Raises:
        ValueError: If num_bands < 2 or band_size < 2.
    """
    if num_bands < 2:
        raise ValueError(f"num_bands must be >= 2, got {num_bands}")
    if band_size < 2:
        raise ValueError(f"band_size must be >= 2, got {band_size}")

    params: list[dict[str, int]] = list(
        itertools.islice(_gen_abp(p, seed), num_bands * band_size)
    )

    def get_signature(feature_set: frozenset[Any]) -> list[tuple[int, ...]]:
        """Compute a banded MinHash signature for a feature set.

        For each of the num_bands * band_size hash functions, the MinHash
        value is min(h(f) for f in feature_set).  The resulting flat list
        is then sliced into num_bands bands.

        An empty feature_set produces a signature of all zeros — two empty
        folders will match at Jaccard 1.0 (both have no files, so they are
        identical by definition).

        Args:
            feature_set: The set of feature tuples for one folder.

        Returns:
            List of num_bands tuples, each of length band_size.
        """
        if not feature_set:
            zero_band = tuple(0 for _ in range(band_size))
            return [zero_band] * num_bands

        minhashes: list[int] = [
            min(_get_hash(f, **abp) for f in feature_set) for abp in params
        ]

        bands: list[tuple[int, ...]] = []
        it = iter(minhashes)
        for _ in range(num_bands):
            bands.append(tuple(itertools.islice(it, band_size)))
        return bands

    return get_signature


# ---------------------------------------------------------------------------
# Core detection
# ---------------------------------------------------------------------------


def run_tier(
    folders: dict[str, FolderRecord],
    components: tuple[str, ...],
    get_signature: Callable[[frozenset[Any]], list[tuple[int, ...]]],
    threshold: float,
) -> list[tuple[str, str, float, int]]:
    """Run one LSH + exact-Jaccard pass over a set of folders.

    Steps:

    1. Build a feature set for each folder from the FileRecord attributes
       named in *components*.  Alongside, record ``FileRecord.size`` keyed by
       feature tuple — this is used to compute *shared_size* independently of
       which attributes appear in *components*, so adding a tier without
       ``size`` as a component does not break the calculation.
    2. Compute a banded MinHash signature for each feature set.
    3. Group folders into buckets by ``(band_index, band_tuple)``.
    4. Enumerate all unique candidate pairs from buckets with >= 2 members.
       A pair may collide in many buckets; deduplicate before verification.
    5. Compute exact Jaccard and shared_size for each candidate pair.
    6. Return pairs whose Jaccard meets *threshold*.

    When two FileRecords in the same folder produce the same feature tuple
    (rare but possible, e.g. two files with identical stem/ext/size), the
    last one's size wins in the size map — an acceptable approximation, as
    the duplicated tuple counts once in the frozenset anyway.

    Args:
        folders: Active folders for this tier, keyed by folder_id.
            Folders in the exclusion set must be removed by the caller.
        components: FileRecord attribute names used to build feature tuples,
            e.g. ``("stem", "ext", "size")`` for T3.
        get_signature: Closure returned by signature_fabric().
        threshold: Minimum Jaccard similarity to report a pair as a match.

    Returns:
        List of ``(folder_id_a, folder_id_b, jaccard, shared_size)`` tuples
        where ``folder_id_a <= folder_id_b`` lexicographically.  Unordered.
    """
    feature_sets: dict[str, frozenset[Any]] = {}
    feature_sizes: dict[str, dict[tuple[Any, ...], int]] = {}
    signatures: dict[str, list[tuple[int, ...]]] = {}

    for folder_id, folder_record in folders.items():
        size_map: dict[tuple[Any, ...], int] = {}
        for f in folder_record.files:
            ft = tuple(getattr(f, c) for c in components)
            size_map[ft] = f.size
        feature_sets[folder_id] = frozenset(size_map)
        feature_sizes[folder_id] = size_map
        signatures[folder_id] = get_signature(frozenset(size_map))

    buckets: dict[tuple[int, tuple[int, ...]], set[str]] = {}
    for folder_id, bands in signatures.items():
        for band_idx, band in enumerate(bands):
            key = (band_idx, band)
            buckets.setdefault(key, set()).add(folder_id)

    candidate_pairs: set[frozenset[str]] = set()
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for a, b in itertools.combinations(bucket, 2):
            candidate_pairs.add(frozenset({a, b}))

    results: list[tuple[str, str, float, int]] = []
    for pair in candidate_pairs:
        a, b = sorted(pair)
        fs_a = feature_sets[a]
        fs_b = feature_sets[b]
        union_size = len(fs_a | fs_b)
        if union_size == 0:
            continue
        intersection = fs_a & fs_b
        jaccard = len(intersection) / union_size
        if jaccard >= threshold:
            shared_size = sum(feature_sizes[a][ft] for ft in intersection)
            results.append((a, b, jaccard, shared_size))

    return results


def find_duplicates(
    folders: dict[str, FolderRecord],
    tier_components: dict[str, tuple[str, ...]],
    tier_order: list[str],
    thresholds: dict[str, float],
    get_signature: Callable[[frozenset[Any]], list[tuple[int, ...]]],
) -> list[MatchCandidate]:
    """Run the full tiered duplicate detection loop.

    Processes tiers in *tier_order*.  After each tier, every folder_id that
    participated in at least one matched pair is added to the exclusion set
    and will not appear in subsequent tiers.  This ensures each folder is
    reported under its strongest (earliest) tier match only.

    Within each tier, results are sorted by descending *shared_size* so the
    highest-impact duplicates appear first.  Tier order is preserved in the
    returned list (all T1 matches, then all T2, then all T3).

    Args:
        folders: All materialised FolderRecords from build_folders(), keyed
            by folder_id.
        tier_components: Maps tier name → tuple of FileRecord attribute names.
            Use TIER_COMPONENTS for the standard T1/T2/T3 definitions.
        tier_order: Processing order, e.g. TIER_ORDER = ["T1", "T2", "T3"].
        thresholds: Per-tier Jaccard threshold.  Use TIER_THRESHOLDS for
            defaults.
        get_signature: Closure from signature_fabric().

    Returns:
        List of MatchCandidate instances grouped by tier (T1 first) and
        within each tier sorted by descending shared_size.
    """
    excluded: set[str] = set()
    all_matches: list[MatchCandidate] = []

    for tier in tier_order:
        active = {fid: f for fid, f in folders.items() if fid not in excluded}
        if not active:
            break

        pairs = run_tier(active, tier_components[tier], get_signature, thresholds[tier])
        pairs.sort(key=lambda t: -t[3])

        for a, b, score, shared_size in pairs:
            excluded.add(a)
            excluded.add(b)
            all_matches.append(
                MatchCandidate(
                    tier=tier,
                    folder_id_a=a,
                    folder_id_b=b,
                    jaccard=score,
                    shared_size=shared_size,
                )
            )

    return all_matches
