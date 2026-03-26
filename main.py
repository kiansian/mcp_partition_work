#!/usr/bin/env python3
"""MCP Partition Analysis CLI.

Usage examples
--------------
Analyse a design file and print a text report::

    python main.py examples/sample_partition.json

Write reports to files in multiple formats::

    python main.py examples/sample_partition.json \\
        --text report.txt --json report.json --csv report.csv

Use custom thresholds::

    python main.py examples/sample_partition.json \\
        --max-xp-ratio 0.25 --max-iface-util 70
"""

from __future__ import annotations

import argparse
import sys

from partition_analysis import PartitionAnalyzer, PartitionReporter
from partition_analysis.analyzer import AnalysisThresholds
from partition_analysis.models import PartitionDesign


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="partition_analysis",
        description="Comprehensive MCP circuit partition analysis and review.",
    )
    p.add_argument(
        "design_file",
        help="Path to a JSON design file produced by PartitionDesign.save().",
    )
    p.add_argument(
        "--text",
        metavar="FILE",
        default=None,
        help="Write plain-text report to FILE (default: stdout).",
    )
    p.add_argument(
        "--json",
        metavar="FILE",
        default=None,
        help="Write JSON report to FILE.",
    )
    p.add_argument(
        "--csv",
        metavar="FILE",
        default=None,
        help="Write CSV partition summary to FILE.",
    )
    p.add_argument(
        "--max-xp-ratio",
        type=float,
        default=0.30,
        metavar="RATIO",
        help="Max acceptable cross-partition signal ratio (default: 0.30).",
    )
    p.add_argument(
        "--max-iface-util",
        type=float,
        default=80.0,
        metavar="PCT",
        help="Max interface utilization %% before WARNING (default: 80).",
    )
    p.add_argument(
        "--max-iface-util-error",
        type=float,
        default=95.0,
        metavar="PCT",
        help="Interface utilization %% that triggers ERROR (default: 95).",
    )
    p.add_argument(
        "--max-balance-cv",
        type=float,
        default=0.40,
        metavar="CV",
        help="Max balance coefficient of variation (default: 0.40).",
    )
    p.add_argument(
        "--max-timing-critical",
        type=int,
        default=10,
        metavar="N",
        help="Max timing-critical cross-partition signals (default: 10).",
    )
    p.add_argument(
        "--max-clock-crossings",
        type=int,
        default=4,
        metavar="N",
        help="Max clock crossings per partition (default: 4).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Load design.
    try:
        design = PartitionDesign.load(args.design_file)
    except FileNotFoundError:
        print(f"ERROR: Design file not found: {args.design_file}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: Failed to load design file: {exc}", file=sys.stderr)
        return 1

    # Build thresholds from CLI flags.
    thresholds = AnalysisThresholds(
        max_cross_partition_ratio=args.max_xp_ratio,
        max_interface_utilization_pct=args.max_iface_util,
        max_interface_utilization_error_pct=args.max_iface_util_error,
        max_balance_cv=args.max_balance_cv,
        max_timing_critical_signals=args.max_timing_critical,
        max_clock_crossings_per_partition=args.max_clock_crossings,
    )

    # Run analysis.
    analyzer = PartitionAnalyzer(thresholds=thresholds)
    result = analyzer.analyze(design)

    # Generate reports.
    reporter = PartitionReporter(result)

    if args.text:
        reporter.save_text(args.text)
        print(f"Text report written to: {args.text}")
    else:
        # Default: print to stdout.
        print(reporter.to_text())

    if args.json:
        reporter.save_json(args.json)
        print(f"JSON report written to: {args.json}")

    if args.csv:
        reporter.save_csv(args.csv)
        print(f"CSV report written to: {args.csv}")

    # Exit with non-zero status if there are errors.
    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
