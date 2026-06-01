"""Unit tests for storage.py."""

from __future__ import annotations

import json
import logging
import zipfile
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

import clonescout.storage
from clonescout.constants import SCAN_PROGRESS_INTERVAL
from clonescout.models import FileRecord
from clonescout.storage import (
    Vocabulary,
    _keys_to_int,
    _keys_to_str,
    _recode,
    init_vocab,
    insert_record,
    merge_metadata,
    read_zip,
    reset_counters,
    write_merge_zip,
    write_zip,
)


class TestVocabulary:
    def test_init_vocab_seeds_anchors(self) -> None:
        vocab = init_vocab()
        assert vocab[""] == 0
        assert vocab["A:"] == 1
        assert vocab["Z:"] == 26
        assert len(vocab) == 27

    def test_init_vocab_returns_fresh_instance(self) -> None:
        v1 = init_vocab()
        v2 = init_vocab()
        assert v1 is not v2


class TestInsertRecord:
    def test_single_record_builds_correct_structure(self) -> None:
        vocab = init_vocab()
        metadata: dict = {}
        rec = FileRecord(
            anchor="",
            folder_parent="home/user",
            folder_name="docs",
            stem="report",
            suffix=".pdf",
            ext="PDF",
            size=1024,
            mtime=1234567890,
        )
        reset_counters()
        insert_record(metadata, vocab, "myhost", rec)

        node = metadata["myhost"]
        anchor_idx = vocab[""]
        folder_parent_idx = vocab["home/user"]
        folder_name_idx = vocab["docs"]
        suffix_idx = vocab[".pdf"]
        stem_idx = vocab["report"]

        leaf = node[anchor_idx][folder_parent_idx][folder_name_idx][suffix_idx][stem_idx]
        assert leaf == ("PDF", 1024, 1234567890)

    def test_insert_record_increments_counter(self) -> None:
        vocab = init_vocab()
        metadata: dict = {}
        rec = FileRecord("", "", "", "", "", "", 0, 0)
        reset_counters()
        insert_record(metadata, vocab, "n", rec)
        assert clonescout.storage._total_inserted == 1
        insert_record(metadata, vocab, "n", rec)
        assert clonescout.storage._total_inserted == 2

    def test_conflict_keeps_larger_mtime(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.DEBUG)
        vocab = init_vocab()
        metadata: dict = {}
        rec1 = FileRecord("", "a", "b", "c", ".d", "D", 10, 100)
        rec2 = FileRecord("", "a", "b", "c", ".d", "D", 20, 200)
        reset_counters()
        insert_record(metadata, vocab, "n", rec1)
        insert_record(metadata, vocab, "n", rec2)

        anchor_idx = vocab[""]
        fp_idx = vocab["a"]
        fn_idx = vocab["b"]
        sf_idx = vocab[".d"]
        stem_idx = vocab["c"]
        leaf = metadata["n"][anchor_idx][fp_idx][fn_idx][sf_idx][stem_idx]
        assert leaf == ("D", 20, 200)

        collision_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(collision_msgs) == 1

    def test_conflict_same_mtime_overwrites(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.DEBUG)
        vocab = init_vocab()
        metadata: dict = {}
        rec1 = FileRecord("", "a", "b", "c", ".d", "D", 10, 100)
        rec2 = FileRecord("", "a", "b", "c", ".d", "D", 20, 100)
        reset_counters()
        insert_record(metadata, vocab, "n", rec1)
        insert_record(metadata, vocab, "n", rec2)

        anchor_idx = vocab[""]
        fp_idx = vocab["a"]
        fn_idx = vocab["b"]
        sf_idx = vocab[".d"]
        stem_idx = vocab["c"]
        leaf = metadata["n"][anchor_idx][fp_idx][fn_idx][sf_idx][stem_idx]
        assert leaf == ("D", 20, 100)

    def test_conflict_keeps_existing_with_larger_mtime(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.DEBUG)
        vocab = init_vocab()
        metadata: dict = {}
        rec1 = FileRecord("", "a", "b", "c", ".d", "D", 10, 200)
        rec2 = FileRecord("", "a", "b", "c", ".d", "D", 20, 100)
        reset_counters()
        insert_record(metadata, vocab, "n", rec1)
        insert_record(metadata, vocab, "n", rec2)

        anchor_idx = vocab[""]
        fp_idx = vocab["a"]
        fn_idx = vocab["b"]
        sf_idx = vocab[".d"]
        stem_idx = vocab["c"]
        leaf = metadata["n"][anchor_idx][fp_idx][fn_idx][sf_idx][stem_idx]
        assert leaf == ("D", 10, 200)

    def test_progress_logging(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.INFO)
        vocab = init_vocab()
        metadata: dict = {}
        reset_counters()
        for i in range(SCAN_PROGRESS_INTERVAL + 1):
            # Change stem each time to avoid collisions
            rec2 = FileRecord("", "", "", f"f{i}", "", "", 0, 0)
            insert_record(metadata, vocab, "n", rec2)
        info_msgs = [r for r in caplog.records if r.levelno == logging.INFO]
        assert len(info_msgs) == 1
        assert "10000" in info_msgs[0].message


