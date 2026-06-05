"""
LSH + MinHash core for CloneScout — annotated reference snippet.

This file is a complete, self-contained implementation of the folder
materialisation, duplicate detection, and report formatting logic that
will move into src/clonescout/analysis.py and src/clonescout/report.py.

Data flow::

    vocab (list[str]) + metadata (nested dict)
        │
        ▼
    build_folders()          →  dict[folder_id, FolderRecord]
        │
        ▼
    find_duplicates()        →  list[MatchCandidate]
        │
        ▼
    format_report()          →  str

The file uses inline copies of FileRecord / FolderRecord / MatchCandidate
so it runs standalone without the full project installed.  When wiring into
the project:

    from clonescout.models import FileRecord, FolderRecord, MatchCandidate

The smoke test at the bottom uses real vocab.json / metadata.json content
produced by ``clonescout scan`` + ``clonescout merge`` on two machines:

  - windows: C:\\smoke\\Users\\alice\\{contracts, photos\\2021}
  - linux:   /smoke/backup/photos/2021_copy

Conventions mirror AGENTS.md:
  - Python 3.11, stdlib only, fully type-hinted, Google-style docstrings.
  - Private helpers prefixed with _.
  - No external dependencies.
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import random
from collections import Counter
from dataclasses import dataclass
from typing import Any
from collections.abc import Callable, Iterator


# ---------------------------------------------------------------------------
# Inline model definitions — identical to models.py in the real project.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class FileRecord:
    """A single file's metadata, suitable for vocabulary-indexed storage.

    Node is not stored here; it is applied at the metadata-insertion stage.

    Attributes:
        anchor: Empty string on POSIX; drive letter (e.g. "C:") on Windows;
            archive path for files inside archives.
        folder_parent: POSIX path to the folder's parent, no leading/trailing
            slash.  Empty string for top-level folders.
        folder_name: Name of the containing directory.
        stem: File name without extension, as in pathlib.Path.stem.
        suffix: File extension including the dot, e.g. ".jpg".
        ext: Extension without the dot, uppercased, e.g. "JPG".
        size: File size in bytes.
        mtime: File modification time as a UNIX timestamp (integer seconds).
    """

    anchor: str
    folder_parent: str
    folder_name: str
    stem: str
    suffix: str
    ext: str
    size: int
    mtime: int


@dataclass(frozen=True, slots=True)
class FolderRecord:
    """A directory's identity and its file members.

    Created from the nested metadata dict by build_folders().  Node is
    included here (unlike FileRecord) because folder identity must be
    unique across machines and scan runs.

    Attributes:
        node: User-assigned machine name from the scan config.
        anchor: Same meaning as in FileRecord.
        folder_parent: POSIX path to this folder's parent, no
            leading/trailing slash.
        folder_name: Name of this directory.
        files: All FileRecord instances that belong to this folder.
    """

    node: str
    anchor: str
    folder_parent: str
    folder_name: str
    files: tuple[FileRecord, ...]

    @property
    def folder_id(self) -> str:
        """Unique, human-readable identifier for this folder across all nodes.

        Format: ``node:anchor/[folder_parent[/folder_name]|folder_name]``.

        Examples:
            ``"linux:/"``
            ``"windows:C:/"``
            ``"linux:/smoke/backup/photos/2021_copy"``
            ``"windows:C:/smoke/Users/alice/contracts"``
        """
        result = f"{self.node}:{self.anchor}/"
        if self.folder_parent:
            result += self.folder_parent
            if self.folder_name:
                result += f"/{self.folder_name}"
        else:
            result += self.folder_name
        return result

    @property
    def total_size(self) -> int:
        """Sum of all contained files' sizes in bytes."""
        return sum(f.size for f in self.files)

    @property
    def file_count(self) -> int:
        """Number of files in this folder."""
        return len(self.files)

    @property
    def min_mtime(self) -> int:
        """Earliest modification timestamp among all files."""
        return min(f.mtime for f in self.files)

    @property
    def max_mtime(self) -> int:
        """Latest modification timestamp among all files."""
        return max(f.mtime for f in self.files)

    @property
    def ext_distribution(self) -> dict[str, int]:
        """Count of files grouped by extension (uppercased, no dot)."""
        return dict(Counter(f.ext for f in self.files))


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    """One matched folder pair produced by the tiered duplicate detection.

    Attributes:
        tier: Tier label at which the match was found: "T1", "T2", or "T3".
        folder_id_a: Folder ID of the first folder (lexicographically smaller).
        folder_id_b: Folder ID of the second folder.
        jaccard: Exact Jaccard similarity of the two feature sets, in [0, 1].
        shared_size: Sum of FileRecord.size for feature tuples present in
            both folders' feature sets.  Represents the amount of data that
            the two folders have in common.
    """

    tier: str
    folder_id_a: str
    folder_id_b: str
    jaccard: float
    shared_size: int


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

