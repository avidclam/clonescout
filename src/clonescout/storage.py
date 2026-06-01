"""Vocabulary management, metadata insertion, and ZIP serialization for CloneScout."""

from __future__ import annotations

import json
import logging
import zipfile
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clonescout.constants import SCAN_PROGRESS_INTERVAL

if TYPE_CHECKING:
    from pathlib import Path

    from clonescout.models import FileRecord


class Vocabulary:
    """A vocabulary that maps unique strings to integer indices."""

    def __init__(self) -> None:
        """Initializes an empty vocabulary."""
        self._str_to_idx: dict[str, int] = {}
        self._strings: list[str] = []

    def add(self, item: str) -> int:
        """Adds a string to the vocabulary if not already present.

        Args:
            item: The string to add to the vocabulary.

        Returns:
            The integer index associated with the string. If the string is
            already present, the vocabulary is not modified and the existing
            index is returned.
        """
        if item not in self._str_to_idx:
            idx: int = len(self._strings)
            self._str_to_idx[item] = idx
            self._strings.append(item)
        return self._str_to_idx[item]

    def as_list(self) -> list[str]:
        """Exports the vocabulary as an ordered list of strings.

        The index of each string in the returned list corresponds to its
        integer index in the vocabulary, so ``enumerate(vocab.as_list())``
        yields ``(index, string)`` pairs.

        Returns:
            A list of strings in insertion order.
        """
        return list(self._strings)

    @classmethod
    def from_list(cls, strings: list[str]) -> Vocabulary:
        """Restores a vocabulary from an ordered list of strings.

        The index of each string in the input list becomes its index
        in the restored vocabulary. No deduplication is performed.

        Args:
            strings: An ordered list of strings, as produced by ``as_list()``.

        Returns:
            A Vocabulary instance with strings registered at their original indices.
        """
        vocab = cls()
        for string in strings:
            vocab.add(string)
        return vocab

    def __len__(self) -> int:
        """Returns the number of entries in the vocabulary.

        Returns:
            The vocabulary size.
        """
        return len(self._strings)

    def __contains__(self, item: str) -> bool:
        """Checks whether a string is already in the vocabulary.

        Args:
            item: The string to look up.

        Returns:
            True if the string is present, False otherwise.
        """
        return item in self._str_to_idx

    def __getitem__(self, item: str) -> int:
        """Returns the index of an existing string.

        Args:
            item: The string to look up.

        Returns:
            The integer index associated with the string.

        Raises:
            KeyError: If the string is not in the vocabulary.
        """
        return self._str_to_idx[item]

    @staticmethod
    def merge(*vocabs: Vocabulary) -> MergeResult:
        """Merges multiple vocabularies into one without duplicating strings.

        Strings are added to the merged vocabulary in the order they are
        first encountered while iterating over the input vocabularies
        left-to-right, each in its insertion order.

        Args:
            *vocabs: Two or more Vocabulary instances to merge.

        Returns:
            A MergeResult containing the merged vocabulary and a
            per-source-vocabulary mapping from old indices to new indices.
        """
        merged: Vocabulary = Vocabulary()
        index_maps: list[list[int]] = []

        for vocab in vocabs:
            old_to_new: list[int] = []
            for old_idx, string in enumerate(vocab._strings):
                new_idx: int = merged.add(string)
                old_to_new.append(new_idx)
            index_maps.append(old_to_new)

        return MergeResult(vocabulary=merged, index_maps=index_maps)


@dataclass(frozen=True, slots=True)
class MergeResult:
    """The result of merging several vocabularies.

    Attributes:
        vocabulary: The merged vocabulary containing all unique strings.
        index_maps: A list parallel to the input vocabularies.  Each element
            is a list where ``index_maps[source][old_index]`` gives the
            corresponding new index in the merged vocabulary.
    """

    vocabulary: Vocabulary
    index_maps: list[list[int]]

    def remap(self, source: int, old_index: int) -> int:
        """Translates an old index from a source vocabulary to the merged one.

        This is a convenience shortcut for
        ``self.index_maps[source][old_index]``.

        Args:
            source: The positional number of the source vocabulary (as it was
                passed to ``Vocabulary.merge``), zero-based.
            old_index: The index within that source vocabulary.

        Returns:
            The corresponding index in the merged vocabulary.
        """
        return self.index_maps[source][old_index]


