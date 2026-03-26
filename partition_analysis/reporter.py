"""Report generation for MCP partition analysis results.

Supports three output formats:
- Plain text (human-readable)
- JSON (machine-readable)
- CSV (spreadsheet-friendly, one row per partition)
"""

from __future__ import annotations

import csv
import io
import json
from typing import List

from .analyzer import AnalysisIssue, AnalysisResult


# ---------------------------------------------------------------------------
# Severity formatting helpers
# ---------------------------------------------------------------------------

_SEVERITY_LABEL = {
    "ERROR": "[ERROR  ]",
    "WARNING": "[WARNING]",
    "INFO": "[INFO   ]",
}


def _fmt_severity(severity: str) -> str:
    return _SEVERITY_LABEL.get(severity, f"[{severity}]")


def _section(title: str, width: int = 70) -> str:
    bar = "=" * width
    return f"\n{bar}\n  {title}\n{bar}\n"


def _subsection(title: str, width: int = 70) -> str:
    bar = "-" * width
    return f"\n{bar}\n  {title}\n{bar}\n"


# ---------------------------------------------------------------------------
# Reporter
# ---------------------------------------------------------------------------


class PartitionReporter:
    """Generates human-readable and machine-readable reports from an
    :class:`~analyzer.AnalysisResult`.

    Parameters
    ----------
    result:
        The analysis result to report on.
    """

    def __init__(self, result: AnalysisResult) -> None:
        self.result = result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def to_text(self) -> str:
        """Return a formatted plain-text report."""
        lines: List[str] = []
        r = self.result

        lines.append(_section(f"MCP Partition Analysis Report: {r.design_name}"))

        # --- Design Summary ---
        lines.append(_subsection("Design Summary"))
        dm = r.design_metrics
        lines.append(f"  Partitions            : {dm.partition_count}")
        lines.append(f"  Total Signals         : {dm.total_signal_count}")
        lines.append(f"  Cross-Partition Signals: {dm.cross_partition_signal_count}")
        lines.append(
            f"  Cross-Partition Ratio : {dm.cross_partition_ratio:.1%}"
        )
        lines.append(
            f"  Total Bandwidth       : {dm.total_bandwidth_mbps:,.1f} Mbit/s"
        )
        lines.append(
            f"  Timing-Critical Xings : {dm.timing_critical_crossings}"
        )
        lines.append(f"  Physical Interfaces   : {dm.interface_count}")
        lines.append(
            f"  Area Balance (CV)     : "
            + (_fmt_optional(dm.area_balance_score, ".4f"))
        )
        lines.append(
            f"  Power Balance (CV)    : "
            + (_fmt_optional(dm.power_balance_score, ".4f"))
        )
        lines.append(
            f"  Cell Balance (CV)     : "
            + (_fmt_optional(dm.cell_balance_score, ".4f"))
        )

        # --- Partition Details ---
        lines.append(_subsection("Partition Details"))
        for pname, pm in r.partition_metrics.items():
            lines.append(f"  Partition: {pname}")
            lines.append(
                f"    Outbound Signals    : {pm.outbound_signal_count}"
            )
            lines.append(
                f"    Inbound Signals     : {pm.inbound_signal_count}"
            )
            lines.append(
                f"    Total Crossings     : {pm.total_cross_partition_signals}"
            )
            lines.append(
                f"    Outbound BW         : {pm.outbound_bandwidth_mbps:,.1f} Mbit/s"
            )
            lines.append(
                f"    Inbound BW          : {pm.inbound_bandwidth_mbps:,.1f} Mbit/s"
            )
            lines.append(
                f"    Timing-Critical     : {pm.timing_critical_crossings}"
            )
            lines.append(f"    Clock Crossings     : {pm.clock_crossings}")
            lines.append(f"    Reset Crossings     : {pm.reset_crossings}")
            lines.append(f"    Physical Interfaces : {pm.interface_count}")
            lines.append(
                f"    Register Ratio      : "
                + _fmt_optional(pm.register_ratio, ".2%")
            )
            lines.append(
                f"    Power Density       : "
                + _fmt_optional(pm.power_density_mw_mm2, ".2f")
                + (" mW/mm²" if pm.power_density_mw_mm2 is not None else "")
            )
            lines.append("")

        # --- Interface Details ---
        if r.interface_metrics:
            lines.append(_subsection("Interface Details"))
            for iname, im in r.interface_metrics.items():
                lines.append(f"  Interface: {iname}")
                lines.append(
                    f"    Signals Routed      : {im.signal_count}"
                )
                lines.append(
                    f"    Utilized Bandwidth  : {im.utilized_bandwidth_mbps:,.1f} Mbit/s"
                )
                lines.append(
                    f"    Utilization         : "
                    + _fmt_optional(im.utilization_pct, ".1f")
                    + ("%" if im.utilization_pct is not None else "")
                )
                lines.append(
                    f"    Timing-Critical     : {im.timing_critical_signal_count}"
                )
                lines.append("")

        # --- Issues ---
        lines.append(_subsection("Issues and Recommendations"))
        issue_list = r.issues
        if not issue_list:
            lines.append("  No issues found. Partition design looks healthy.")
        else:
            counts = {
                "ERROR": len(r.errors),
                "WARNING": len(r.warnings),
                "INFO": len(r.infos),
            }
            lines.append(
                f"  Errors: {counts['ERROR']}  "
                f"Warnings: {counts['WARNING']}  "
                f"Info: {counts['INFO']}"
            )
            lines.append("")
            for issue in issue_list:
                prefix = _fmt_severity(issue.severity)
                scope = f"[{issue.partition}] " if issue.partition else ""
                lines.append(
                    f"  {prefix} [{issue.category}] {scope}{issue.message}"
                )
                lines.append(f"    → {issue.recommendation}")
                lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """Return the full analysis result as a JSON string."""
        return json.dumps(self.result.to_dict(), indent=indent)

    def to_csv(self) -> str:
        """Return a CSV string with one row per partition.

        Columns: partition_name, inbound_signal_count,
        outbound_signal_count, total_cross_partition_signals,
        inbound_bandwidth_mbps, outbound_bandwidth_mbps,
        timing_critical_crossings, clock_crossings, reset_crossings,
        interface_count, register_ratio, power_density_mw_mm2.
        """
        output = io.StringIO()
        fieldnames = [
            "partition_name",
            "inbound_signal_count",
            "outbound_signal_count",
            "total_cross_partition_signals",
            "inbound_bandwidth_mbps",
            "outbound_bandwidth_mbps",
            "timing_critical_crossings",
            "clock_crossings",
            "reset_crossings",
            "interface_count",
            "register_ratio",
            "power_density_mw_mm2",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        for pm in self.result.partition_metrics.values():
            row = pm.to_dict()
            writer.writerow({k: row[k] for k in fieldnames})
        return output.getvalue()

    def save_text(self, filepath: str) -> None:
        """Write the plain-text report to *filepath*."""
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(self.to_text())

    def save_json(self, filepath: str, indent: int = 2) -> None:
        """Write the JSON report to *filepath*."""
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(self.to_json(indent=indent))

    def save_csv(self, filepath: str) -> None:
        """Write the CSV report to *filepath*."""
        with open(filepath, "w", encoding="utf-8", newline="") as fh:
            fh.write(self.to_csv())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fmt_optional(value, fmt: str) -> str:
    """Format *value* using *fmt* spec, or return ``'N/A'`` for ``None``."""
    if value is None:
        return "N/A"
    return format(value, fmt)
