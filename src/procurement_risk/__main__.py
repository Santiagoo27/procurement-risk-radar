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

    build = commands.add_parser("build-dataset", help="Build the validated training dataset.")
    build.add_argument("--raw", type=Path, default=config.DATA_DIR / "raw")
    build.add_argument("--out", type=Path,
                       default=config.DATA_DIR / "processed" / "dataset.parquet")
    build.add_argument("--as-of", type=date.fromisoformat, required=True)

    train = commands.add_parser("train", help="Train baselines and the LightGBM risk model.")
    train.add_argument("--dataset", type=Path,
                       default=config.DATA_DIR / "processed" / "dataset.parquet")
    train.add_argument("--target", choices=["has_value_addition", "has_time_extension"],
                       required=True)
    train.add_argument("--tracking-uri", default="sqlite:///mlflow.db")

    card = commands.add_parser("model-card", help="Write the model card from saved metrics.")
    card.add_argument("--dataset", type=Path,
                      default=config.DATA_DIR / "processed" / "dataset.parquet")
    card.add_argument("--models", type=Path, default=config.DATA_DIR / "models")
    card.add_argument("--out", type=Path, default=Path("docs") / "model-card.md")
    card.add_argument("--rolling-as-of", type=date.fromisoformat, default=None,
                      help="Models were trained with the rolling split for this date.")

    export = commands.add_parser("export-bundle", help="Package models for the API.")
    export.add_argument("--raw", type=Path, default=config.DATA_DIR / "raw")
    export.add_argument("--dataset", type=Path,
                        default=config.DATA_DIR / "processed" / "dataset.parquet")
    export.add_argument("--models", type=Path, default=config.DATA_DIR / "models")
    export.add_argument("--out", type=Path, default=Path("serving_bundle"))
    export.add_argument("--as-of", type=date.fromisoformat, required=True)
    export.add_argument("--rolling-split", action="store_true",
                        help="Models were trained with the rolling split for --as-of.")

    demo = commands.add_parser("demo-bundle", help="Build a synthetic bundle (tests, CI).")
    demo.add_argument("--out", type=Path, default=Path("serving_bundle"))

    web = commands.add_parser("export-web-data", help="Write static JSON for the web demo.")
    web.add_argument("--raw", type=Path, nargs="+", default=[config.DATA_DIR / "raw"])
    web.add_argument("--bundle", type=Path, default=Path("serving_bundle"))
    web.add_argument("--topo", type=Path,
                     default=Path("web/public/geo/colombia-municipalities.topo.json"))
    web.add_argument("--out", type=Path, default=Path("web/public/data"))
    web.add_argument("--as-of", type=date.fromisoformat, required=True)

    quality = commands.add_parser("check-quality", help="Check a fresh download before use.")
    quality.add_argument("--raw", type=Path, nargs="+", default=[config.DATA_DIR / "raw"])
    quality.add_argument("--previous", type=Path, default=None,
                         help="quality.json from the last successful run (row counts).")
    quality.add_argument("--out", type=Path, default=config.DATA_DIR / "quality.json")
    quality.add_argument("--run-date", type=date.fromisoformat, default=None)

    re = commands.add_parser("retrain", help="Train challengers and compare with production.")
    re.add_argument("--raw", type=Path, nargs="+", default=[config.DATA_DIR / "raw"])
    re.add_argument("--bundle", type=Path, default=Path("serving_bundle"))
    re.add_argument("--as-of", type=date.fromisoformat, required=True)
    re.add_argument("--out", type=Path, default=config.DATA_DIR / "retrain")

    mon = commands.add_parser("monitor", help="Drift and realized-performance report.")
    mon.add_argument("--raw", type=Path, nargs="+", default=[config.DATA_DIR / "raw"])
    mon.add_argument("--bundle", type=Path, default=Path("serving_bundle"))
    mon.add_argument("--as-of", type=date.fromisoformat, required=True)
    mon.add_argument("--out", type=Path, default=Path("web/public/data/monitoring.json"))

    size = commands.add_parser("amendment-size", help="Addition sizes from the snapshots.")
    size.add_argument("--snapshots", type=Path, default=config.DATA_DIR / "snapshots")
    size.add_argument("--out", type=Path, default=Path("web/public/data/amendment-size.json"))
    return parser


def _run_amendment_size(args: argparse.Namespace) -> None:
    import json

    from procurement_risk.ops.severity import summary

    result = summary(args.snapshots)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"{result['n_increased']:,} of {result['n_contracts_observed']:,} contracts increased "
          f"since {result['since']}; median {result['median_increase_pct']}")


def _run_monitor(args: argparse.Namespace) -> None:
    import json

    from procurement_risk.ops.monitoring import monitor_from_raw

    report = monitor_from_raw(args.raw, args.bundle, args.as_of)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    shifted = [d["feature"] for d in report["feature_drift"] if d["shifted"]]
    print(f"status {report['status']}; shifted features: {shifted or 'none'}")


