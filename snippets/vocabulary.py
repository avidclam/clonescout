from dataclasses import dataclass


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
    def from_list(cls, strings: list[str]) -> "Vocabulary":
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
    def merge(*vocabs: "Vocabulary") -> "MergeResult":
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