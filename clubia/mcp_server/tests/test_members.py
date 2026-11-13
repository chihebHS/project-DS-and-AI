from mcp_server.members import is_unassigned, match_member, normalize, split_names

MEMBERS = [
    {"name": "Karim", "aliases": []},
    {"name": "Sarah Ben Ali", "aliases": ["Sarah B."]},
    {"name": "Yasmine", "aliases": []},
]


def test_normalize_removes_accents_case_and_punctuation():
    assert normalize("  Hélène B. ") == "helene b"


def test_exact_match_on_alias():
    member, exact = match_member("sarah b", MEMBERS)
    assert member["name"] == "Sarah Ben Ali" and exact


def test_same_first_name_matches_single_member():
    member, exact = match_member("Karim B.", MEMBERS)
    assert member["name"] == "Karim" and not exact


def test_typo_matches_close_name():
    member, _ = match_member("Yasmin", MEMBERS)
    assert member["name"] == "Yasmine"


def test_unknown_name_returns_none():
    assert match_member("Amine", MEMBERS) == (None, False)


def test_split_and_unassigned():
    assert split_names("Sarah et Karim, Amine") == ["Sarah", "Karim", "Amine"]
    assert is_unassigned("Non attribué") and is_unassigned("") and not is_unassigned("Karim")
