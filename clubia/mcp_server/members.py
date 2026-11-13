"""Normalisation des noms des membres.

Le LLM écrit les responsables tels qu'il les lit : « Karim », « Karim B. », « karim benali »...
Ici, on rattache chaque nom à un membre connu du club, pour que les statistiques par
membre soient justes. Règles, dans l'ordre :

1. nom vide ou « personne » → « Non attribué » ;
2. correspondance exacte (sans accents ni casse) avec un nom ou un alias ;
3. même prénom qu'un seul membre connu (« Karim B. » → « Karim ») ;
4. nom très proche (faute de frappe, difflib) ;
5. sinon, un nouveau membre est créé.

Quand le rattachement n'est pas exact, le nom lu est enregistré comme alias du membre.
"""
import difflib
import re
import unicodedata

EMPTY_NAMES = {"", "non attribue", "personne", "aucun", "n/a", "na", "none", "null", "inconnu", "unassigned", "tbd"}
SEPARATORS = re.compile(r"\s*(?:,|&|/|\bet\b|\band\b)\s*", re.IGNORECASE)


def normalize(name):
    """« Karim B. » → « karim b » (minuscules, sans accents ni ponctuation)."""
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s-]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def clean_display(name):
    name = re.sub(r"\s+", " ", (name or "").strip(" ,;:-"))
    return name[:1].upper() + name[1:] if name else name


def split_names(raw):
    """« Sarah et Karim » → ["Sarah", "Karim"]."""
    return [part for part in SEPARATORS.split(raw or "") if part and part.strip()]


def match_member(raw, members):
    """Cherche le membre correspondant à `raw` parmi `members` (liste de dicts name/aliases).

    Renvoie (membre, exact) ou (None, False).
    """
    key = normalize(raw)
    if not key:
        return None, False

    for member in members:
        if key in {normalize(member["name"]), *(normalize(a) for a in member["aliases"])}:
            return member, True

    first = key.split(" ")[0]
    if len(first) >= 3:
        same_first = [m for m in members if normalize(m["name"]).split(" ")[0] == first]
        if len(same_first) == 1:
            return same_first[0], False

    candidates = {}
    for member in members:
        for label in (member["name"], *member["aliases"]):
            candidates[normalize(label)] = member
    close = difflib.get_close_matches(key, list(candidates), n=1, cutoff=0.85)
    if close:
        return candidates[close[0]], False
    return None, False


def is_unassigned(raw):
    return normalize(raw) in EMPTY_NAMES
