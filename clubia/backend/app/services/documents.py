"""Lecture des fichiers (PDF, texte) et découpage en morceaux (chunks)."""
from pypdf import PdfReader

from ..config import CHUNK_OVERLAP, CHUNK_SIZE


def read_pdf(path):
    """Retourne une liste de sections : une par page, avec son numéro."""
    reader = PdfReader(path)
    sections = []
    for number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            sections.append({"label": f"page {number}", "text": text})
    return sections


def read_text_file(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        text = f.read().strip()
    return [{"label": "texte", "text": text}] if text else []


def split_into_chunks(sections):
    """Découpe chaque section en morceaux de CHUNK_SIZE caractères qui se chevauchent.

    Le chevauchement évite de couper une idée en deux entre deux morceaux.
    Chaque morceau garde le label de sa section (page ou minute) pour les citations.
    """
    chunks = []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for section in sections:
        text = section["text"]
        for start in range(0, len(text), step):
            piece = text[start:start + CHUNK_SIZE].strip()
            if len(piece) > 30:
                chunks.append({"label": section["label"], "text": piece})
            if start + CHUNK_SIZE >= len(text):
                break
    return chunks
