"""Command line entry point: python -m gamealert run-once [--dry-run]."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_settings
from .runner import run_once
from .scheduler import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gamealert")
    sub = parser.add_subparsers(dest="command", required=True)
    once = sub.add_parser("run-once", help="check all sources once and post a summary")
    once.add_argument("--dry-run", action="store_true", help="print the summary, do not post or save state")
    serve_cmd = sub.add_parser("serve", help="run the summary at the scheduled times, forever")
    for p in (once, serve_cmd):
        p.add_argument("--config", default="config.yaml")
        p.add_argument("--env-file", default=".env")
    args = parser.parse_args(argv)

    log = logging.getLogger("gamealert")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = load_settings(args.config, args.env_file)
    if args.command == "run-once":
        result = run_once(settings, dry_run=args.dry_run)
        log.info(
            "Done: %d new items, %d messages sent, unavailable: %s",
            result.new_count,
            result.messages_sent,
            ", ".join(result.unavailable) or "none",
        )
    elif args.command == "serve":
        serve(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
