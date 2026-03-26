"""Comprehensive partition analyzer for MCP circuit designs.

Computes partition-level and design-level metrics and identifies
potential issues / recommendations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import Interface, Partition, PartitionDesign, Signal


# ---------------------------------------------------------------------------
# Result data-classes
# ---------------------------------------------------------------------------


@dataclass
class PartitionMetrics:
    """Per-partition computed metrics.

    Attributes:
        partition_name: Name of the analysed partition.
        inbound_signal_count: Number of cross-partition signals received.
        outbound_signal_count: Number of cross-partition signals driven.
        total_cross_partition_signals: Total signals crossing boundary.
        inbound_bandwidth_mbps: Estimated inbound bandwidth in Mbit/s.
        outbound_bandwidth_mbps: Estimated outbound bandwidth in Mbit/s.
        timing_critical_crossings: Signals marked timing-critical that
            cross into/out-of this partition.
        clock_crossings: Clock signals that cross this partition boundary.
        reset_crossings: Reset signals that cross this partition boundary.
        interface_count: Number of physical interfaces attached.
        register_ratio: Fraction of cells that are flip-flops.
        power_density_mw_mm2: Power density in mW/mm².
    """

    partition_name: str
    inbound_signal_count: int = 0
    outbound_signal_count: int = 0
    total_cross_partition_signals: int = 0
    inbound_bandwidth_mbps: float = 0.0
    outbound_bandwidth_mbps: float = 0.0
    timing_critical_crossings: int = 0
    clock_crossings: int = 0
    reset_crossings: int = 0
    interface_count: int = 0
    register_ratio: Optional[float] = None
    power_density_mw_mm2: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "partition_name": self.partition_name,
            "inbound_signal_count": self.inbound_signal_count,
            "outbound_signal_count": self.outbound_signal_count,
            "total_cross_partition_signals": self.total_cross_partition_signals,
            "inbound_bandwidth_mbps": round(self.inbound_bandwidth_mbps, 3),
            "outbound_bandwidth_mbps": round(self.outbound_bandwidth_mbps, 3),
            "timing_critical_crossings": self.timing_critical_crossings,
            "clock_crossings": self.clock_crossings,
            "reset_crossings": self.reset_crossings,
            "interface_count": self.interface_count,
            "register_ratio": (
                round(self.register_ratio, 4)
                if self.register_ratio is not None
                else None
            ),
            "power_density_mw_mm2": (
                round(self.power_density_mw_mm2, 4)
                if self.power_density_mw_mm2 is not None
                else None
            ),
        }


@dataclass
class InterfaceMetrics:
    """Per-interface computed metrics.

    Attributes:
        interface_name: Name of the physical interface.
        utilized_bandwidth_mbps: Sum of signal bandwidths routed through
            this interface in Mbit/s.
        utilization_pct: ``utilized_bandwidth_mbps / max_bandwidth_mbps``
            expressed as a percentage (``None`` if limit is unknown).
        signal_count: Number of signals routed through this interface.
        timing_critical_signal_count: Number of timing-critical signals.
    """

    interface_name: str
    utilized_bandwidth_mbps: float = 0.0
    utilization_pct: Optional[float] = None
    signal_count: int = 0
    timing_critical_signal_count: int = 0

    def to_dict(self) -> dict:
        return {
            "interface_name": self.interface_name,
            "utilized_bandwidth_mbps": round(self.utilized_bandwidth_mbps, 3),
            "utilization_pct": (
                round(self.utilization_pct, 2)
                if self.utilization_pct is not None
                else None
            ),
            "signal_count": self.signal_count,
            "timing_critical_signal_count": self.timing_critical_signal_count,
        }


@dataclass
class DesignMetrics:
    """Design-wide aggregate metrics.

    Attributes:
        partition_count: Total number of partitions.
        total_signal_count: Total signals in the design.
        cross_partition_signal_count: Signals crossing at least one boundary.
        cross_partition_ratio: Fraction of signals that are cross-partition.
        total_bandwidth_mbps: Aggregate bandwidth of all cross-partition
            signals in Mbit/s.
        timing_critical_crossings: Total timing-critical cross-partition
            signals.
        area_balance_score: Coefficient of variation (CV) of per-partition
            area (lower = more balanced; ``None`` if areas are all zero).
        power_balance_score: CV of per-partition power (lower = more
            balanced; ``None`` if powers are all zero).
        cell_balance_score: CV of per-partition cell count (lower = more
            balanced; ``None`` if cell counts are all zero).
        interface_count: Total number of physical interfaces.
    """

    partition_count: int = 0
    total_signal_count: int = 0
    cross_partition_signal_count: int = 0
    cross_partition_ratio: float = 0.0
    total_bandwidth_mbps: float = 0.0
    timing_critical_crossings: int = 0
    area_balance_score: Optional[float] = None
    power_balance_score: Optional[float] = None
    cell_balance_score: Optional[float] = None
    interface_count: int = 0

    def to_dict(self) -> dict:
        return {
            "partition_count": self.partition_count,
            "total_signal_count": self.total_signal_count,
            "cross_partition_signal_count": self.cross_partition_signal_count,
            "cross_partition_ratio": round(self.cross_partition_ratio, 4),
            "total_bandwidth_mbps": round(self.total_bandwidth_mbps, 3),
            "timing_critical_crossings": self.timing_critical_crossings,
            "area_balance_score": (
                round(self.area_balance_score, 4)
                if self.area_balance_score is not None
                else None
            ),
            "power_balance_score": (
                round(self.power_balance_score, 4)
                if self.power_balance_score is not None
                else None
            ),
            "cell_balance_score": (
                round(self.cell_balance_score, 4)
                if self.cell_balance_score is not None
                else None
            ),
            "interface_count": self.interface_count,
        }


@dataclass
class AnalysisIssue:
    """A single issue or warning identified during analysis.

    Attributes:
        severity: One of ``"ERROR"``, ``"WARNING"``, or ``"INFO"``.
        category: Short category tag (e.g. ``"TIMING"``, ``"BANDWIDTH"``).
        partition: Affected partition name (``None`` = design-wide).
        message: Human-readable description of the issue.
        recommendation: Suggested corrective action.
    """

    severity: str
    category: str
    message: str
    recommendation: str
    partition: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "category": self.category,
            "partition": self.partition,
            "message": self.message,
            "recommendation": self.recommendation,
        }


@dataclass
class AnalysisResult:
    """Complete analysis result for a :class:`~models.PartitionDesign`.

    Attributes:
        design_name: Name of the analysed design.
        design_metrics: Aggregate design-level metrics.
        partition_metrics: Per-partition metrics keyed by partition name.
        interface_metrics: Per-interface metrics keyed by interface name.
        issues: Ordered list of :class:`AnalysisIssue` objects.
    """

    design_name: str
    design_metrics: DesignMetrics = field(default_factory=DesignMetrics)
    partition_metrics: Dict[str, PartitionMetrics] = field(default_factory=dict)
    interface_metrics: Dict[str, InterfaceMetrics] = field(default_factory=dict)
    issues: List[AnalysisIssue] = field(default_factory=list)

    @property
    def errors(self) -> List[AnalysisIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> List[AnalysisIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    @property
    def infos(self) -> List[AnalysisIssue]:
        return [i for i in self.issues if i.severity == "INFO"]

    def to_dict(self) -> dict:
        return {
            "design_name": self.design_name,
            "design_metrics": self.design_metrics.to_dict(),
            "partition_metrics": {
                k: v.to_dict() for k, v in self.partition_metrics.items()
            },
            "interface_metrics": {
                k: v.to_dict() for k, v in self.interface_metrics.items()
            },
            "issues": [i.to_dict() for i in self.issues],
        }


# ---------------------------------------------------------------------------
# Thresholds (can be overridden when creating the analyzer)
# ---------------------------------------------------------------------------


@dataclass
class AnalysisThresholds:
    """Configurable thresholds that drive issue generation.

    All thresholds are directional: exceeding the threshold triggers at
    least a WARNING.

    Attributes:
        max_cross_partition_ratio: Maximum acceptable ratio of cross-partition
            signals to total signals before a WARNING is raised.
        max_interface_utilization_pct: Maximum acceptable interface
            utilization percentage before a WARNING is raised.
        max_interface_utilization_error_pct: Utilization percentage above
            which an ERROR (rather than WARNING) is raised.
        max_balance_cv: Maximum acceptable coefficient of variation for
            area/power/cell balance before a WARNING is raised.
        max_timing_critical_signals: Maximum number of timing-critical
            cross-partition signals before a WARNING is raised.
        max_clock_crossings_per_partition: Limit on clock nets crossing
            per partition.
    """

    max_cross_partition_ratio: float = 0.30
    max_interface_utilization_pct: float = 80.0
    max_interface_utilization_error_pct: float = 95.0
    max_balance_cv: float = 0.40
    max_timing_critical_signals: int = 10
    max_clock_crossings_per_partition: int = 4


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------


class PartitionAnalyzer:
    """Analyses a :class:`~models.PartitionDesign` and produces an
    :class:`AnalysisResult`.

    Parameters
    ----------
    thresholds:
        Optional custom thresholds.  Defaults to :class:`AnalysisThresholds`.
    """

    def __init__(
        self, thresholds: Optional[AnalysisThresholds] = None
    ) -> None:
        self.thresholds = thresholds or AnalysisThresholds()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, design: PartitionDesign) -> AnalysisResult:
        """Run all analyses and return a fully-populated
        :class:`AnalysisResult`.

        Parameters
        ----------
        design:
            The design to analyse.
        """
        result = AnalysisResult(design_name=design.name)

        self._compute_partition_metrics(design, result)
        self._compute_interface_metrics(design, result)
        self._compute_design_metrics(design, result)
        self._generate_issues(design, result)

        return result

    # ------------------------------------------------------------------
    # Partition metrics
    # ------------------------------------------------------------------

    def _compute_partition_metrics(
        self, design: PartitionDesign, result: AnalysisResult
    ) -> None:
        cross_signals = design.get_cross_partition_signals()

        # Initialise a metrics object for every partition.
        for pname, partition in design.partitions.items():
            pm = PartitionMetrics(partition_name=pname)
            pm.register_ratio = partition.register_ratio
            if partition.area_mm2 > 0:
                pm.power_density_mw_mm2 = partition.power_mw / partition.area_mm2
            result.partition_metrics[pname] = pm

        # Accumulate signal crossing counts.
        for sig in cross_signals:
            src = sig.source_partition
            if src in result.partition_metrics:
                pm_src = result.partition_metrics[src]
                pm_src.outbound_signal_count += 1
                pm_src.total_cross_partition_signals += 1
                pm_src.outbound_bandwidth_mbps += sig.bandwidth_mbps
                if sig.timing_critical:
                    pm_src.timing_critical_crossings += 1
                if sig.is_clock:
                    pm_src.clock_crossings += 1
                if sig.is_reset:
                    pm_src.reset_crossings += 1

            for sink in sig.sink_partitions:
                if sink == src:
                    continue
                if sink in result.partition_metrics:
                    pm_sink = result.partition_metrics[sink]
                    pm_sink.inbound_signal_count += 1
                    pm_sink.total_cross_partition_signals += 1
                    pm_sink.inbound_bandwidth_mbps += sig.bandwidth_mbps
                    if sig.timing_critical:
                        pm_sink.timing_critical_crossings += 1
                    if sig.is_clock:
                        pm_sink.clock_crossings += 1
                    if sig.is_reset:
                        pm_sink.reset_crossings += 1

        # Count interfaces per partition.
        for iface in design.interfaces:
            for pname in (iface.partition_a, iface.partition_b):
                if pname in result.partition_metrics:
                    result.partition_metrics[pname].interface_count += 1

    # ------------------------------------------------------------------
    # Interface metrics
    # ------------------------------------------------------------------

    def _compute_interface_metrics(
        self, design: PartitionDesign, result: AnalysisResult
    ) -> None:
        cross_signals = design.get_cross_partition_signals()

        for iface in design.interfaces:
            im = InterfaceMetrics(interface_name=iface.name)

            for sig in cross_signals:
                # A signal is routed through this interface if source and at
                # least one sink match the interface's two partitions.
                src = sig.source_partition
                for sink in sig.sink_partitions:
                    if sink == src:
                        continue
                    if iface.connects(src, sink):
                        im.signal_count += 1
                        im.utilized_bandwidth_mbps += sig.bandwidth_mbps
                        if sig.timing_critical:
                            im.timing_critical_signal_count += 1
                        break  # count each signal only once per interface

            max_bw_mbps = iface.max_bandwidth_gbps * 1000.0
            if max_bw_mbps > 0:
                im.utilization_pct = (
                    im.utilized_bandwidth_mbps / max_bw_mbps * 100.0
                )

            result.interface_metrics[iface.name] = im

    # ------------------------------------------------------------------
    # Design-level metrics
    # ------------------------------------------------------------------

    def _compute_design_metrics(
        self, design: PartitionDesign, result: AnalysisResult
    ) -> None:
        dm = result.design_metrics
        dm.partition_count = len(design.partitions)
        dm.total_signal_count = len(design.signals)
        cross = design.get_cross_partition_signals()
        dm.cross_partition_signal_count = len(cross)
        dm.interface_count = len(design.interfaces)

        if dm.total_signal_count > 0:
            dm.cross_partition_ratio = (
                dm.cross_partition_signal_count / dm.total_signal_count
            )

        dm.total_bandwidth_mbps = sum(s.bandwidth_mbps for s in cross)
        dm.timing_critical_crossings = sum(
            1 for s in cross if s.timing_critical
        )

        areas = [p.area_mm2 for p in design.partitions.values()]
        powers = [p.power_mw for p in design.partitions.values()]
        cells = [float(p.cell_count) for p in design.partitions.values()]

        dm.area_balance_score = _coefficient_of_variation(areas)
        dm.power_balance_score = _coefficient_of_variation(powers)
        dm.cell_balance_score = _coefficient_of_variation(cells)

    # ------------------------------------------------------------------
    # Issue generation
    # ------------------------------------------------------------------

    def _generate_issues(
        self, design: PartitionDesign, result: AnalysisResult
    ) -> None:
        t = self.thresholds
        dm = result.design_metrics

        # --- Design-level checks ---

        if dm.total_signal_count == 0 and dm.partition_count > 0:
            result.issues.append(
                AnalysisIssue(
                    severity="WARNING",
                    category="COMPLETENESS",
                    message="No signals defined in the design.",
                    recommendation=(
                        "Add signal definitions so cross-partition analysis "
                        "can be performed."
                    ),
                )
            )

        if (
            dm.cross_partition_ratio > t.max_cross_partition_ratio
            and dm.total_signal_count > 0
        ):
            result.issues.append(
                AnalysisIssue(
                    severity="WARNING",
                    category="PARTITION_QUALITY",
                    message=(
                        f"Cross-partition signal ratio {dm.cross_partition_ratio:.1%} "
                        f"exceeds threshold {t.max_cross_partition_ratio:.1%}."
                    ),
                    recommendation=(
                        "Consider re-partitioning to reduce signal crossings, "
                        "or review whether signals can be internalized."
                    ),
                )
            )

        if dm.timing_critical_crossings > t.max_timing_critical_signals:
            result.issues.append(
                AnalysisIssue(
                    severity="WARNING",
                    category="TIMING",
                    message=(
                        f"{dm.timing_critical_crossings} timing-critical signals "
                        f"cross partition boundaries (threshold: "
                        f"{t.max_timing_critical_signals})."
                    ),
                    recommendation=(
                        "Review timing-critical paths that cross boundaries. "
                        "Consider co-locating related logic or adding retiming."
                    ),
                )
            )

        for metric_name, score in (
            ("area", dm.area_balance_score),
            ("power", dm.power_balance_score),
            ("cell count", dm.cell_balance_score),
        ):
            if score is not None and score > t.max_balance_cv:
                result.issues.append(
                    AnalysisIssue(
                        severity="WARNING",
                        category="BALANCE",
                        message=(
                            f"Partition {metric_name} imbalance detected "
                            f"(CV={score:.2f}, threshold={t.max_balance_cv:.2f})."
                        ),
                        recommendation=(
                            f"Consider rebalancing partition {metric_name} to "
                            "reduce thermal hotspots and improve manufacturing yield."
                        ),
                    )
                )

        if dm.partition_count == 0:
            result.issues.append(
                AnalysisIssue(
                    severity="ERROR",
                    category="COMPLETENESS",
                    message="Design contains no partitions.",
                    recommendation=(
                        "Define at least one partition before running analysis."
                    ),
                )
            )

        # --- Per-partition checks ---

        for pname, pm in result.partition_metrics.items():
            if pm.clock_crossings > t.max_clock_crossings_per_partition:
                result.issues.append(
                    AnalysisIssue(
                        severity="WARNING",
                        category="CLOCK",
                        partition=pname,
                        message=(
                            f"Partition '{pname}' has {pm.clock_crossings} "
                            f"clock crossings (threshold: "
                            f"{t.max_clock_crossings_per_partition})."
                        ),
                        recommendation=(
                            "Excessive clock crossings increase clock-domain "
                            "crossing complexity. Consider clock consolidation."
                        ),
                    )
                )

            partition = design.partitions.get(pname)
            if partition and partition.cell_count > 0:
                if partition.flip_flop_count > partition.cell_count:
                    result.issues.append(
                        AnalysisIssue(
                            severity="ERROR",
                            category="DATA_INTEGRITY",
                            partition=pname,
                            message=(
                                f"Partition '{pname}' has more flip-flops "
                                f"({partition.flip_flop_count}) than total "
                                f"cells ({partition.cell_count})."
                            ),
                            recommendation=(
                                "Verify cell count data — flip-flop count "
                                "cannot exceed total cell count."
                            ),
                        )
                    )

        # --- Per-interface checks ---

        for iname, im in result.interface_metrics.items():
            if im.utilization_pct is not None:
                if im.utilization_pct >= t.max_interface_utilization_error_pct:
                    result.issues.append(
                        AnalysisIssue(
                            severity="ERROR",
                            category="BANDWIDTH",
                            message=(
                                f"Interface '{iname}' utilization "
                                f"{im.utilization_pct:.1f}% exceeds critical "
                                f"threshold {t.max_interface_utilization_error_pct:.1f}%."
                            ),
                            recommendation=(
                                "Interface is over-subscribed. Increase "
                                "bandwidth allocation or redistribute signals "
                                "across multiple interfaces."
                            ),
                        )
                    )
                elif im.utilization_pct >= t.max_interface_utilization_pct:
                    result.issues.append(
                        AnalysisIssue(
                            severity="WARNING",
                            category="BANDWIDTH",
                            message=(
                                f"Interface '{iname}' utilization "
                                f"{im.utilization_pct:.1f}% is high "
                                f"(threshold: {t.max_interface_utilization_pct:.1f}%)."
                            ),
                            recommendation=(
                                "Monitor interface utilization closely. "
                                "Consider adding margin or redistributing signals."
                            ),
                        )
                    )

        # Sort: ERRORs first, then WARNINGs, then INFOs.
        _severity_order = {"ERROR": 0, "WARNING": 1, "INFO": 2}
        result.issues.sort(key=lambda i: _severity_order.get(i.severity, 99))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coefficient_of_variation(values: List[float]) -> Optional[float]:
    """Return the coefficient of variation (std / mean) for *values*.

    Returns ``None`` when the mean is zero or there are fewer than two
    non-zero values.
    """
    non_zero = [v for v in values if v > 0]
    if len(non_zero) < 2:
        return None
    mean = sum(non_zero) / len(non_zero)
    if mean == 0:
        return None
    variance = sum((v - mean) ** 2 for v in non_zero) / len(non_zero)
    return math.sqrt(variance) / mean
