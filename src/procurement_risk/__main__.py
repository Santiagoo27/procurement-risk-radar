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
from procurement_risk.snapshot import Watermark, take_snapshot
from procurement_risk.sources.socrata import SocrataClient


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="procurement_risk")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Download a SECOP II dataset to Parquet.")
    ingest.add_argument("dataset", choices=["contracts", "amendments", "processes"])
    ingest.add_argument("--from", dest="start", type=date.fromisoformat)
    ingest.add_argument("--to", dest="end", type=date.fromisoformat)
    ingest.add_argument("--out", type=Path, default=config.DATA_DIR / "raw")

    snap = commands.add_parser("snapshot", help="Archive changed contract values and dates.")
    snap.add_argument("--watermark", type=Path,
                      default=config.DATA_DIR / "snapshots" / "watermark.json")
    snap.add_argument("--out", type=Path, default=config.DATA_DIR / "snapshots")
    snap.add_argument("--run-date", type=date.fromisoformat, default=None)
    snap.add_argument("--full", action="store_true", help="Re-download every contract.")

    audit = commands.add_parser("audit", help="Run the Phase 0 data audit.")
    audit.add_argument("--raw", type=Path, default=config.DATA_DIR / "raw")
    audit.add_argument("--out", type=Path, default=Path("docs") / "data-audit.md")
    audit.add_argument("--as-of", type=date.fromisoformat, required=True)
    audit.add_argument("--sample-precision", type=float, default=None,
                       help="Manual precision (0-1) of the text matcher on the sample.")
    audit.add_argument("--sample-out", type=Path,
                       default=config.DATA_DIR / "audit" / "value_addition_sample.txt",
                       help="Where to write the text sample (keep it out of git).")
    return parser


def _run_audit(args: argparse.Namespace) -> None:
    from procurement_risk.audit import metrics
    from procurement_risk.audit.report import decide, render_report, write_sample

    con = metrics.open_audit_db(args.raw)
    results = {
        "as_of": args.as_of,
        "sample_precision": args.sample_precision,
        "label_rates": metrics.label_rates_by_year(con),
        "hidden": metrics.hidden_value_additions(con),
        "value_vs_award": metrics.value_vs_award(con),
        "end_date": metrics.end_date_vs_duration(con),
        "closure": metrics.closure_states(con, args.as_of),
        "bidders": metrics.bidder_coverage(con),
    }
    decisions = decide(results)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_report(results, decisions), encoding="utf-8")
    write_sample(results["hidden"]["sample"], args.sample_out)
    print(f"wrote {args.out}; primary target: {decisions['primary_target']}")


def _run_snapshot(args: argparse.Namespace) -> None:
    watermark = Watermark.load(args.watermark)
    run_date = args.run_date or date.today()
    path, new_watermark = take_snapshot(
        SocrataClient(), args.out, watermark, run_date, full=args.full
    )
    if path is None:
        print("no changes since last snapshot")
        return
    new_watermark.save(args.watermark)
    print(f"wrote {path}; watermark {new_watermark.last_updated}")


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
    elif args.command == "snapshot":
        _run_snapshot(args)
    elif args.command == "audit":
        _run_audit(args)


if __name__ == "__main__":
    main()