# Mersenne prime used as the hash field modulus.
# 2^61 - 1 is prime, fits in 64 bits, and is large enough that collisions
# from the universal hash family are negligible in practice.
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
    # Little-endian so the low bytes (which vary most) land in the LSBs.
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
# Tier definitions (also live in constants.py in the real project)
# ---------------------------------------------------------------------------

TIER_COMPONENTS: dict[str, tuple[str, ...]] = {
    "T1": ("folder_name", "stem", "ext", "size"),
    "T2": ("stem", "ext", "size", "mtime"),
    "T3": ("stem", "ext", "size"),
}
TIER_ORDER: list[str] = ["T1", "T2", "T3"]
TIER_THRESHOLDS: dict[str, float] = {"T1": 0.80, "T2": 0.70, "T3": 0.60}


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
    # Step 1 + 2: build feature sets, size maps, and signatures in one pass.
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

    # Step 3: build LSH buckets.
    buckets: dict[tuple[int, tuple[int, ...]], set[str]] = {}
    for folder_id, bands in signatures.items():
        for band_idx, band in enumerate(bands):
            key = (band_idx, band)
            buckets.setdefault(key, set()).add(folder_id)

    # Step 4: collect unique candidate pairs.
    # frozenset({a, b}) as key deduplicates (a, b) vs (b, a) and handles
    # the same pair arriving from multiple buckets.
    candidate_pairs: set[frozenset[str]] = set()
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        for a, b in itertools.combinations(bucket, 2):
            candidate_pairs.add(frozenset({a, b}))

    # Step 5 + 6: exact Jaccard, shared_size, threshold filter.
    results: list[tuple[str, str, float, int]] = []
    for pair in candidate_pairs:
        a, b = sorted(pair)  # folder_id_a <= folder_id_b, always
        fs_a = feature_sets[a]
        fs_b = feature_sets[b]
        union_size = len(fs_a | fs_b)
        if union_size == 0:
            continue
        intersection = fs_a & fs_b
        jaccard = len(intersection) / union_size
        if jaccard >= threshold:
            # For feature tuples that include "size" as a component (all
            # current tiers), the size value is identical in both folders by
            # construction, so taking it from folder A is exact, not an
            # approximation.
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
        pairs.sort(key=lambda t: -t[3])  # descending shared_size within tier

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


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _fmt_size(n: int) -> str:
    """Format a byte count as a human-readable string, like ``du -sh``.

    Uses binary prefixes (1 KiB = 1024 bytes).  Values below 1 KiB are
    shown as whole bytes.  Larger values are shown with one decimal place.

    Args:
        n: Non-negative byte count.

    Returns:
        A compact string such as ``"892 B"``, ``"1.5 MiB"``, ``"3.2 GiB"``.
    """
    if n < 1024:
        return f"{n} B"
    value: float = float(n)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        value /= 1024
        if value < 1024:
            return f"{value:.1f} {unit}"
    return f"{value:.1f} TiB"


