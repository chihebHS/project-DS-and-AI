"""Lecture des fichiers, découpage en chapitres et en morceaux (chunks)."""
import re

from pypdf import PdfReader

from ..config import CHUNK_OVERLAP, CHUNK_SIZE, MAX_CHAPTERS, MAX_CHARS_PER_PART, PART_OVERLAP

# Titres de chapitres reconnus : « Chapitre 2 : ... », « Partie II », « # Titre », « 3. Les jointures »
STRONG_HEADING = re.compile(
    r"^\s*(?:#{1,2}\s+\S.*|(?:chapitre|chapter|partie|part|module|le[cç]on|lesson|s[ée]ance|unit[ée]?)\s+"
    r"(?:\d+|[IVXLC]+)\b.*)$", re.IGNORECASE)
NUMBERED_HEADING = re.compile(r"^\s*(?:\d{1,2}|[IVX]{1,4})[.)]\s+[A-ZÀ-Ý].{2,80}$")


def read_pdf(path):
    """Une section par page, avec son numéro."""
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
    """Morceaux de CHUNK_SIZE caractères qui se chevauchent, avec le label (page / minute) pour les citations."""
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
    """Découpe un long texte en parties, de préférence en fin de paragraphe ou de phrase."""
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


def _label_range(labels):
    labels = list(dict.fromkeys(labels))
    if not labels:
        return ""
    if len(labels) == 1:
        return labels[0]
    first, last = labels[0], labels[-1]
    if first.startswith("page ") and last.startswith("page "):
        return f"pages {first[5:]}-{last[5:]}"
    return f"{first} → {last}"


def split_into_chapters(sections):
    """Découpe le cours en chapitres (« les différentes parties du cours »).

    1. Si le texte contient au moins deux titres de chapitre reconnaissables, on coupe sur ces titres
       (les titres « forts » comme « Chapitre 2 » ou « # Titre » sont préférés aux listes numérotées).
    2. Sinon, on coupe par taille ; le LLM donnera ensuite un titre à chaque partie.

    Renvoie [{"title", "text", "label"}], où label indique les pages / minutes couvertes.
    """
    lines = [(line, s["label"]) for s in sections for line in s["text"].splitlines()]
    for pattern in (STRONG_HEADING, NUMBERED_HEADING):
        heads = [i for i, (line, _) in enumerate(lines) if pattern.match(line) and len(line.strip()) <= 100]
        if 2 <= len(heads) <= MAX_CHAPTERS:
            chapters = []
            if heads[0] > 0:  # introduction avant le premier titre
                intro = lines[:heads[0]]
                if sum(len(line) for line, _ in intro) > 300:
                    chapters.append({"title": "Introduction", "lines": intro})
            for start, end in zip(heads, heads[1:] + [len(lines)], strict=True):
                title = lines[start][0].strip().lstrip("#").strip()
                chapters.append({"title": title[:100], "lines": lines[start + 1:end]})
            result = [{"title": c["title"], "text": "\n".join(line for line, _ in c["lines"]).strip(),
                       "label": _label_range(label for _, label in c["lines"])} for c in chapters]
            result = [c for c in result if len(c["text"]) > 40]
            if len(result) >= 2:
                return result

    full_text = "\n\n".join(s["text"] for s in sections).strip()
    parts = split_for_llm(full_text)[:MAX_CHAPTERS]
    label = _label_range(s["label"] for s in sections)
    if len(parts) <= 1:
        return [{"title": "", "text": full_text, "label": label}] if full_text else []
    return [{"title": "", "text": p, "label": label} for p in parts]
