from __future__ import annotations

from pathlib import Path

from docx import Document
from pypdf import PdfReader


def extract_text_from_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md", ".ps1", ".log"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        document = Document(path)
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        chunks: list[str] = []
        for page in reader.pages:
            chunks.append(page.extract_text() or "")
        return "\n".join(chunks)
    return ""