class TestVocabSerialisation:
    def test_as_list_and_from_list_roundtrip(self) -> None:
        vocab = init_vocab()
        vocab.add("foo")
        vocab.add("bar")
        restored = Vocabulary.from_list(vocab.as_list())
        assert restored.as_list() == vocab.as_list()
        assert restored["foo"] == vocab["foo"]
        assert restored["bar"] == vocab["bar"]

    def test_contains(self) -> None:
        vocab = init_vocab()
        assert "" in vocab
        assert "A:" in vocab
        assert "ZZZ" not in vocab

    def test_getitem_raises_keyerror(self) -> None:
        vocab = init_vocab()
        with pytest.raises(KeyError):
            vocab["nonexistent"]

    def test_merge_result_remap(self) -> None:
        v1 = Vocabulary()
        v1.add("a")
        v1.add("b")
        v2 = Vocabulary()
        v2.add("a")
        v2.add("c")
        result = Vocabulary.merge(v1, v2)
        assert result.remap(0, 0) == 0  # v1 "a" → 0
        assert result.remap(0, 1) == 1  # v1 "b" → 1
        assert result.remap(1, 0) == 0  # v2 "a" → 0 (unchanged)
        assert result.remap(1, 1) == 2  # v2 "c" → 2


class TestKeyConversion:
    def test_keys_to_str_converts_int_keys(self) -> None:
        d: dict = {1: {2: (3, 4, 5)}}
        result = _keys_to_str(d)
        assert result == {"1": {"2": [3, 4, 5]}}

    def test_keys_to_int_restores_int_keys(self) -> None:
        d: dict = {"1": {"2": [3, 4, 5]}}
        result = _keys_to_int(d)
        assert result == {1: {2: (3, 4, 5)}}

    def test_keys_to_int_preserves_string_keys(self) -> None:
        d: dict = {"node": {"42": [3, 4, 5]}}
        result = _keys_to_int(d)
        assert result == {"node": {42: (3, 4, 5)}}


