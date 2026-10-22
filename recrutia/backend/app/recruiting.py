"""Matching candidats / poste et rédaction des messages d'approche.

Les données sont récupérées via les outils MCP, puis analysées par le LLM.
"""
from . import llm
from .mcp_client import mcp_client

LANGUAGES = {"fr": "français", "en": "anglais"}
CV_CHARS_FOR_MATCHING = 2500


def job_as_text(job):
    return f"{job['title']}\n{job['description']}\nCompétences recherchées : {job.get('skills') or '-'}"


async def match_candidates(job_id, limit=5):
    job = await mcp_client.call("get_job", {"job_id": job_id})
    if "error" in job:
        raise ValueError(job["error"])

    # 1. Présélection par recherche sémantique (embeddings) côté serveur MCP
    shortlist = await mcp_client.call("search_candidates", {"query": job_as_text(job), "limit": limit})
    if not shortlist:
        return {"job": job, "results": []}

    # 2. Lecture des CV présélectionnés
    cvs = []
    for candidate in shortlist:
        cv = await mcp_client.call("read_cv", {"candidate_id": candidate["id"]})
        cvs.append(f"### Candidat id={cv['id']} ({cv['name']})\n{cv['cv_text'][:CV_CHARS_FOR_MATCHING]}")

    # 3. Analyse fine par le LLM, en un seul appel pour tous les candidats
    prompt = f"""Tu es un recruteur expérimenté. Compare chaque CV à la fiche de poste.
Évalue le sens des compétences, pas seulement les mots exacts
(par exemple « Django » montre une expérience en développement web Python).

FICHE DE POSTE :
{job_as_text(job)}

CV :
{chr(10).join(cvs)}

Réponds en français, au format JSON :
{{"results": [{{"candidate_id": 1, "score": 0, "strengths": ["..."], "gaps": ["..."], "summary": "une phrase"}}]}}
score : adéquation de 0 à 100. 2 à 4 points forts, 0 à 3 manques. Un élément par candidat."""
    analysis = llm.ask(prompt, json_mode=True, temperature=0.2)

    by_id = {item.get("candidate_id"): item for item in analysis.get("results", [])}
    results = []
    for candidate in shortlist:
        item = by_id.get(candidate["id"], {})
        results.append({
            **candidate,
            "score": item.get("score", 0),
            "strengths": item.get("strengths", []),
            "gaps": item.get("gaps", []),
            "summary": item.get("summary", ""),
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return {"job": job, "results": results}


async def write_outreach(candidate_id, job_id, channel="email", language="fr", recruiter="", company=""):
    candidate = await mcp_client.call("read_cv", {"candidate_id": candidate_id})
    job = await mcp_client.call("get_job", {"job_id": job_id})
    if "error" in candidate or "error" in job:
        raise ValueError("Candidat ou poste introuvable")

    format_rules = (
        "un e-mail avec une ligne « Objet : ... », puis 120 à 180 mots"
        if channel == "email"
        else "un message LinkedIn court (70 à 100 mots), sans objet"
    )
    prompt = f"""Rédige {format_rules}, en {LANGUAGES.get(language, 'français')}, pour proposer ce poste au candidat.
Le message doit être personnalisé : cite 2 éléments précis de son parcours qui correspondent au poste.
Ton professionnel et chaleureux, pas de formules creuses, termine par une proposition d'échange.
Signe avec : {recruiter or '[Prénom du recruteur]'}{', ' + company if company else ''}.

POSTE :
{job_as_text(job)}

CV DE {candidate['name']} :
{candidate['cv_text'][:3000]}"""
    return llm.ask(prompt, temperature=0.6)