# --- Module-level progress counter ---

_total_inserted: int = 0


def reset_counters() -> None:
    """Reset the module-level progress counter to zero."""
    global _total_inserted
    _total_inserted = 0


# --- Public API ---


def init_vocab() -> Vocabulary:
    """Create a Vocabulary pre-populated with POSIX and Windows anchors.

    Inserts the empty string (POSIX anchor) at index 0, followed by
    Windows drive letters ``"A:"`` through ``"Z:"`` at indices 1–26.

    Returns:
        A Vocabulary instance with system anchors pre-registered.
    """
    vocab = Vocabulary()
    vocab.add("")
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        vocab.add(f"{letter}:")
    return vocab


def insert_record(
    metadata: dict[Any, Any],
    vocab: Vocabulary,
    node: str,
    record: FileRecord,
) -> None:
    """Insert one FileRecord into the nested metadata structure.

    The metadata dict uses the layout::

        metadata[node][anchor_idx][folder_parent_idx][folder_name_idx]
            [suffix_idx][stem_idx] = (ext, size, mtime)

    String dimensions (anchor, folder_parent, folder_name, suffix, stem)
    are stored as vocabulary indices.  ``node`` and ``ext`` are stored
    as raw strings.

    If the leaf position is already occupied, the record with the larger
    ``mtime`` is kept.  On equal ``mtime``, the new record overwrites the
    existing one.  A ``DEBUG`` log message is emitted for every collision.

    Progress is logged at every ``SCAN_PROGRESS_INTERVAL`` insertions.

    Args:
        metadata: The mutable nested metadata dict to populate.
        vocab: The Vocabulary used to encode string dimensions.
        node: The node name for this scan run.
        record: The FileRecord to insert.
    """
    global _total_inserted

    anchor_idx = vocab.add(record.anchor)
    folder_parent_idx = vocab.add(record.folder_parent)
    folder_name_idx = vocab.add(record.folder_name)
    suffix_idx = vocab.add(record.suffix)
    stem_idx = vocab.add(record.stem)

    payload: tuple[str, int, int] = (record.ext, record.size, record.mtime)

    d = metadata
    for key in (node, anchor_idx, folder_parent_idx, folder_name_idx, suffix_idx):
        d = d.setdefault(key, {})

    if stem_idx in d:
        logging.debug("Collision at leaf position: stem_idx=%d", stem_idx)
        existing = d[stem_idx]
        if record.mtime >= existing[2]:
            d[stem_idx] = payload
    else:
        d[stem_idx] = payload

    _total_inserted += 1
    if _total_inserted % SCAN_PROGRESS_INTERVAL == 0:
        logging.info("Scanned %d files so far...", _total_inserted)


def _keys_to_str(d: dict[Any, Any]) -> dict[str, Any]:
    """Recursively convert integer dict keys to strings for JSON serialization.

    Leaf tuples are converted to lists.
    """
    result: dict[str, Any] = {}
    for k, v in d.items():
        key = str(k)
        if isinstance(v, dict):
            result[key] = _keys_to_str(v)
        elif isinstance(v, tuple):
            result[key] = list(v)
        else:
            result[key] = v
    return result


def _keys_to_int(d: dict[str, Any]) -> dict[Any, Any]:
    """Recursively convert string dict keys back to integers where possible.

    Leaf lists are converted back to tuples.
    """
    result: dict[Any, Any] = {}
    for k, v in d.items():
        try:
            key: int | str = int(k)
        except ValueError:
            key = k
        if isinstance(v, dict):
            result[key] = _keys_to_int(v)
        elif isinstance(v, list):
            result[key] = tuple(v)
        else:
            result[key] = v
    return result