def _run_retrain(args: argparse.Namespace) -> None:
    from procurement_risk.features.build import assemble_dataset
    from procurement_risk.model.split import rolling_split_dates
    from procurement_risk.ops.promotion import retrain
    from procurement_risk.validate import validate_dataset

    df, summary = assemble_dataset(args.raw, args.as_of,
                                   train_end=rolling_split_dates(args.as_of)[0])
    validate_dataset(df)
    args.out.mkdir(parents=True, exist_ok=True)
    dataset = args.out / "dataset.parquet"
    df.to_parquet(dataset, index=False)
    print(f"dataset: {summary.n_rows:,} closed contracts")
    decision = retrain(dataset, args.bundle, args.as_of, args.out)
    print(("PROMOTE" if decision.promote else "KEEP") + ": " + "; ".join(decision.reasons))


def _run_check_quality(args: argparse.Namespace) -> None:
    import json

    from procurement_risk.ops.quality import check_raw

    previous = None
    if args.previous and args.previous.exists():
        previous = json.loads(args.previous.read_text(encoding="utf-8")).get("counts")
    report = check_raw(args.raw, previous, args.run_date or date.today())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    print(report.to_markdown())
    if not report.passed:
        raise SystemExit(4)


def _run_export_web_data(args: argparse.Namespace) -> None:
    from procurement_risk.web.export import export_web_data

    report = export_web_data(args.raw, args.bundle, args.topo, args.out, args.as_of)
    cov = report["coverage"]
    print(f"closed {report['n_closed']:,}, open scored {report['n_open_scored']:,}; coverage "
          f"department {cov['department_share']:.1%}, municipality {cov['municipality_share']:.1%}")
    for name, size in sorted(report["sizes"].items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {name}: {size / 1e3:.0f} KB")
    print(f"  total: {sum(report['sizes'].values()) / 1e6:.2f} MB in {len(report['sizes'])} files")


def _run_export_bundle(args: argparse.Namespace) -> None:
    from procurement_risk.model.split import rolling_split_dates
    from procurement_risk.serving.bundle import export_bundle, load_bundle

    dates = rolling_split_dates(args.as_of) if args.rolling_split else None
    out = export_bundle(args.raw, args.dataset, args.models, args.out, args.as_of, dates)
    bundle = load_bundle(out)
    size = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
    print(f"wrote {out}: {len(bundle.buyers):,} buyers, {size / 1e6:.1f} MB")


def _run_demo_bundle(args: argparse.Namespace) -> None:
    from procurement_risk.serving.bundle import make_demo_bundle

    print(f"wrote {make_demo_bundle(args.out)}")


def _run_model_card(args: argparse.Namespace) -> None:
    import json

    from procurement_risk.model.report import write_model_card
    from procurement_risk.model.train import dataset_summary

    results = {
        target: json.loads((args.models / target / "metrics.json").read_text(encoding="utf-8"))
        for target in ("has_value_addition", "has_time_extension")
        if (args.models / target / "metrics.json").exists()
    }
    if not results:
        print(f"error: no metrics.json under {args.models}; run `train` first", file=sys.stderr)
        raise SystemExit(2)
    from procurement_risk.model.split import rolling_split_dates

    dates = rolling_split_dates(args.rolling_as_of) if args.rolling_as_of else None
    write_model_card(results, dataset_summary(args.dataset, split_dates=dates), args.out)
    print(f"wrote {args.out}")


def _run_train(args: argparse.Namespace) -> None:
    from procurement_risk.model.train import run_experiment

    results = run_experiment(args.dataset, args.target, tracking_uri=args.tracking_uri)
    print(f"test metrics for {args.target}:")
    for name, metrics in results.items():
        print(f"  {name:<11} PR-AUC {metrics['pr_auc']:.3f}  ROC-AUC {metrics['roc_auc']:.3f}  "
              f"Brier {metrics['brier']:.4f}  precision@5% {metrics['precision_at_top']:.3f}")


def _run_build_dataset(args: argparse.Namespace) -> None:
    from procurement_risk.features.build import assemble_dataset
    from procurement_risk.validate import DatasetValidationError, validate_dataset

    df, summary = assemble_dataset(args.raw, args.as_of)
    try:
        validate_dataset(df)
    except DatasetValidationError as exc:
        print(f"error: dataset failed validation: {exc}", file=sys.stderr)
        raise SystemExit(3) from exc
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    rates = ", ".join(f"{k}={v:.2%}" for k, v in summary.positive_rate.items())
    print(f"wrote {args.out}: {summary.n_rows:,} closed contracts, "
          f"{summary.n_without_process:,} without process; {rates}")


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
    elif args.command == "build-dataset":
        _run_build_dataset(args)
    elif args.command == "train":
        _run_train(args)
    elif args.command == "model-card":
        _run_model_card(args)
    elif args.command == "export-bundle":
        _run_export_bundle(args)
    elif args.command == "demo-bundle":
        _run_demo_bundle(args)
    elif args.command == "export-web-data":
        _run_export_web_data(args)
    elif args.command == "check-quality":
        _run_check_quality(args)
    elif args.command == "retrain":
        _run_retrain(args)
    elif args.command == "monitor":
        _run_monitor(args)
    elif args.command == "amendment-size":
        _run_amendment_size(args)


if __name__ == "__main__":
    main()
