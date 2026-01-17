"""Resume text extraction helpers."""

from __future__ import annotations

from pathlib import Path


def extract_resume_text(path: str | Path) -> str:
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in {".txt", ".md"}:
        return p.read_text(encoding="utf-8", errors="ignore")

    if suffix == ".pdf":
        # Lazy import so base crawler doesn't require PDF deps.
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(p))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)

    if suffix in {".docx"}:
        from docx import Document  # type: ignore

        doc = Document(str(p))
        return "\n".join(par.text for par in doc.paragraphs if par.text)

    raise ValueError(f"Unsupported resume file type: {suffix} (supported: .txt, .md, .pdf, .docx)")

