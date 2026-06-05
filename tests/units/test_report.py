"""Unit tests for clonescout.report — duplicate report formatting."""

from __future__ import annotations

from clonescout.analysis import build_folders
from clonescout.models import FolderRecord, MatchCandidate
from clonescout.report import _fmt_size, format_report
from tests.conftest import SMOKE_METADATA, SMOKE_VOCAB


class TestFmtSize:
    def test_bytes(self) -> None:
        assert _fmt_size(512) == "512 B"

    def test_kib(self) -> None:
        assert _fmt_size(1536) == "1.5 KiB"

    def test_mib(self) -> None:
        assert _fmt_size(1_572_864) == "1.5 MiB"

    def test_boundary(self) -> None:
        assert _fmt_size(1024) == "1.0 KiB"


class TestFormatReport:
    def test_empty(self) -> None:
        assert format_report([], {}) == ""

    def test_structure(self) -> None:
        folders = build_folders(SMOKE_VOCAB, SMOKE_METADATA)
        m = MatchCandidate(
            tier="T3",
            folder_id_a="linux:/smoke/backup/photos/2021_copy",
            folder_id_b="windows:C:/smoke/Users/alice/photos/2021",
            jaccard=5 / 6,
            shared_size=15360,
        )

        output = format_report([m], folders)

        assert "## Tier: T3" in output
        assert "linux:/smoke/backup/photos/2021_copy" in output
        assert "windows:C:/smoke/Users/alice/photos/2021" in output
        assert "Jaccard: 0.83" in output
        assert "Shared: 15.0 KiB" in output

    def test_tier_order(self) -> None:
        m_t2 = MatchCandidate(
            tier="T2",
            folder_id_a="a:/x",
            folder_id_b="b:/x",
            jaccard=0.75,
            shared_size=2000,
        )
        m_t1 = MatchCandidate(
            tier="T1",
            folder_id_a="a:/x",
            folder_id_b="b:/x",
            jaccard=0.85,
            shared_size=1000,
        )
        folders = {
            "a:/x": FolderRecord(node="a", anchor="", folder_parent="", folder_name="x", files=()),
            "b:/x": FolderRecord(node="b", anchor="", folder_parent="", folder_name="x", files=()),
        }

        output = format_report([m_t2, m_t1], folders)

        pos_t2 = output.find("## Tier: T2")
        pos_t1 = output.find("## Tier: T1")
        assert pos_t2 < pos_t1

    def test_folder_id_order(self) -> None:
        m = MatchCandidate(
            tier="T3",
            folder_id_a="a:/alpha",
            folder_id_b="b:/beta",
            jaccard=0.90,
            shared_size=500,
        )
        folders = {
            "a:/alpha": FolderRecord(
                node="a", anchor="", folder_parent="", folder_name="alpha", files=()
            ),
            "b:/beta": FolderRecord(
                node="b", anchor="", folder_parent="", folder_name="beta", files=()
            ),
        }

        output = format_report([m], folders)

        pos_a = output.find("a:/alpha")
        pos_b = output.find("b:/beta")
        assert pos_a < pos_b
