"""The stat catalogue behind the leaderboards: an allow-list of mart columns.

Only stats Lahman provides (or that are computed from Lahman columns in the
marts). Every column name the browse API puts into SQL comes from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal["batting", "pitching"]
Scope = Literal["season", "career"]

# Display formats, applied by the frontend:
#   int   1,234          rate3  .366 (leading zero dropped, as in baseball)
#   dec2  2.45           ip     the mart's ip_display text (e.g. 216.1)
Format = Literal["int", "rate3", "dec2", "ip", "text", "player", "year"]


@dataclass(frozen=True)
class Stat:
    key: str
    label: str
    column: str  # column to sort and rank on
    fmt: Format = "int"
    rate: bool = False  # rate stats only make sense for qualified players
    ascending: bool = False  # lower is better (ERA, WHIP, BB/9)
    display: str | None = None  # column to show instead of `column` (IP)
    description: str = ""

    def public(self) -> dict:
        return {"key": self.key, "label": self.label, "format": self.fmt, "rate": self.rate,
                "ascending": self.ascending, "description": self.description}


BATTING: dict[str, Stat] = {s.key: s for s in [
    Stat("hr", "HR", "hr", description="Home runs"),
    Stat("h", "H", "h", description="Hits"),
    Stat("r", "R", "r", description="Runs scored"),
    Stat("rbi", "RBI", "rbi", description="Runs batted in"),
    Stat("doubles", "2B", "doubles", description="Doubles"),
    Stat("triples", "3B", "triples", description="Triples"),
    Stat("tb", "TB", "tb", description="Total bases"),
    Stat("sb", "SB", "sb", description="Stolen bases"),
    Stat("bb", "BB", "bb", description="Walks"),
    Stat("so", "SO", "so", description="Strikeouts"),
    Stat("g", "G", "g", description="Games"),
    Stat("pa", "PA", "pa", description="Plate appearances"),
    Stat("avg", "AVG", "avg", "rate3", rate=True, description="Batting average"),
    Stat("obp", "OBP", "obp", "rate3", rate=True, description="On-base percentage"),
    Stat("slg", "SLG", "slg", "rate3", rate=True, description="Slugging percentage"),
    Stat("ops", "OPS", "ops", "rate3", rate=True, description="On-base plus slugging"),
]}

PITCHING: dict[str, Stat] = {s.key: s for s in [
    Stat("so", "SO", "so", description="Strikeouts"),
    Stat("w", "W", "w", description="Wins"),
    Stat("sv", "SV", "sv", description="Saves"),
    Stat("ip", "IP", "ipouts", "ip", display="ip_display", description="Innings pitched"),
    Stat("g", "G", "g", description="Games pitched"),
    Stat("gs", "GS", "gs", description="Games started"),
    Stat("cg", "CG", "cg", description="Complete games"),
    Stat("sho", "SHO", "sho", description="Shutouts"),
    Stat("era", "ERA", "era", "dec2", rate=True, ascending=True, description="Earned run average"),
    Stat("whip", "WHIP", "whip", "dec2", rate=True, ascending=True,
         description="Walks plus hits per inning pitched"),
    Stat("so9", "SO/9", "so9", "dec2", rate=True, description="Strikeouts per nine innings"),
    Stat("bb9", "BB/9", "bb9", "dec2", rate=True, ascending=True, description="Walks per nine innings"),
    Stat("so_bb", "SO/BB", "so_bb", "dec2", rate=True, description="Strikeout-to-walk ratio"),
    Stat("win_pct", "W-L%", "win_pct", "rate3", rate=True, description="Winning percentage"),
]}

CATALOGUE: dict[str, dict[str, Stat]] = {"batting": BATTING, "pitching": PITCHING}
DEFAULT_STAT: dict[str, str] = {"batting": "hr", "pitching": "so"}

# Supporting columns every row shows, as (column, label, format). The ranked
# stat is added if it isn't already one of them.
CONTEXT: dict[str, list[tuple[str, str, Format]]] = {
    "batting": [("g", "G", "int"), ("pa", "PA", "int"), ("h", "H", "int"), ("hr", "HR", "int"),
                ("rbi", "RBI", "int"), ("sb", "SB", "int"), ("avg", "AVG", "rate3"),
                ("obp", "OBP", "rate3"), ("slg", "SLG", "rate3"), ("ops", "OPS", "rate3")],
    "pitching": [("w", "W", "int"), ("l", "L", "int"), ("g", "G", "int"), ("gs", "GS", "int"),
                 ("sv", "SV", "int"), ("ip_display", "IP", "ip"), ("so", "SO", "int"),
                 ("bb", "BB", "int"), ("era", "ERA", "dec2"), ("whip", "WHIP", "dec2")],
}

# Tables per (category, scope, split by league?), and the qualification flag.
TABLES: dict[tuple[str, str, bool], str] = {
    ("batting", "season", False): "batting_seasons",
    ("batting", "season", True): "batting_league_seasons",
    ("batting", "career", False): "batting_careers",
    ("pitching", "season", False): "pitching_seasons",
    ("pitching", "season", True): "pitching_league_seasons",
    ("pitching", "career", False): "pitching_careers",
}
QUALIFIER: dict[tuple[str, str], str] = {
    ("batting", "season"): "qualifies_batting_title",
    ("pitching", "season"): "qualifies_era_title",
    ("batting", "career"): "qualifies_career_leaders",
    ("pitching", "career"): "qualifies_career_leaders",
}

QUALIFIER_NOTE: dict[tuple[str, str], str] = {
    ("batting", "season"): "Qualified: 3.1 plate appearances per team game.",
    ("pitching", "season"): "Qualified: 1 inning pitched per team game.",
    ("batting", "career"): "Qualified: 3,000 career plate appearances.",
    ("pitching", "career"): "Qualified: 1,000 career innings pitched.",
}

# Era presets for the season range, shown as quick filters in the UI.
ERAS: list[dict] = [
    {"key": "all", "label": "All years", "from": None, "to": None},
    {"key": "modern", "label": "Integration era on (1947+)", "from": 1947, "to": None},
    {"key": "live_ball", "label": "Live-ball (1920–1946)", "from": 1920, "to": 1946},
    {"key": "dead_ball", "label": "Dead-ball (1901–1919)", "from": 1901, "to": 1919},
    {"key": "nineteenth", "label": "19th century (to 1900)", "from": None, "to": 1900},
]
