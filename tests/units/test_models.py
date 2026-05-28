"""Unit tests for models.py."""

import pytest

from clonescout.models import FileRecord


class TestFileRecord:
    def test_instantiation(self) -> None:
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
        assert rec.anchor == ""
        assert rec.folder_parent == "home/user"
        assert rec.folder_name == "docs"
        assert rec.stem == "report"
        assert rec.suffix == ".pdf"
        assert rec.ext == "PDF"
        assert rec.size == 1024
        assert rec.mtime == 1234567890

    def test_frozen(self) -> None:
        rec = FileRecord(
            anchor="C:",
            folder_parent="",
            folder_name="photos",
            stem="IMG_001",
            suffix=".jpg",
            ext="JPG",
            size=0,
            mtime=0,
        )
        with pytest.raises(Exception):
            rec.size = 999  # type: ignore[misc]

    def test_windows_anchor(self) -> None:
        rec = FileRecord(
            anchor="D:",
            folder_parent="Users\\me",
            folder_name="Desktop",
            stem="notes",
            suffix=".txt",
            ext="TXT",
            size=42,
            mtime=1,
        )
        assert rec.anchor == "D:"

    def test_empty_folder_parent(self) -> None:
        rec = FileRecord(
            anchor="",
            folder_parent="",
            folder_name="rootfiles",
            stem="README",
            suffix=".md",
            ext="MD",
            size=512,
            mtime=2,
        )
        assert rec.folder_parent == ""

    def test_no_suffix(self) -> None:
        rec = FileRecord(
            anchor="",
            folder_parent="bin",
            folder_name="scripts",
            stem="run",
            suffix="",
            ext="",
            size=100,
            mtime=3,
        )
        assert rec.suffix == ""
        assert rec.ext == ""

    def test_uppercased_ext(self) -> None:
        rec = FileRecord(
            anchor="",
            folder_parent="a",
            folder_name="b",
            stem="c",
            suffix=".JPG",
            ext="JPG",
            size=1,
            mtime=4,
        )
        assert rec.ext == "JPG"
