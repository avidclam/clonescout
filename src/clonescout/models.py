"""Data model definitions for CloneScout."""

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
