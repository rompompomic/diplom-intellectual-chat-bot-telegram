from __future__ import annotations

import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from send2trash import send2trash
except Exception:  # noqa: BLE001
    send2trash = None  # type: ignore[assignment]

from security.validators import normalize_filename, normalize_path


@dataclass(slots=True)
class FileTools:
    allowed_dirs: list[Path]
    max_files_per_operation: int = 100

    def find_file_by_name(self, name: str, scope_dirs: list[str] | None = None, limit: int = 50) -> dict:
        limit = max(1, min(limit, self.max_files_per_operation))
        search_roots = self._resolve_scope_dirs(scope_dirs)
        needle = name.strip().lower()
        fuzzy_query = self._build_fuzzy_query(name)
        results: list[str] = []
        fuzzy_results: list[tuple[int, str]] = []
        for root in search_roots:
            for path in self._iter_files(root):
                if len(results) >= limit:
                    break
                try:
                    if not path.is_file():
                        continue
                except (FileNotFoundError, PermissionError, OSError):
                    continue

                path_name = path.name.lower()
                if needle and needle in path_name:
                    results.append(str(path))
                    continue

                score = self._score_fuzzy_file_match(path, fuzzy_query)
                if score > 0:
                    fuzzy_results.append((score, str(path)))
            if len(results) >= limit:
                break
        if len(results) < limit and fuzzy_results:
            seen = set(results)
            fuzzy_results.sort(key=lambda item: (-item[0], item[1].lower()))
            for _, path in fuzzy_results:
                if path in seen:
                    continue
                results.append(path)
                seen.add(path)
                if len(results) >= limit:
                    break
        return {"query": name, "count": len(results), "files": results}

    def _build_fuzzy_query(self, name: str) -> dict:
        normalized = self._normalize_search_text(name)
        parts = [part for part in normalized.split() if part]
        extensions = {
            part.lstrip(".")
            for part in parts
            if part.lstrip(".") in {"png", "jpg", "jpeg", "webp", "gif", "pdf", "doc", "docx", "txt", "md", "zip"}
        }
        terms = [part for part in parts if part.lstrip(".") not in extensions]
        return {"terms": terms, "extensions": extensions}

    def _score_fuzzy_file_match(self, path: Path, query: dict) -> int:
        terms: list[str] = query["terms"]
        extensions: set[str] = query["extensions"]
        if not terms and not extensions:
            return 0

        extension = path.suffix.lower().lstrip(".")
        if extensions and extension not in extensions:
            return 0

        haystack = self._normalize_search_text(path.stem)
        matched_terms = 0
        score = 20 if extensions else 0
        for term in terms:
            if term in haystack:
                matched_terms += 1
                score += 10 + len(term)

        if terms and matched_terms == 0:
            return 0
        if terms and matched_terms < len(terms) and len(terms) <= 2:
            return 0
        return score

    def _normalize_search_text(self, value: str) -> str:
        value = value.lower()
        value = re.sub(r"([а-яa-z])(\d)", r"\1 \2", value)
        value = re.sub(r"(\d)([а-яa-z])", r"\1 \2", value)
        value = re.sub(r"\b(jpe?g|png|webp|gif|pdf|docx?|txt|md|zip)\b", r" \1 ", value)
        value = value.replace(".", " ")
        value = re.sub(r"[^0-9a-zа-яё]+", " ", value, flags=re.IGNORECASE)
        return " ".join(value.split())

    def _iter_files(self, root: Path) -> Iterable[Path]:
        if not root.exists():
            return

        def ignore_walk_error(_: OSError) -> None:
            return None

        try:
            for dirpath, _, filenames in os.walk(root, onerror=ignore_walk_error, followlinks=False):
                for filename in filenames:
                    yield Path(dirpath) / filename
        except (FileNotFoundError, PermissionError, OSError):
            return

    def rename_file(self, path: str, new_name: str) -> dict:
        src = self._resolve_allowed_path(path)
        safe_name = normalize_filename(new_name)
        dst = src.with_name(safe_name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return {"status": "ok", "path": str(dst)}

    def move_file(self, src: str, dst: str) -> dict:
        src_path = self._resolve_allowed_path(src)
        dst_path = self._resolve_allowed_path(dst, allow_non_existing=True)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dst_path))
        return {"status": "ok", "path": str(dst_path)}

    def copy_file(self, src: str, dst: str) -> dict:
        src_path = self._resolve_allowed_path(src)
        dst_path = self._resolve_allowed_path(dst, allow_non_existing=True)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return {"status": "ok", "path": str(dst_path)}

    def delete_file(self, path: str, safe_mode: bool = True) -> dict:
        target = self._resolve_allowed_path(path)
        if not target.exists():
            return {"status": "not_found", "path": str(target)}

        if safe_mode:
            if send2trash is not None:
                send2trash(str(target))
            else:
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink()
        else:
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        return {"status": "ok", "deleted": str(target), "safe_mode": safe_mode}

    def create_folder(self, path: str) -> dict:
        folder = self._resolve_allowed_path(path, allow_non_existing=True)
        folder.mkdir(parents=True, exist_ok=True)
        return {"status": "ok", "path": str(folder)}

    def extract_archive(self, path: str, dst: str) -> dict:
        archive_path = self._resolve_allowed_path(path)
        dst_dir = self._resolve_allowed_path(dst, allow_non_existing=True)
        dst_dir.mkdir(parents=True, exist_ok=True)
        if archive_path.suffix.lower() != ".zip":
            raise ValueError("Only .zip archives are supported in this build.")

        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(dst_dir)
        return {"status": "ok", "archive": str(archive_path), "dst": str(dst_dir)}

    def create_archive(self, paths: list[str], archive_name: str) -> dict:
        if not paths:
            raise ValueError("paths is empty")
        if len(paths) > self.max_files_per_operation:
            raise ValueError("Too many files for one archive operation.")

        archive_filename = normalize_filename(archive_name)
        if not archive_filename.lower().endswith(".zip"):
            archive_filename += ".zip"

        archive_path = self._resolve_allowed_path(archive_filename, allow_non_existing=True)
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        added: list[str] = []

        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for raw in paths:
                src = self._resolve_allowed_path(raw)
                if src.is_file():
                    zf.write(src, arcname=src.name)
                    added.append(str(src))

        return {"status": "ok", "archive": str(archive_path), "files_added": added}

    def open_file(self, path: str) -> dict:
        target = self._resolve_allowed_path(path)
        os.startfile(target)  # type: ignore[attr-defined]
        return {"status": "ok", "path": str(target)}

    def path_exists(self, path: str) -> dict:
        target = self._resolve_allowed_path(path, allow_non_existing=True)
        return {"exists": target.exists(), "path": str(target)}

    def clean_downloads(self) -> dict:
        downloads = None
        for item in self.allowed_dirs:
            if item.name.lower() == "downloads":
                downloads = item
                break
        if downloads is None:
            raise ValueError("Downloads folder is not in allowed dirs.")

        affected = 0
        for child in downloads.iterdir():
            if affected >= self.max_files_per_operation:
                break
            if send2trash is not None:
                send2trash(str(child))
            else:
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            affected += 1
        return {"status": "ok", "deleted_count": affected, "folder": str(downloads)}

    def _resolve_scope_dirs(self, scope_dirs: list[str] | None) -> list[Path]:
        if not scope_dirs:
            return self.allowed_dirs

        resolved: list[Path] = []
        for raw in scope_dirs:
            try:
                candidate = self._resolve_allowed_path(raw)
                if candidate.is_dir():
                    resolved.append(candidate)
            except (FileNotFoundError, PermissionError):
                continue
        return resolved or self.allowed_dirs

    def _resolve_allowed_path(self, raw_path: str, allow_non_existing: bool = False) -> Path:
        candidate = normalize_path(raw_path, default_parent=self.allowed_dirs[0])
        if not self._is_allowed_path(candidate):
            raise PermissionError(f"Path is outside allowed directories: {candidate}")

        if not allow_non_existing and not candidate.exists():
            raise FileNotFoundError(candidate)
        return candidate

    def _is_allowed_path(self, candidate: Path) -> bool:
        resolved_candidate = candidate.resolve()
        for allowed in self.allowed_dirs:
            try:
                resolved_candidate.relative_to(allowed.resolve())
                return True
            except ValueError:
                continue
        return False
