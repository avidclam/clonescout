"""Data model definitions for CloneScout."""

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FileRecord:
    """A single file's metadata, suitable for vocabulary-indexed storage.

    Node is not stored here; it is applied at the metadata-insertion stage.
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

    Created post-scan/merge when the nested metadata dict is materialised
    for analysis.  Node is included here (unlike FileRecord) because the
    folder identity must be unique across machines/scan runs.

    Attributes:
        node: The node (machine/scan run) this folder belongs to.
        anchor: The anchor (POSIX ``""``, Windows ``"C:"`` etc.,
            archive: resolved archive path).
        folder_parent: Posix path to the folder's parent, no leading/trailing slash.
        folder_name: Name of this directory.  May be ``""`` for root-level folders.
        files: Immutable tuple of FileRecord instances belonging to this folder.
    """

    node: str
    anchor: str
    folder_parent: str
    folder_name: str
    files: tuple[FileRecord, ...]

    @property
    def folder_id(self) -> str:
        """Unique identifier for this folder across all nodes.
 
        Format: ``node:anchor/[folder_parent[/folder_name]|folder_name]``.
        Always starts with ``node:anchor/``.  Then:
 
        - If *folder_parent* is non-empty: appends ``folder_parent``, then
          ``/folder_name`` if *folder_name* is also non-empty.
        - If *folder_parent* is empty: appends ``folder_name`` directly
          (no leading slash).
 
        Examples: ``"nas:/"`` , ``"host:C:/"`` , ``"nas:/photos/2021"`` ,
        ``"host:C:/Users"``.
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
        return sum(f.size for f in self.files)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def min_mtime(self) -> int:
        return min(f.mtime for f in self.files)

    @property
    def max_mtime(self) -> int:
        return max(f.mtime for f in self.files)

    @property
    def ext_distribution(self) -> dict[str, int]:
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