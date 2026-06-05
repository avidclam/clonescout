"""Unit tests for clonescout.analysis — folder materialisation and duplicate detection."""

from __future__ import annotations

import copy
import logging
from typing import Any

import pytest

from clonescout.analysis import build_folders, find_duplicates, run_tier, signature_fabric
from clonescout.constants import TIER_COMPONENTS, TIER_ORDER, TIER_THRESHOLDS
from clonescout.models import FileRecord, FolderRecord
from tests.conftest import SMOKE_METADATA, SMOKE_VOCAB


def _make_file(
    *,
    anchor: str = "",
    folder_parent: str = "p",
    folder_name: str = "f",
    stem: str = "s",
    suffix: str = ".txt",
    ext: str = "TXT",
    size: int = 100,
    mtime: int = 1000,
) -> FileRecord:
    return FileRecord(
        anchor=anchor,
        folder_parent=folder_parent,
        folder_name=folder_name,
        stem=stem,
        suffix=suffix,
        ext=ext,
        size=size,
        mtime=mtime,
    )


def _make_folder(
    *,
    node: str = "n",
    anchor: str = "",
    folder_parent: str = "p",
    folder_name: str = "f",
    files: tuple[FileRecord, ...] = (),
) -> FolderRecord:
    return FolderRecord(
        node=node,
        anchor=anchor,
        folder_parent=folder_parent,
        folder_name=folder_name,
        files=files,
    )


# ---------------------------------------------------------------------------
# build_folders tests
# ---------------------------------------------------------------------------


class TestBuildFolders:
    def test_count(self) -> None:
        folders = build_folders(SMOKE_VOCAB, SMOKE_METADATA)
        assert len(folders) == 3

    def test_ids(self) -> None:
        folders = build_folders(SMOKE_VOCAB, SMOKE_METADATA)
        assert set(folders) == {
            "linux:/smoke/backup/photos/2021_copy",
            "windows:C:/smoke/Users/alice/contracts",
            "windows:C:/smoke/Users/alice/photos/2021",
        }

    def test_file_count(self) -> None:
        folders = build_folders(SMOKE_VOCAB, SMOKE_METADATA)
        counts = {fid: fr.file_count for fid, fr in folders.items()}
        assert counts["linux:/smoke/backup/photos/2021_copy"] == 6
        assert counts["windows:C:/smoke/Users/alice/contracts"] == 2
        assert counts["windows:C:/smoke/Users/alice/photos/2021"] == 5

    def test_total_size(self) -> None:
        folders = build_folders(SMOKE_VOCAB, SMOKE_METADATA)
        sizes = {fid: fr.total_size for fid, fr in folders.items()}
        assert sizes["linux:/smoke/backup/photos/2021_copy"] == 15872
        assert sizes["windows:C:/smoke/Users/alice/contracts"] == 17408
        assert sizes["windows:C:/smoke/Users/alice/photos/2021"] == 15360

    def test_skips_empty(self) -> None:
        vocab = list(SMOKE_VOCAB)
        meta: dict[Any, Any] = copy.deepcopy(SMOKE_METADATA)

        vocab.append("empty_parent")
        vocab.append("empty_name")
        fp_idx = len(vocab) - 2
        fn_idx = len(vocab) - 1

        meta["empty_node"] = {0: {fp_idx: {fn_idx: {}}}}

        folders = build_folders(vocab, meta)
        assert len(folders) == 3

    def test_duplicate_id_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        vocab = list(SMOKE_VOCAB)
        meta: dict[Any, Any] = copy.deepcopy(SMOKE_METADATA)

        vocab.append("smoke/backup")
        vocab.append("photos/2021_copy")
        fp_idx = len(vocab) - 2
        fn_idx = len(vocab) - 1
        sf_idx = vocab.index(".jpg")
        stem_idx = vocab.index("IMG_001")

        meta.setdefault("linux", {}).setdefault(0, {}).setdefault(fp_idx, {})[
            fn_idx
        ] = {sf_idx: {stem_idx: ("JPG", 1024, 1780606892)}}

        with caplog.at_level(logging.WARNING):
            folders = build_folders(vocab, meta)

        assert any(
            "Duplicate folder_id" in r.message for r in caplog.records
        )
        assert len(folders) == 3


# ---------------------------------------------------------------------------
# run_tier tests
# ---------------------------------------------------------------------------