def write_zip(
    path: Path,
    vocab: Vocabulary,
    metadata: dict[str, Any],
    run_info: dict[str, Any],
    force: bool,
    indent: int | None = None,
) -> None:
    """Write metadata, vocabulary, and run info to a compressed ZIP archive.

    The archive contains three JSON members:

    - ``vocab.json`` — vocabulary as a plain JSON list.
    - ``metadata.json`` — nested metadata dict with all keys serialised as
      strings.  Leaf tuples ``(ext, size, mtime)`` become JSON lists.
    - ``run.json`` — run-info dict as-is.

    Args:
        path: Destination path for the output ZIP file.
        vocab: The Vocabulary to serialise.
        metadata: The nested metadata dict.
        run_info: Arbitrary run-information dict (caller provides contents).
        force: If ``True``, overwrite *path* when it already exists.
        indent: If a positive integer, pretty-print each JSON member with that
            indentation level.  ``None`` (the default) produces compact output.

    Raises:
        FileExistsError: If *path* exists and *force* is ``False``.
    """
    if path.exists() and not force:
        raise FileExistsError(f"Output file already exists: {path}")

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "vocab.json", json.dumps(vocab.as_list(), ensure_ascii=False, indent=indent)
        )
        zf.writestr(
            "metadata.json",
            json.dumps(_keys_to_str(metadata), ensure_ascii=False, indent=indent),
        )
        zf.writestr(
            "run.json",
            json.dumps(run_info, ensure_ascii=False, default=str, indent=indent),
        )


# --- Merge helpers ---


def _recode(d: dict[Any, Any], index_map: list[int]) -> dict[Any, Any]:
    """Recursively recode integer keys using index_map.

    Args:
        d: A metadata dict whose vocabulary-indexed keys (int) must be
            translated to new positions in a merged vocabulary.
        index_map: A list where ``index_map[old_idx] = new_idx``.

    Returns:
        A new dict with all ``int`` keys replaced by
        ``index_map[old_key]``.  ``str`` keys and leaf ``(ext, size, mtime)``
        tuples are copied unchanged.
    """
    result: dict[Any, Any] = {}
    for k, v in d.items():
        new_key: int | str = index_map[k] if isinstance(k, int) else k
        if isinstance(v, dict):
            result[new_key] = _recode(v, index_map)
        else:
            result[new_key] = v
    return result


def _deep_merge_into(target: dict[Any, Any], source: dict[Any, Any]) -> dict[Any, Any]:
    """Recursively merge *source* into *target*, resolving leaf collisions.

    At non-leaf levels ``dict.setdefault`` opens the corresponding subtree.
    At leaf level (values are tuples, i.e. ``(ext, size, mtime)``):

    - Vacant position → insert.
    - Occupied position → keep the entry with the larger *mtime*
      (index 2).  On equal *mtime*, the new entry overwrites.
    - Log a ``DEBUG`` message for every collision.

    Args:
        target: The result dict being built.
        source: A recoded metadata dict to merge in.

    Returns:
        *target* (mutated in-place).
    """
    for k, v in source.items():
        if isinstance(v, dict):
            target.setdefault(k, {})
            _deep_merge_into(target[k], v)
        else:
            if k in target:
                logging.debug(
                    "Collision during metadata merge at leaf position"
                )
                existing = target[k]
                if v[2] >= existing[2]:
                    target[k] = v
            else:
                target[k] = v
    return target