def format_report(
    matches: list[MatchCandidate],
    folders: dict[str, FolderRecord],
) -> str:
    """Render duplicate-detection results as a plain-text report.

    Output structure::

        Tier: T1
        1. Shared: 10.5 KiB  Jaccard: 0.83
           linux:/smoke/backup/photos/2021_copy        12.0 KiB
           windows:C:/smoke/Users/alice/photos/2021    15.0 KiB
           
        2. ...

        Tier: T2
        ...

    Rules:

    - Tiers are printed in the order they first appear in *matches*
      (normally T1, T2, T3).
    - Within each tier, pairs are in the order they appear in *matches*
      (find_duplicates already sorted by descending shared_size).
    - Within each pair, folder_id_a is always printed first; run_tier
      guarantees folder_id_a <= folder_id_b lexicographically.
    - Jaccard is rounded to two decimal places.
    - Sizes are formatted with _fmt_size (human-readable binary prefixes).

    Args:
        matches: List of MatchCandidate instances from find_duplicates().
        folders: All FolderRecords from build_folders(), used to look up
            each folder's total_size.

    Returns:
        A formatted multi-line string, or an empty string if matches is empty.
    """
    if not matches:
        return ""

    # Group by tier, preserving first-appearance order.
    tier_order: list[str] = []
    by_tier: dict[str, list[MatchCandidate]] = {}
    for m in matches:
        if m.tier not in by_tier:
            tier_order.append(m.tier)
            by_tier[m.tier] = []
        by_tier[m.tier].append(m)

    lines: list[str] = []
    for tier in tier_order:
        lines.append(f"Tier: {tier}")
        for idx, m in enumerate(by_tier[tier], start=1):
            size_a = getattr(folders.get(m.folder_id_a), "total_size", 0)
            size_b = getattr(folders.get(m.folder_id_b), "total_size", 0)
            lines.append(
                f"{idx}. Shared: {_fmt_size(m.shared_size)}"
                f"  Jaccard: {m.jaccard:.2f}"
            )
            lines.append(f"   {m.folder_id_a:<60}  {_fmt_size(size_a)}")
            lines.append(f"   {m.folder_id_b:<60}  {_fmt_size(size_b)}")
        lines.append("")  # blank line between tiers

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# Smoke test — run this file directly to verify the full pipeline.
#
# Test data comes from a real clonescout scan + merge of two machines:
#
#   windows  C:\smoke\
#            └── Users\alice\
#                ├── contracts\
#                │   contract_2020.pdf  (8192 B)
#                │   contract_2021.pdf  (9216 B)
#                └── photos\2021\
#                    IMG_001.jpg (1024 B)  IMG_002.jpg (2048 B)
#                    IMG_003.jpg (3072 B)  IMG_004.jpg (4096 B)
#                    IMG_005.jpg (5120 B)
#
#   linux    /smoke/backup/photos/2021_copy/
#                    IMG_001.jpg (1024 B)  IMG_002.jpg (2048 B)
#                    IMG_003.jpg (3072 B)  IMG_004.jpg (4096 B)
#                    IMG_005.jpg (5120 B)
#                    THUMB.png   (512 B)   ← extra file, not on windows
#
# Expected result: photos/2021 ↔ 2021_copy matched on T3 (folder names
# differ, so T1 misses; mtimes differ, so T2 misses; T3 matches on
# stem+ext+size).  Shared size = 1024+2048+3072+4096+5120 = 15360 B.
# contracts is unmatched.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # -- vocab.json content (as produced by clonescout merge) ----------------
    VOCAB: list[str] = [
        "",           # 0  — POSIX anchor
        "A:", "B:", "C:", "D:", "E:", "F:", "G:", "H:", "I:", "J:", "K:", "L:", "M:",
        "N:", "O:", "P:", "Q:", "R:", "S:", "T:", "U:", "V:", "W:", "X:", "Y:", "Z:",
        # 27 onward — strings encountered during scan
        "smoke/Users/alice",            # 27
        "contracts",                    # 28
        ".pdf",                         # 29
        "contract_2020",                # 30
        "contract_2021",                # 31
        "smoke/Users/alice/photos",     # 32
        "2021",                         # 33
        ".jpg",                         # 34
        "IMG_001",                      # 35
        "IMG_002",                      # 36
        "IMG_003",                      # 37
        "IMG_004",                      # 38
        "IMG_005",                      # 39
        "smoke/backup/photos",          # 40
        "2021_copy",                    # 41
        ".png",                         # 42
        "THUMB",                        # 43
    ]

    # -- metadata.json content (integer keys, as returned by read_zip) -------
    METADATA: dict[Any, Any] = {
        "windows": {
            3: {                        # anchor = "C:"
                27: {                   # folder_parent = "smoke/Users/alice"
                    28: {               # folder_name = "contracts"
                        29: {           # suffix = ".pdf"
                            30: ("PDF", 8192,  1780599591),  # contract_2020
                            31: ("PDF", 9216,  1780599604),  # contract_2021
                        }
                    }
                },
                32: {                   # folder_parent = "smoke/Users/alice/photos"
                    33: {               # folder_name = "2021"
                        34: {           # suffix = ".jpg"
                            35: ("JPG", 1024, 1780599691),   # IMG_001
                            36: ("JPG", 2048, 1780599698),   # IMG_002
                            37: ("JPG", 3072, 1780599708),   # IMG_003
                            38: ("JPG", 4096, 1780599715),   # IMG_004
                            39: ("JPG", 5120, 1780599725),   # IMG_005
                        }
                    }
                }
            }
        },
        "linux": {
            0: {                        # anchor = "" (POSIX)
                40: {                   # folder_parent = "smoke/backup/photos"
                    41: {               # folder_name = "2021_copy"
                        34: {           # suffix = ".jpg"
                            35: ("JPG", 1024, 1780606892),   # IMG_001
                            36: ("JPG", 2048, 1780606900),   # IMG_002
                            37: ("JPG", 3072, 1780606910),   # IMG_003
                            38: ("JPG", 4096, 1780606916),   # IMG_004
                            39: ("JPG", 5120, 1780606926),   # IMG_005
                        },
                        42: {           # suffix = ".png"
                            43: ("PNG",  512, 1780600161),   # THUMB
                        }
                    }
                }
            }
        }
    }

    # -- Pipeline -------------------------------------------------------------
    folders = build_folders(VOCAB, METADATA)

    print("Materialised folders:")
    for fid, fr in sorted(folders.items()):
        print(f"  {fid}  ({fr.file_count} files, {_fmt_size(fr.total_size)})")
    print()

    get_sig = signature_fabric(num_bands=15, band_size=8, seed=42)

    results = find_duplicates(
        folders,
        TIER_COMPONENTS,
        TIER_ORDER,
        TIER_THRESHOLDS,
        get_sig,
    )

    print(format_report(results, folders))