class TestRunTier:
    def test_finds_match(self) -> None:
        a = _make_folder(
            node="a",
            folder_name="f",
            files=(
                _make_file(stem="s1", size=100),
                _make_file(stem="s2", size=200),
                _make_file(stem="s3", size=300),
                _make_file(stem="s4", size=400),
                _make_file(stem="s5", size=500),
            ),
        )
        b = _make_folder(
            node="b",
            folder_name="f",
            files=(
                _make_file(stem="s1", size=100),
                _make_file(stem="s2", size=200),
                _make_file(stem="s3", size=300),
                _make_file(stem="s4", size=400),
            ),
        )
        folders = {a.folder_id: a, b.folder_id: b}
        get_sig = signature_fabric(num_bands=15, band_size=8, seed=42)

        results = run_tier(folders, TIER_COMPONENTS["T3"], get_sig, 0.60)

        assert len(results) == 1
        fid_a, fid_b, jaccard, shared_size = results[0]
        assert fid_a <= fid_b
        assert jaccard == pytest.approx(4 / 5)
        assert shared_size == 1000

    def test_no_match_below_threshold(self) -> None:
        a = _make_folder(
            node="a",
            folder_name="f",
            files=(
                _make_file(stem="s1", size=100),
                _make_file(stem="s2", size=200),
                _make_file(stem="s3", size=300),
                _make_file(stem="s4", size=400),
                _make_file(stem="s5", size=500),
            ),
        )
        b = _make_folder(
            node="b",
            folder_name="f",
            files=(
                _make_file(stem="s1", size=100),
                _make_file(stem="s2", size=200),
                _make_file(stem="s3", size=300),
                _make_file(stem="s4", size=400),
            ),
        )
        folders = {a.folder_id: a, b.folder_id: b}
        get_sig = signature_fabric(num_bands=15, band_size=8, seed=42)

        results = run_tier(folders, TIER_COMPONENTS["T3"], get_sig, 0.99)

        assert results == []

    def test_pair_order(self) -> None:
        a = _make_folder(
            node="b-node",
            folder_name="f",
            files=(_make_file(stem="s1", size=100),),
        )
        b = _make_folder(
            node="a-node",
            folder_name="f",
            files=(_make_file(stem="s1", size=100),),
        )
        folders = {a.folder_id: a, b.folder_id: b}
        get_sig = signature_fabric(num_bands=15, band_size=8, seed=42)

        results = run_tier(folders, TIER_COMPONENTS["T3"], get_sig, 0.60)

        for fid_a, fid_b, _, _ in results:
            assert fid_a <= fid_b


# ---------------------------------------------------------------------------
# find_duplicates tests
# ---------------------------------------------------------------------------


class TestFindDuplicates:
    def test_exclusion(self) -> None:
        a = _make_folder(
            node="A",
            folder_name="docs",
            files=(
                _make_file(stem="s1", size=100),
                _make_file(stem="s2", size=200),
                _make_file(stem="s3", size=300),
                _make_file(stem="s4", size=400),
                _make_file(stem="s5", size=500),
            ),
        )
        b = _make_folder(
            node="B",
            folder_name="docs",
            files=(
                _make_file(stem="s1", size=100),
                _make_file(stem="s2", size=200),
                _make_file(stem="s3", size=300),
                _make_file(stem="s4", size=400),
                _make_file(stem="s5", size=500),
                _make_file(stem="s6", size=600),
            ),
        )
        c = _make_folder(
            node="C",
            folder_name="other",
            files=(
                _make_file(stem="s1", size=100),
                _make_file(stem="s2", size=200),
                _make_file(stem="s3", size=300),
                _make_file(stem="s4", size=400),
                _make_file(stem="s5", size=500),
            ),
        )
        folders = {a.folder_id: a, b.folder_id: b, c.folder_id: c}
        get_sig = signature_fabric(num_bands=15, band_size=8, seed=42)

        matches = find_duplicates(
            folders, TIER_COMPONENTS, TIER_ORDER, TIER_THRESHOLDS, get_sig
        )

        t1_ids: set[str] = set()
        for m in matches:
            if m.tier == "T1":
                t1_ids.update([m.folder_id_a, m.folder_id_b])

        assert "A:/docs" in t1_ids or any(
            "A:" in fid for fid in t1_ids
        )
        assert "B:/docs" in t1_ids or any(
            "B:" in fid for fid in t1_ids
        )

        t3_ids: set[str] = set()
        for m in matches:
            if m.tier == "T3":
                t3_ids.update([m.folder_id_a, m.folder_id_b])

        b_in_t3 = any("B:" in fid for fid in t3_ids)
        assert not b_in_t3, "B should be excluded from T3 after T1 match"

    def test_sorted_by_shared_size(self) -> None:
        a = _make_folder(
            node="A",
            folder_name="docs",
            files=(
                _make_file(stem="x1", size=100),
                _make_file(stem="x2", size=200),
                _make_file(stem="x3", size=300),
                _make_file(stem="x4", size=400),
            ),
        )
        b = _make_folder(
            node="B",
            folder_name="docs",
            files=(
                _make_file(stem="x1", size=100),
                _make_file(stem="x2", size=200),
                _make_file(stem="x3", size=300),
                _make_file(stem="x4", size=400),
            ),
        )
        c = _make_folder(
            node="C",
            folder_name="docs",
            files=(
                _make_file(stem="y1", size=500),
                _make_file(stem="y2", size=600),
                _make_file(stem="y3", size=700),
            ),
        )
        d = _make_folder(
            node="D",
            folder_name="docs",
            files=(
                _make_file(stem="y1", size=500),
                _make_file(stem="y2", size=600),
                _make_file(stem="y3", size=700),
            ),
        )
        folders = {a.folder_id: a, b.folder_id: b, c.folder_id: c, d.folder_id: d}
        get_sig = signature_fabric(num_bands=15, band_size=8, seed=42)

        matches = find_duplicates(
            folders, TIER_COMPONENTS, TIER_ORDER, TIER_THRESHOLDS, get_sig
        )

        t1_matches = [m for m in matches if m.tier == "T1"]
        assert len(t1_matches) >= 2
        shared_sizes = [m.shared_size for m in t1_matches]
        assert shared_sizes == sorted(shared_sizes, reverse=True)

    def test_smoke(self) -> None:
        folders = build_folders(SMOKE_VOCAB, SMOKE_METADATA)
        get_sig = signature_fabric(num_bands=15, band_size=8, seed=42)

        matches = find_duplicates(
            folders, TIER_COMPONENTS, TIER_ORDER, TIER_THRESHOLDS, get_sig
        )

        assert len(matches) == 1
        m = matches[0]
        assert m.tier == "T3"
        assert m.jaccard == pytest.approx(5 / 6, abs=0.01)
        assert m.shared_size == 15360
