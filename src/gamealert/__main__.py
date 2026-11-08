"""Command line entry point: python -m gamealert run-once [--dry-run]."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_settings
from .report import scrub
from .runner import run_once, secret_values
from .scheduler import serve


class SecretFilter(logging.Filter):
    """Remove API keys and webhook URLs from every log line, including tracebacks."""

    def __init__(self, secrets: list[str]):
        super().__init__()
        self.secrets = secrets

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub(record.getMessage(), self.secrets)
        record.args = ()
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = scrub(record.exc_text, self.secrets)
        return True


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
    for handler in logging.getLogger().handlers:
        handler.addFilter(SecretFilter(secret_values(settings)))
    if args.command == "run-once":
        result = run_once(settings, dry_run=args.dry_run)
        log.info(
            "Done: %d new items, %d messages sent, failed sources: %s",
            result.new_count,
            result.messages_sent,
            ", ".join(result.report.failed_sources) or "none",
        )
    elif args.command == "serve":
        serve(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
