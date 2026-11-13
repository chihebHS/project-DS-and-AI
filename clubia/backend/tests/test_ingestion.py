from app.agents import ingestion
from app.services import documents

from .conftest import FakeMCP


def make_mcp():
    return FakeMCP({"index_meeting": lambda args: {"indexed": len(args["chunks"])},
                    "complete_meeting": {"tasks_created": 2}, "fail_meeting": {"status": "error"}})


async def test_ingestion_graph_extracts_normalizes_and_persists(fake_llm):
    mcp = make_mcp()
    result = await ingestion.process_meeting(
        mcp, 7, "Bureau", "2026-11-01", "fr", "saisie", text="Sarah réserve l'amphi. Karim fait l'affiche.")

    assert set(mcp.names()) == {"index_meeting", "complete_meeting"}
    assert mcp.names()[-1] == "complete_meeting"  # la jointure attend l'indexation
    saved = dict(mcp.calls)["complete_meeting"]
    assert saved["decisions"] == ["Budget de 300 euros validé"]
    # doublon supprimé, date illisible remplacée par None
    assert [t["description"] for t in saved["tasks"]] == ["Réserver l'amphithéâtre", "Préparer l'affiche"]
    assert saved["tasks"][1]["due_date"] is None
    assert any("illisible" in w for w in result["warnings"])


async def test_long_meeting_is_split_and_merged(fake_llm, monkeypatch):
    monkeypatch.setattr(documents, "split_for_llm", lambda text: ["partie un", "partie deux", "partie trois"])
    mcp = make_mcp()
    result = await ingestion.process_meeting(mcp, 1, "AG", "2026-11-01", "fr", "saisie", text="long texte")

    extraction_calls = [c for c in fake_llm.calls if "secrétaire d'un club" in c[0].content]
    assert len(extraction_calls) == 3  # une extraction par partie (map)
    assert result["summary"] == "Résumé fusionné"  # reduce
    assert len(dict(mcp.calls)["complete_meeting"]["tasks"]) == 2  # doublons entre parties supprimés


async def test_ingestion_failure_marks_meeting_as_error(fake_llm):
    mcp = make_mcp()
    result = await ingestion.process_meeting(mcp, 3, "Vide", "2026-11-01", "fr", "saisie", text="   ")
    assert result is None
    assert mcp.calls[-1] == ("fail_meeting", {"meeting_id": 3, "error": "Aucun texte n'a pu être extrait."})


def test_split_for_llm_cuts_on_sentences():
    text = "Phrase courte. " * 2000
    parts = documents.split_for_llm(text, max_chars=1000, overlap=100)
    assert len(parts) > 1 and all(len(p) <= 1000 for p in parts)
    assert all(p.endswith(".") for p in parts[:-1])
    assert documents.split_for_llm("court") == ["court"]
