from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from docx import Document
from pypdf import PdfReader

from security.validators import normalize_path


class DocTools:
    def __init__(self, allowed_dirs: list[Path], max_chars_for_summary: int = 12_000) -> None:
        self.allowed_dirs = [path.resolve() for path in allowed_dirs]
        self.max_chars_for_summary = max_chars_for_summary

    def extract_text_docx(self, path: str) -> dict:
        doc_path = self._resolve_allowed_path(path)
        if doc_path.suffix.lower() != ".docx":
            raise ValueError("Only .docx is supported by extract_text_docx.")
        document = Document(doc_path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
        return {"path": str(doc_path), "text": text}

    def extract_text_pdf(self, path: str) -> dict:
        pdf_path = self._resolve_allowed_path(path)
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError("Only .pdf is supported by extract_text_pdf.")
        reader = PdfReader(str(pdf_path))
        chunks: list[str] = []
        for page in reader.pages:
            extracted = page.extract_text() or ""
            if extracted.strip():
                chunks.append(extracted)
        text = "\n".join(chunks)
        return {"path": str(pdf_path), "text": text}

    def summarize_document(self, path: str, summarizer: Callable[[str], str] | None = None) -> dict:
        target = self._resolve_allowed_path(path)
        suffix = target.suffix.lower()
        if suffix == ".docx":
            extracted = self.extract_text_docx(str(target))
        elif suffix == ".pdf":
            extracted = self.extract_text_pdf(str(target))
        elif suffix in {".txt", ".md"}:
            extracted = {"path": str(target), "text": target.read_text(encoding="utf-8", errors="ignore")}
        else:
            raise ValueError(f"Unsupported extension for summary: {suffix}")

        text = extracted.get("text", "")
        if not text.strip():
            return {"path": str(target), "summary": "Документ пустой или текст не удалось извлечь."}

        if summarizer is None:
            summary = self._simple_summary(text)
        else:
            summary = summarizer(text[: self.max_chars_for_summary])

        return {"path": str(target), "summary": summary, "chars": len(text)}

    def open_document(self, path: str) -> dict:
        target = self._resolve_allowed_path(path)
        os.startfile(target)  # type: ignore[attr-defined]
        return {"status": "ok", "path": str(target)}

    def search_docs_by_keyword(self, query: str, search_fn: Callable[[str], dict]) -> dict:
        return search_fn(query)

    def _resolve_allowed_path(self, raw_path: str) -> Path:
        candidate = normalize_path(raw_path, default_parent=self.allowed_dirs[0])
        for allowed in self.allowed_dirs:
            try:
                candidate.resolve().relative_to(allowed)
                if candidate.exists():
                    return candidate
                raise FileNotFoundError(candidate)
            except ValueError:
                continue
        raise PermissionError(f"Path is outside allowed dirs: {candidate}")

    def _simple_summary(self, text: str) -> str:
        compact = " ".join(text.split())
        if len(compact) <= 600:
            return compact
        return compact[:600] + "..."