class TestZipRoundtrip:
    def test_write_and_read_roundtrip(self, tmp_path: Path) -> None:
        vocab = init_vocab()
        metadata: dict[str, dict] = {}
        run_info = {"clonescout_version": "2026.05", "hostname": "test"}
        rec = FileRecord(
            anchor="",
            folder_parent="home/user",
            folder_name="docs",
            stem="report",
            suffix=".pdf",
            ext="PDF",
            size=1024,
            mtime=1234567890,
        )
        reset_counters()
        insert_record(metadata, vocab, "myhost", rec)

        zip_path = tmp_path / "test.zip"
        write_zip(zip_path, vocab, metadata, run_info, force=False)
        assert zip_path.exists()

        v2, m2, r2 = read_zip(zip_path)
        assert v2.as_list() == vocab.as_list()
        assert m2 == metadata
        assert r2 == run_info

    def test_write_zip_raises_when_exists_and_not_force(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "test.zip"
        zip_path.write_text("dummy")
        vocab = init_vocab()
        with pytest.raises(FileExistsError):
            write_zip(zip_path, vocab, {}, {}, force=False)

    def test_write_zip_overwrites_when_force(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "test.zip"
        zip_path.write_text("dummy")
        vocab = init_vocab()
        run_info: dict[str, str] = {}
        metadata: dict[str, dict] = {}
        write_zip(zip_path, vocab, metadata, run_info, force=True)

        v2, m2, r2 = read_zip(zip_path)
        assert v2.as_list() == vocab.as_list()
        assert m2 == metadata
        assert r2 == run_info


class TestRecode:
    def test_recode_remaps_int_keys(self) -> None:
        d = {"nodeA": {0: {1: {2: {3: {4: ("txt", 100, 200)}}}}}}
        index_map = list(range(10, 20))

        result = _recode(d, index_map)
        expected = {"nodeA": {10: {11: {12: {13: {14: ("txt", 100, 200)}}}}}}
        assert result == expected

        assert d["nodeA"][0] is not result["nodeA"][10]

    def test_recode_preserves_str_keys_and_leaf_tuples(self) -> None:
        d = {"host": {0: ("ext", 42, 999)}}
        index_map = [5]
        result = _recode(d, index_map)
        assert result == {"host": {5: ("ext", 42, 999)}}


class TestMergeMetadata:
    def test_merges_disjoint_sources(self) -> None:
        meta1 = {"nodeA": {0: {1: {2: {3: {4: ("txt", 100, 200)}}}}}}
        meta2 = {"nodeB": {0: {1: {2: {3: {4: ("pdf", 300, 400)}}}}}}
        index_map = [0, 1, 2, 3, 4, 5, 6, 7]

        result = merge_metadata([(meta1, index_map), (meta2, index_map)])
        expected = {
            "nodeA": {0: {1: {2: {3: {4: ("txt", 100, 200)}}}}},
            "nodeB": {0: {1: {2: {3: {4: ("pdf", 300, 400)}}}}},
        }
        assert result == expected

    def test_overlapping_takes_larger_mtime(self) -> None:
        meta1 = {"nodeA": {0: {1: {2: {3: {4: ("txt", 100, 200)}}}}}}
        meta2 = {"nodeA": {0: {1: {2: {3: {4: ("txt", 50, 300)}}}}}}
        index_map = [0, 1, 2, 3, 4, 5, 6, 7]

        result = merge_metadata([(meta1, index_map), (meta2, index_map)])
        expected = {"nodeA": {0: {1: {2: {3: {4: ("txt", 50, 300)}}}}}}
        assert result == expected

    def test_equal_mtime_overwrites(self) -> None:
        meta1 = {"nodeA": {0: {1: {2: {3: {4: ("txt", 100, 200)}}}}}}
        meta2 = {"nodeA": {0: {1: {2: {3: {4: ("pdf", 50, 200)}}}}}}
        index_map = [0, 1, 2, 3, 4, 5, 6, 7]

        result = merge_metadata([(meta1, index_map), (meta2, index_map)])
        expected = {"nodeA": {0: {1: {2: {3: {4: ("pdf", 50, 200)}}}}}}
        assert result == expected

    def test_collision_logging(self, caplog) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.DEBUG)
        meta1 = {"nodeA": {0: {1: {2: {3: {4: ("txt", 100, 200)}}}}}}
        meta2 = {"nodeA": {0: {1: {2: {3: {4: ("pdf", 50, 300)}}}}}}
        index_map = [0, 1, 2, 3, 4, 5, 6, 7]

        merge_metadata([(meta1, index_map), (meta2, index_map)])
        collision_msgs = [r for r in caplog.records if r.levelno == logging.DEBUG]
        assert len(collision_msgs) == 1


class TestMergeZipRoundtrip:
    def test_write_merge_zip_and_read_zip_roundtrip(self, tmp_path: Path) -> None:
        vocab = init_vocab()
        metadata: dict[str, dict] = {}
        rec = FileRecord(
            anchor="",
            folder_parent="home/user",
            folder_name="docs",
            stem="report",
            suffix=".pdf",
            ext="PDF",
            size=1024,
            mtime=1234567890,
        )
        reset_counters()
        insert_record(metadata, vocab, "myhost", rec)

        merge_doc = {
            "merge_info": {
                "clonescout_version": "2026.05",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "inputs": ["a.zip"],
            },
            "runs": [{"hostname": "test", "files_scanned": 1}],
        }

        zip_path = tmp_path / "merged.zip"
        write_merge_zip(zip_path, vocab, metadata, merge_doc, force=False)
        assert zip_path.exists()

        v2, m2, info2 = read_zip(zip_path)
        assert v2.as_list() == vocab.as_list()
        assert m2 == metadata
        assert info2 == merge_doc
        assert "runs" in info2

    def test_write_merge_zip_raises_when_exists_and_not_force(
        self, tmp_path: Path
    ) -> None:
        zip_path = tmp_path / "test.zip"
        zip_path.write_text("dummy")
        vocab = init_vocab()
        with pytest.raises(FileExistsError):
            write_merge_zip(zip_path, vocab, {}, {}, force=False)

    def test_write_merge_zip_overwrites_when_force(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "test.zip"
        zip_path.write_text("dummy")
        vocab = init_vocab()
        merge_doc: dict[str, dict] = {}
        metadata: dict[str, dict] = {}
        write_merge_zip(zip_path, vocab, metadata, merge_doc, force=True)

        v2, m2, info2 = read_zip(zip_path)
        assert v2.as_list() == vocab.as_list()
        assert m2 == metadata
        assert info2 == merge_doc


class TestReadZipExtended:
    def test_falls_back_to_merge_json(self, tmp_path: Path) -> None:
        vocab = init_vocab()
        merge_doc = {"merge_info": {}, "runs": [{"hostname": "test"}]}
        zip_path = tmp_path / "test.zip"
        write_merge_zip(zip_path, vocab, {}, merge_doc, force=False)

        _, _, info = read_zip(zip_path)
        assert "runs" in info
        assert info["runs"][0]["hostname"] == "test"

    def test_prefers_merge_json_over_run_json(
        self, tmp_path: Path, caplog
    ) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.WARNING)

        vocab = init_vocab()
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("vocab.json", json.dumps(vocab.as_list()))
            zf.writestr("metadata.json", json.dumps({}))
            zf.writestr("run.json", json.dumps({"from": "run"}))
            zf.writestr("merge.json", json.dumps({"runs": [{"from": "merge"}]}))

        _, _, info = read_zip(zip_path)
        assert info == {"runs": [{"from": "merge"}]}

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "both merge.json and run.json" in r.message for r in warnings
        )

    def test_returns_empty_dict_when_no_info(
        self, tmp_path: Path, caplog
    ) -> None:  # type: ignore[no-untyped-def]
        caplog.set_level(logging.WARNING)

        vocab = init_vocab()
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("vocab.json", json.dumps(vocab.as_list()))
            zf.writestr("metadata.json", json.dumps({}))

        _, _, info = read_zip(zip_path)
        assert info == {}

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "neither run.json nor merge.json" in r.message for r in warnings
        )
