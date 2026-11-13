"""Unit tests for the alias builder (no database or model needed)."""

from baseball_pipeline.embed import build_aliases, strip_accents


def test_strip_accents():
    assert strip_accents("José Abreu") == "Jose Abreu"
    assert strip_accents("Ronald Acuña") == "Ronald Acuna"
    assert strip_accents("Lou Gehrig") == "Lou Gehrig"


def test_build_aliases_kinds_and_dedup():
    players = [
        ("gehrilo01", "Lou Gehrig", "Gehrig", "Henry Louis"),
        ("abreujo02", "José Abreu", "Abreu", "José Dariel"),
        ("smithjo01", "John Smith", "Smith", "John"),  # given name == full name
    ]
    nicknames = [
        ("gehrilo01", "The Iron Horse", "nickname"),
        ("gehrilo01", "the iron horse", "nickname"),  # case-insensitive duplicate
        ("gehrilo01", "  The   Iron  Horse ", "nickname"),  # whitespace duplicate
    ]
    got = {(a.player_id, a.alias, a.kind) for a in build_aliases(players, nicknames)}
    assert got == {
        ("gehrilo01", "Lou Gehrig", "name"),
        ("gehrilo01", "Henry Louis Gehrig", "given_name"),
        ("gehrilo01", "The Iron Horse", "nickname"),
        ("abreujo02", "José Abreu", "name"),
        ("abreujo02", "Jose Abreu", "unaccented"),
        ("abreujo02", "José Dariel Abreu", "given_name"),
        ("abreujo02", "Jose Dariel Abreu", "unaccented"),
        ("smithjo01", "John Smith", "name"),
    }


def test_build_aliases_skips_blanks():
    assert build_aliases([("x", "X Y", None, None)], [("x", "", "nickname"), ("x", None, "nickname")]) == [
        a for a in build_aliases([("x", "X Y", None, None)], [])
    ]
