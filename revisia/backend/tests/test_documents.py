from app.services.documents import split_for_llm, split_into_chapters


def test_chapters_detected_from_headings_with_page_ranges():
    sections = [
        {"label": "page 1", "text": "Chapitre 1 : Modèle relationnel\n" + "Les tables ont des clés. " * 5},
        {"label": "page 2", "text": "Suite du modèle relationnel. " * 5},
        {"label": "page 3", "text": "Chapitre 2 : Requêtes SELECT\n" + "On interroge les tables. " * 5},
    ]
    chapters = split_into_chapters(sections)
    assert [c["title"] for c in chapters] == ["Chapitre 1 : Modèle relationnel", "Chapitre 2 : Requêtes SELECT"]
    assert chapters[0]["label"] == "pages 1-2" and chapters[1]["label"] == "page 3"


def test_markdown_headings_and_introduction():
    text = "Intro du cours. " * 30 + "\n# Variables\n" + "Une variable stocke. " * 5 + "\n# Boucles\n" + "for et while. " * 5
    chapters = split_into_chapters([{"label": "texte", "text": text}])
    assert [c["title"] for c in chapters] == ["Introduction", "Variables", "Boucles"]


def test_no_heading_falls_back_to_size_split():
    chapters = split_into_chapters([{"label": "texte", "text": "Phrase sans titre. " * 2000}])
    assert len(chapters) > 1 and all(c["title"] == "" for c in chapters)
    assert split_into_chapters([{"label": "texte", "text": "Court."}])[0]["text"] == "Court."


def test_split_for_llm_cuts_on_sentences():
    parts = split_for_llm("Phrase courte. " * 2000, max_chars=1000, overlap=100)
    assert all(len(p) <= 1000 for p in parts) and all(p.endswith(".") for p in parts[:-1])
