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

        Format: ``node:anchor/folder_parent/folder_name``.
        When *folder_parent* or *folder_name* is empty the leading ``/``
        before that segment is omitted.
        """
        parts = [f"{self.node}:{self.anchor}"]
        if self.folder_parent:
            parts.append(self.folder_parent)
        if self.folder_name:
            parts.append(self.folder_name)
        return "/".join(parts)

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
