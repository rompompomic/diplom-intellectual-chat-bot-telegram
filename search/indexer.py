from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from search.extractors import extract_text_from_path


@dataclass(slots=True)
class SearchIndexer:
    db_path: Path
    allowed_dirs: list[Path]
    max_indexed_chars_per_file: int = 200_000

    def __post_init__(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def rebuild_index(self, extensions: Iterable[str] = ("txt", "docx", "pdf", "md", "ps1")) -> dict:
        exts = {f".{ext.lower().lstrip('.')}" for ext in extensions}
        indexed = 0
        skipped = 0
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute("DELETE FROM files")
                conn.execute("DELETE FROM files_fts")

            for root in self.allowed_dirs:
                for path in root.rglob("*"):
                    if not path.is_file():
                        continue
                    if path.suffix.lower() not in exts:
                        continue

                    try:
                        text = extract_text_from_path(path)
                        text = text[: self.max_indexed_chars_per_file]
                        modified = path.stat().st_mtime
                    except Exception:
                        skipped += 1
                        continue

                    with conn:
                        conn.execute(
                            """
                            INSERT INTO files(path, filename, ext, modified_at, content)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                str(path),
                                path.name,
                                path.suffix.lower().lstrip("."),
                                modified,
                                text,
                            ),
                        )
                        conn.execute(
                            """
                            INSERT INTO files_fts(path, filename, ext, content)
                            VALUES (?, ?, ?, ?)
                            """,
                            (str(path), path.name, path.suffix.lower().lstrip("."), text),
                        )
                        indexed += 1
        finally:
            conn.close()
        return {"indexed": indexed, "skipped": skipped}

    def search_filename(self, query: str, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT path, filename, ext, modified_at
                FROM files
                WHERE filename LIKE ?
                ORDER BY modified_at DESC
                LIMIT ?
                """,
                (f"%{query}%", limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def search_content(self, query: str, file_types: list[str] | None = None, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            if file_types:
                placeholders = ",".join("?" for _ in file_types)
                params = [query] + [ext.lower().lstrip(".") for ext in file_types] + [limit]
                rows = conn.execute(
                    f"""
                    SELECT f.path, f.filename, f.ext, snippet(files_fts, 3, '[', ']', '...', 18) AS fragment
                    FROM files_fts
                    JOIN files f ON f.path = files_fts.path
                    WHERE files_fts MATCH ?
                      AND f.ext IN ({placeholders})
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT f.path, f.filename, f.ext, snippet(files_fts, 3, '[', ']', '...', 18) AS fragment
                    FROM files_fts
                    JOIN files f ON f.path = files_fts.path
                    WHERE files_fts MATCH ?
                    LIMIT ?
                    """,
                    (query, limit),
                ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def search_by_extension(self, extension: str, limit: int = 50) -> list[dict]:
        normalized = extension.lower().lstrip(".")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT path, filename, ext, modified_at
                FROM files
                WHERE ext = ?
                ORDER BY modified_at DESC
                LIMIT ?
                """,
                (normalized, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def search_by_modified(self, date_from: str | None = None, date_to: str | None = None, limit: int = 50) -> list[dict]:
        dt_from = datetime.fromisoformat(date_from).timestamp() if date_from else 0.0
        dt_to = datetime.fromisoformat(date_to).timestamp() if date_to else datetime.now().timestamp()

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT path, filename, ext, modified_at
                FROM files
                WHERE modified_at BETWEEN ? AND ?
                ORDER BY modified_at DESC
                LIMIT ?
                """,
                (dt_from, dt_to, limit),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS files (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        path TEXT NOT NULL UNIQUE,
                        filename TEXT NOT NULL,
                        ext TEXT NOT NULL,
                        modified_at REAL NOT NULL,
                        content TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS files_fts
                    USING fts5(path, filename, ext, content)
                    """
                )
        finally:
            conn.close()
