"""Compare plain SQL name search with hybrid search on labeled queries.

    cd backend && .venv/bin/python eval/search_eval.py

Each case is a query and the player a person typing it means. Reports hit@1 and
hit@5 per category for both modes. This is the phase 4 baseline that phase 5
(fine-tuning the embedding model) has to beat.
"""

import asyncio
import csv
import logging
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.disable(logging.WARNING)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import db  # noqa: E402
import players  # noqa: E402
import search  # noqa: E402

CASES = Path(__file__).with_name("search_cases.csv")


async def main() -> None:
    cases = list(csv.DictReader(CASES.open()))
    if not await search.vectors_ready():
        sys.exit("vectors.player_aliases isn't built with the backend's model; run `make embed`")
    modes = {"sql": players._sql_search, "hybrid": search.hybrid_search}
    stats = defaultdict(lambda: [0, 0, 0])  # (mode, category) -> [n, hit1, hit5]
    misses = []
    for c in cases:
        for mode, fn in modes.items():
            ids = [r["player_id"] for r in await fn(c["query"], 5)]
            for key in ((mode, c["category"]), (mode, "ALL")):
                s = stats[key]
                s[0] += 1
                s[1] += ids[:1] == [c["player_id"]]
                s[2] += c["player_id"] in ids
            if mode == "hybrid" and c["player_id"] not in ids[:1]:
                misses.append(f"  {c['query']!r}: wanted {c['player_id']}, got {ids[:3]}")
    cats = sorted({c["category"] for c in cases}) + ["ALL"]
    print(f"{'category':12s} {'n':>3s}   {'sql @1':>7s} {'@5':>5s}   {'hybrid @1':>9s} {'@5':>5s}")
    for cat in cats:
        n, s1, s5 = stats[("sql", cat)]
        _, h1, h5 = stats[("hybrid", cat)]
        print(f"{cat:12s} {n:3d}   {s1 / n:7.0%} {s5 / n:5.0%}   {h1 / n:9.0%} {h5 / n:5.0%}")
    if misses:
        print("\nhybrid misses at @1:\n" + "\n".join(misses))
    await db.close_pool()


asyncio.run(main())