def merge_metadata(
    sources: list[tuple[dict[Any, Any], list[int]]],
) -> dict[Any, Any]:
    """Merge recoded metadata dicts into one, resolving leaf conflicts.

    Args:
        sources: A list of ``(metadata_dict, index_map)`` pairs, where
            ``index_map[old_index] = new_index`` in the merged vocabulary.
            Pairs are processed left-to-right; later entries win on
            equal *mtime*.

    Returns:
        A single merged metadata dict using the merged vocabulary indices.
    """
    merged: dict[Any, Any] = {}
    for meta, index_map in sources:
        recoded = _recode(meta, index_map)
        _deep_merge_into(merged, recoded)
    return merged


# --- Merge ZIP I/O ---


def write_merge_zip(
    path: Path,
    vocab: Vocabulary,
    metadata: dict[str, Any],
    merge_doc: dict[str, Any],
    force: bool,
    indent: int | None = None,
) -> None:
    """Write a merge-result ZIP archive.

    Like :func:`write_zip`, but writes ``merge.json`` instead of
    ``run.json``.  The archive contains:

    - ``vocab.json`` — vocabulary as a plain JSON list.
    - ``metadata.json`` — nested metadata dict with all keys serialised as
      strings.  Leaf tuples ``(ext, size, mtime)`` become JSON lists.
    - ``merge.json`` — merge document with ``merge_info`` and ``runs``.

    Args:
        path: Destination path for the output ZIP file.
        vocab: The merged Vocabulary to serialise.
        metadata: The merged nested metadata dict.
        merge_doc: The merge document (merge_info + runs list).
        force: If ``True``, overwrite *path* when it already exists.
        indent: If a positive integer, pretty-print each JSON member with that
            indentation level.  ``None`` (the default) produces compact output.

    Raises:
        FileExistsError: If *path* exists and *force* is ``False``.
    """
    if path.exists() and not force:
        raise FileExistsError(f"Output file already exists: {path}")

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "vocab.json", json.dumps(vocab.as_list(), ensure_ascii=False, indent=indent)
        )
        zf.writestr(
            "metadata.json",
            json.dumps(_keys_to_str(metadata), ensure_ascii=False, indent=indent),
        )
        zf.writestr(
            "merge.json",
            json.dumps(merge_doc, ensure_ascii=False, default=str, indent=indent),
        )


def read_zip(path: Path) -> tuple[Vocabulary, dict[Any, Any], dict[str, Any]]:
    """Read a metadata ZIP archive written by :func:`write_zip` or :func:`write_merge_zip`.

    Inspects the ZIP member list to determine which information payload is
    present:

    - If ``merge.json`` is present it is returned as the third element.
      If ``run.json`` is also present it is ignored with a ``WARNING``.
    - Else if ``run.json`` is present it is returned.
    - If neither is present a ``WARNING`` is logged and an empty dict is
      returned.  Callers distinguish merge-ZIP from scan-ZIP by checking
      for the ``"runs"`` key.

    Args:
        path: Path to the ZIP file to read.

    Returns:
        A tuple ``(vocab, metadata, info)`` where *vocab* is the restored
        Vocabulary, *metadata* is the nested metadata dict with integer keys
        restored, and *info* is the run-information dict, the merge document,
        or ``{}``.
    """
    with zipfile.ZipFile(path, "r") as zf:
        vocab_list: list[str] = json.loads(zf.read("vocab.json").decode())
        metadata_raw: dict[str, Any] = json.loads(
            zf.read("metadata.json").decode()
        )

        names = set(zf.namelist())
        if "merge.json" in names:
            info: dict[str, Any] = json.loads(zf.read("merge.json").decode())
            if "run.json" in names:
                logging.warning(
                    "ZIP contains both merge.json and run.json; "
                    "using merge.json, run.json ignored: %s",
                    path,
                )
        elif "run.json" in names:
            info = json.loads(zf.read("run.json").decode())
        else:
            logging.warning(
                "ZIP contains neither run.json nor merge.json: %s", path
            )
            info = {}

    vocab = Vocabulary.from_list(vocab_list)
    metadata = _keys_to_int(metadata_raw)
    return vocab, metadata, info
