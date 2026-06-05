"""Duplicate report formatting for CloneScout.

Renders a list of MatchCandidate instances as a human-readable Markdown report.
"""

from clonescout.models import FolderRecord, MatchCandidate


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
    """Render duplicate-detection results as a Markdown report.

    Output structure::

        ## Tier: T1

        1. Shared: 10.5 KiB  Jaccard: 0.83
           linux:/smoke/backup/photos/2021_copy        12.0 KiB
           windows:C:/smoke/Users/alice/photos/2021    15.0 KiB

        ## Tier: T2

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
        folders: All FolderRecords from build_folders(), keyed by folder_id.
            Used to look up each folder's total_size.

    Returns:
        A formatted Markdown string, or an empty string if matches is empty.

    Raises:
        KeyError: If a folder_id from *matches* is not present in *folders*.
    """
    if not matches:
        return ""

    tier_order: list[str] = []
    by_tier: dict[str, list[MatchCandidate]] = {}
    for m in matches:
        if m.tier not in by_tier:
            tier_order.append(m.tier)
            by_tier[m.tier] = []
        by_tier[m.tier].append(m)

    lines: list[str] = []
    for tier in tier_order:
        lines.append(f"## Tier: {tier}")
        lines.append("")
        for idx, m in enumerate(by_tier[tier], start=1):
            size_a = folders[m.folder_id_a].total_size
            size_b = folders[m.folder_id_b].total_size
            lines.append(
                f"{idx}. Shared: {_fmt_size(m.shared_size)}"
                f"  Jaccard: {m.jaccard:.2f}"
            )
            lines.append(f"   {m.folder_id_a:<60}  {_fmt_size(size_a)}")
            lines.append(f"   {m.folder_id_b:<60}  {_fmt_size(size_b)}")
        lines.append("")

    return "\n".join(lines).rstrip()
