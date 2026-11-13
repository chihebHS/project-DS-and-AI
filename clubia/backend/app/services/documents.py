"""Lecture des fichiers (PDF, texte) et découpage en morceaux (chunks)."""
from pypdf import PdfReader

from ..config import CHUNK_OVERLAP, CHUNK_SIZE, MAX_CHARS_PER_PART, PART_OVERLAP


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


def split_for_llm(text, max_chars=MAX_CHARS_PER_PART, overlap=PART_OVERLAP):
    """Découpe un long compte-rendu en parties analysables par le LLM.

    Avant : seuls les 15 000 premiers caractères étaient lus. Maintenant, chaque partie est
    analysée en parallèle par le graphe d'ingestion, puis les résultats sont fusionnés.
    On coupe de préférence sur un saut de ligne ou une fin de phrase.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []
    parts, start = [], 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            cut = max(text.rfind("\n", start + max_chars // 2, end), text.rfind(". ", start + max_chars // 2, end))
            if cut > start:
                end = cut + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return [p for p in parts if p]
