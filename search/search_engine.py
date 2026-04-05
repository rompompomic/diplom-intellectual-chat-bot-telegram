from __future__ import annotations

from dataclasses import dataclass

from search.indexer import SearchIndexer


@dataclass(slots=True)
class SearchEngine:
    indexer: SearchIndexer

    def rebuild_index(self) -> dict:
        result = self.indexer.rebuild_index()
        return {"status": "ok", **result}

    def search_filename(self, query: str, limit: int = 20) -> dict:
        rows = self.indexer.search_filename(query, limit=limit)
        return {"query": query, "count": len(rows), "results": rows}

    def search_file_content(self, query: str, file_types: list[str] | None = None, limit: int = 20) -> dict:
        rows = self.indexer.search_content(query, file_types=file_types, limit=limit)
        return {"query": query, "count": len(rows), "results": rows}

    def search_extension(self, extension: str, limit: int = 50) -> dict:
        rows = self.indexer.search_by_extension(extension, limit=limit)
        return {"extension": extension, "count": len(rows), "results": rows}

    def search_by_date(self, date_from: str | None, date_to: str | None, limit: int = 50) -> dict:
        rows = self.indexer.search_by_modified(date_from, date_to, limit=limit)
        return {"date_from": date_from, "date_to": date_to, "count": len(rows), "results": rows}
