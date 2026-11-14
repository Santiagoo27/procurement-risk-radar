"""Command-line interface: `python -m procurement_risk <command>`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from procurement_risk import config
from procurement_risk.ingest import ingest_amendments, ingest_contracts, ingest_processes
from procurement_risk.privacy import MissingSaltError, load_salt
from procurement_risk.sources.socrata import SocrataClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="procurement_risk")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Download a SECOP II dataset to Parquet.")
    ingest.add_argument("dataset", choices=["contracts", "amendments", "processes"])
    ingest.add_argument("--from", dest="start", type=date.fromisoformat)
    ingest.add_argument("--to", dest="end", type=date.fromisoformat)
    ingest.add_argument("--out", type=Path, default=config.DATA_DIR / "raw")
    return parser


def _run_ingest(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    dated = args.dataset in ("contracts", "processes")
    if dated and (args.start is None or args.end is None):
        parser.error(f"ingest {args.dataset} requires --from and --to")
    if not dated and (args.start or args.end):
        parser.error("ingest amendments does not accept --from/--to")

    if args.dataset == "contracts":
        try:
            salt = load_salt()
        except MissingSaltError as exc:
            print(f"error: {exc}", file=sys.stderr)
            raise SystemExit(2) from exc
        out = ingest_contracts(SocrataClient(), args.out, args.start, args.end, salt)
    elif args.dataset == "processes":
        out = ingest_processes(SocrataClient(), args.out, args.start, args.end)
    else:
        out = ingest_amendments(SocrataClient(), args.out)
    print(f"wrote {out}")


def main(argv: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "ingest":
        _run_ingest(args, parser)


if __name__ == "__main__":
    main()
