"""Command line entry point.

    bgpt-pipeline discover --release 2025 --box-shared-name <id>   # pin a new release
    bgpt-pipeline fetch    --release 2025                          # download + verify
    bgpt-pipeline verify   --release 2025                          # re-check the cache, offline
    bgpt-pipeline load     --release 2025                          # verify + load raw schema
    bgpt-pipeline build    --release 2025                          # fetch + load
    bgpt-pipeline embed                                            # aliases + embeddings -> vectors schema
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import embed as embed_mod
from . import fetch as fetch_mod
from . import load as load_mod

DEFAULT_RELEASE = "2025"
SOURCE_PAGE = "https://sabr.org/lahman-database/"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bgpt-pipeline", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name: str, help: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help)
        p.add_argument("--release", default=DEFAULT_RELEASE)
        return p

    d = add("discover", "list a Box release folder and pin it in a new manifest")
    d.add_argument("--box-shared-name", required=True,
                   help="the id at the end of the release's sabr.box.com/s/<id> link")
    d.add_argument("--source-page", default=SOURCE_PAGE)
    d.add_argument("--force", action="store_true", help="overwrite an existing manifest")
    add("fetch", "download the release and verify it against its manifest")
    add("verify", "verify the cached release without downloading")
    lp = add("load", "verify the cached release and load it into the raw schema")
    bp = add("build", "fetch, verify and load")
    for p in (lp, bp):
        p.add_argument("--database-url", help="defaults to $DATABASE_URL")
    ep = sub.add_parser("embed", help="embed player names and nicknames into vectors.player_aliases")
    ep.add_argument("--database-url", help="defaults to $DATABASE_URL")
    ep.add_argument("--model", default=embed_mod.DEFAULT_MODEL,
                    help="sentence-transformers model (default: $EMBED_MODEL or all-MiniLM-L6-v2)")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)-7s %(message)s")
    # The Hugging Face client logs every model file request at INFO.
    for noisy in ("httpx", "huggingface_hub"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        if args.command == "discover":
            fetch_mod.discover(args.release, args.box_shared_name, args.source_page, args.force)
        elif args.command == "fetch":
            fetch_mod.fetch(args.release)
        elif args.command == "verify":
            fetch_mod.verify(args.release)
        elif args.command == "load":
            load_mod.load(args.release, args.database_url)
        elif args.command == "build":
            fetch_mod.fetch(args.release)
            load_mod.load(args.release, args.database_url)
        elif args.command == "embed":
            embed_mod.embed(args.database_url, args.model)
    except (fetch_mod.VerificationError, load_mod.LoadError, embed_mod.EmbedError, FileNotFoundError, FileExistsError) as e:
        logging.error("%s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
