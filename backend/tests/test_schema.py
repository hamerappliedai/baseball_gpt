import pytest

import schema
from schema import Column, Table


def test_render_moves_shared_descriptions_to_glossary():
    tables = [
        Table("batting_seasons", "Per season.", [
            Column("player_id", "text", "Player id."),
            Column("hr", "int", "Home runs."),
            Column("team_games", "int", "Games for qualification."),
        ]),
        Table("batting_careers", "Per career.", [
            Column("player_id", "text", "Player id."),
            Column("hr", "int", "Home runs."),
        ]),
        Table("team_seasons", "Per team.", [
            Column("hr", "int", "Team home runs."),  # differs, so hr stays per-table
        ]),
    ]
    out = schema.render(tables)
    glossary = out.split("## batting_seasons")[0]
    assert "- player_id: Player id." in glossary
    assert "hr:" not in glossary
    assert "- player_id text\n" in out  # listed without repeating the description
    assert "- team_games int: Games for qualification." in out
    assert "- hr int: Team home runs." in out


@pytest.mark.anyio
async def test_schema_prompt_from_database(reader):
    text = await schema.schema_prompt(refresh=True)
    for table in ("players", "batting_seasons", "pitching_careers", "team_seasons"):
        assert f"## {table}\n" in text
    assert "qualifies_batting_title" in text
