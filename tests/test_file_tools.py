from __future__ import annotations

from pathlib import Path

import pytest

from tools.file_tools import FileTools


def test_file_tools_rename_move_copy_delete(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tools = FileTools(allowed_dirs=[allowed], max_files_per_operation=100)

    source = allowed / "source.txt"
    source.write_text("hello", encoding="utf-8")

    renamed = tools.rename_file(str(source), "renamed.txt")
    renamed_path = Path(renamed["path"])
    assert renamed_path.exists()

    moved = tools.move_file(str(renamed_path), str(allowed / "sub" / "moved.txt"))
    moved_path = Path(moved["path"])
    assert moved_path.exists()

    copied = tools.copy_file(str(moved_path), str(allowed / "copy.txt"))
    copied_path = Path(copied["path"])
    assert copied_path.exists()

    deleted = tools.delete_file(str(copied_path), safe_mode=False)
    assert deleted["status"] == "ok"
    assert not copied_path.exists()


def test_file_tools_create_folder_and_find(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    tools = FileTools(allowed_dirs=[allowed], max_files_per_operation=100)

    folder = tools.create_folder(str(allowed / "notes"))
    folder_path = Path(folder["path"])
    assert folder_path.exists()

    target = folder_path / "project_notes.txt"
    target.write_text("x", encoding="utf-8")
    found = tools.find_file_by_name("notes")
    assert found["count"] >= 1


def test_file_tools_block_outside_path(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("x", encoding="utf-8")

    tools = FileTools(allowed_dirs=[allowed], max_files_per_operation=100)
    with pytest.raises(PermissionError):
        tools.delete_file(str(outside), safe_mode=False)
