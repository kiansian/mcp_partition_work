"""Unit tests for partition_analysis.analyzer."""

import pytest

from partition_analysis.analyzer import (
    AnalysisThresholds,
    PartitionAnalyzer,
    _coefficient_of_variation,
)
from partition_analysis.models import (
    Interface,
    Partition,
    PartitionDesign,
    Signal,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_design() -> PartitionDesign:
    """Return a 3-partition design with a mix of internal and
    cross-partition signals and two physical interfaces."""
    design = PartitionDesign("TestDesign")

    design.add_partition(
        Partition("COMPUTE", area_mm2=45.0, power_mw=8500.0,
                  cell_count=4000000, flip_flop_count=1000000,
                  combinational_cell_count=3000000)
    )
    design.add_partition(
        Partition("MEMORY", area_mm2=38.0, power_mw=3200.0,
                  cell_count=800000, flip_flop_count=80000,
                  combinational_cell_count=720000)
    )
    design.add_partition(
        Partition("IO", area_mm2=22.0, power_mw=1800.0,
                  cell_count=350000, flip_flop_count=70000,
                  combinational_cell_count=280000)
    )

    # Cross-partition signals
    design.add_signal(Signal("clk_core", "COMPUTE", ["MEMORY"],
                             width=1, frequency_mhz=3200.0,
                             is_clock=True, timing_critical=True))
    design.add_signal(Signal("mem_data", "COMPUTE", ["MEMORY"],
                             width=256, frequency_mhz=1600.0,
                             timing_critical=True))
    design.add_signal(Signal("mem_read_data", "MEMORY", ["COMPUTE"],
                             width=256, frequency_mhz=1600.0,
                             timing_critical=True))
    design.add_signal(Signal("io_tx", "COMPUTE", ["IO"],
                             width=64, frequency_mhz=1000.0))
    design.add_signal(Signal("io_rx", "IO", ["COMPUTE"],
                             width=64, frequency_mhz=1000.0))
    design.add_signal(Signal("rst_n", "IO", ["COMPUTE", "MEMORY"],
                             width=1, frequency_mhz=0.0, is_reset=True))

    # Internal signals
    design.add_signal(Signal("cpu_bus", "COMPUTE", ["COMPUTE"],
                             width=512, frequency_mhz=3200.0,
                             timing_critical=True))
    design.add_signal(Signal("mem_refresh", "MEMORY", ["MEMORY"],
                             width=4, frequency_mhz=400.0))
    design.add_signal(Signal("io_ctrl", "IO", ["IO"],
                             width=8, frequency_mhz=200.0))

    # Interfaces
    design.add_interface(
        Interface("CM_UCIe", "COMPUTE", "MEMORY",
                  max_bandwidth_gbps=2048.0, latency_ns=5.0,
                  protocol="UCIe", pin_count=2048)
    )
    design.add_interface(
        Interface("CI_UCIe", "COMPUTE", "IO",
                  max_bandwidth_gbps=512.0, latency_ns=8.0,
                  protocol="UCIe", pin_count=512)
    )

    return design


# ---------------------------------------------------------------------------
# PartitionAnalyzer tests
# ---------------------------------------------------------------------------


class TestPartitionAnalyzer:

    def test_basic_analysis_runs(self):
        design = _make_design()
        analyzer = PartitionAnalyzer()
        result = analyzer.analyze(design)
        assert result.design_name == "TestDesign"

    def test_design_metrics_partition_count(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        assert result.design_metrics.partition_count == 3

    def test_design_metrics_total_signals(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        # 9 total signals defined
        assert result.design_metrics.total_signal_count == 9

    def test_design_metrics_cross_partition_count(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        # 6 cross-partition signals (all except cpu_bus, mem_refresh, io_ctrl)
        assert result.design_metrics.cross_partition_signal_count == 6

    def test_design_metrics_cross_partition_ratio(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        expected = 6 / 9
        assert result.design_metrics.cross_partition_ratio == pytest.approx(expected)

    def test_design_metrics_timing_critical_crossings(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        # clk_core (cross), mem_data (cross), mem_read_data (cross) = 3
        assert result.design_metrics.timing_critical_crossings == 3

    def test_partition_metrics_outbound_signals(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        pm = result.partition_metrics["COMPUTE"]
        # COMPUTE drives: clk_core, mem_data, io_tx, rst_n? No, rst_n is from IO.
        # COMPUTE drives: clk_core->MEMORY, mem_data->MEMORY, io_tx->IO  = 3
        assert pm.outbound_signal_count == 3

    def test_partition_metrics_inbound_signals(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        pm = result.partition_metrics["COMPUTE"]
        # COMPUTE receives: mem_read_data from MEMORY, io_rx from IO, rst_n from IO
        assert pm.inbound_signal_count == 3

    def test_partition_metrics_clock_crossings(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        # clk_core crosses from COMPUTE to MEMORY
        assert result.partition_metrics["COMPUTE"].clock_crossings == 1
        assert result.partition_metrics["MEMORY"].clock_crossings == 1
        assert result.partition_metrics["IO"].clock_crossings == 0

    def test_partition_metrics_reset_crossings(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        # rst_n from IO to COMPUTE and MEMORY
        assert result.partition_metrics["IO"].reset_crossings == 1
        assert result.partition_metrics["COMPUTE"].reset_crossings == 1
        assert result.partition_metrics["MEMORY"].reset_crossings == 1

    def test_interface_metrics_signal_count(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        im_cm = result.interface_metrics["CM_UCIe"]
        # COMPUTE<->MEMORY: clk_core (COMPUTE→MEMORY), mem_data (COMPUTE→MEMORY),
        # mem_read_data (MEMORY→COMPUTE) = 3.
        # rst_n goes IO→COMPUTE and IO→MEMORY, not through this interface.
        assert im_cm.signal_count == 3

    def test_interface_metrics_utilization(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        im_cm = result.interface_metrics["CM_UCIe"]
        assert im_cm.utilization_pct is not None
        assert im_cm.utilization_pct > 0

    def test_partition_metrics_power_density(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        pm = result.partition_metrics["COMPUTE"]
        assert pm.power_density_mw_mm2 == pytest.approx(8500.0 / 45.0)

    def test_partition_metrics_interface_count(self):
        design = _make_design()
        result = PartitionAnalyzer().analyze(design)
        assert result.partition_metrics["COMPUTE"].interface_count == 2
        assert result.partition_metrics["MEMORY"].interface_count == 1
        assert result.partition_metrics["IO"].interface_count == 1

    def test_no_issues_for_healthy_design(self):
        """A very simple 2-partition design with few crossings should produce
        no ERRORs and ideally no WARNINGs."""
        design = PartitionDesign("SimpleDesign")
        design.add_partition(Partition("A", area_mm2=10.0, power_mw=100.0,
                                       cell_count=100, flip_flop_count=25,
                                       combinational_cell_count=75))
        design.add_partition(Partition("B", area_mm2=10.0, power_mw=100.0,
                                       cell_count=100, flip_flop_count=25,
                                       combinational_cell_count=75))
        design.add_signal(Signal("s_internal_a", "A", ["A"], width=1, frequency_mhz=100))
        design.add_signal(Signal("s_internal_b", "B", ["B"], width=1, frequency_mhz=100))
        design.add_signal(Signal("s_cross", "A", ["B"], width=4, frequency_mhz=100))
        design.add_interface(Interface("iface", "A", "B",
                                       max_bandwidth_gbps=10.0))

        result = PartitionAnalyzer().analyze(design)
        assert len(result.errors) == 0

    def test_error_on_empty_design(self):
        design = PartitionDesign("EmptyDesign")
        result = PartitionAnalyzer().analyze(design)
        errors = [i for i in result.errors if i.category == "COMPLETENESS"]
        assert len(errors) >= 1

    def test_warning_high_cross_partition_ratio(self):
        """Trigger the cross-partition ratio warning."""
        design = PartitionDesign("HighXPDesign")
        design.add_partition(Partition("A"))
        design.add_partition(Partition("B"))
        # 9 cross-partition, 1 internal → ratio = 0.9 > 0.30 threshold
        for i in range(9):
            design.add_signal(Signal(f"xp_{i}", "A", ["B"], width=1, frequency_mhz=100))
        design.add_signal(Signal("internal", "A", ["A"], width=1, frequency_mhz=100))

        result = PartitionAnalyzer().analyze(design)
        warnings = [i for i in result.warnings if i.category == "PARTITION_QUALITY"]
        assert len(warnings) >= 1

    def test_warning_high_interface_utilization(self):
        """Trigger the interface bandwidth warning."""
        design = PartitionDesign("HighBWDesign")
        design.add_partition(Partition("A"))
        design.add_partition(Partition("B"))
        # 1 Gbit/s signal on a 1 Gbit/s interface → 100% → ERROR
        design.add_signal(Signal("big_sig", "A", ["B"],
                                 width=1000, frequency_mhz=1000.0))
        design.add_interface(Interface("tiny_iface", "A", "B",
                                       max_bandwidth_gbps=1.0))

        result = PartitionAnalyzer().analyze(design)
        bw_issues = [i for i in result.issues if i.category == "BANDWIDTH"]
        assert len(bw_issues) >= 1

    def test_error_flip_flop_exceeds_cell_count(self):
        design = PartitionDesign("BadData")
        design.add_partition(Partition("X", cell_count=100, flip_flop_count=200,
                                       combinational_cell_count=0))
        result = PartitionAnalyzer().analyze(design)
        errors = [i for i in result.errors if i.category == "DATA_INTEGRITY"]
        assert len(errors) == 1
        assert errors[0].partition == "X"

    def test_clock_crossing_warning(self):
        """Trigger the per-partition clock crossing warning."""
        design = PartitionDesign("ManyClocksDesign")
        design.add_partition(Partition("SRC"))
        design.add_partition(Partition("DST"))
        for i in range(5):
            design.add_signal(Signal(f"clk_{i}", "SRC", ["DST"],
                                     width=1, frequency_mhz=100.0, is_clock=True))

        t = AnalysisThresholds(max_clock_crossings_per_partition=4)
        result = PartitionAnalyzer(thresholds=t).analyze(design)
        clock_warnings = [i for i in result.warnings if i.category == "CLOCK"]
        assert len(clock_warnings) >= 1

    def test_no_signals_warning(self):
        design = PartitionDesign("NoSignals")
        design.add_partition(Partition("A"))
        design.add_partition(Partition("B"))
        result = PartitionAnalyzer().analyze(design)
        warnings = [i for i in result.warnings if i.category == "COMPLETENESS"]
        assert len(warnings) >= 1

    def test_custom_thresholds_respected(self):
        """Verify that custom thresholds change issue generation."""
        design = PartitionDesign("ThresholdTest")
        design.add_partition(Partition("A"))
        design.add_partition(Partition("B"))
        design.add_signal(Signal("xp", "A", ["B"], width=1, frequency_mhz=0))
        design.add_signal(Signal("in", "A", ["A"], width=1, frequency_mhz=0))

        # Default threshold 0.30 — ratio is 0.5 → warning expected
        r1 = PartitionAnalyzer().analyze(design)
        w1 = [i for i in r1.warnings if i.category == "PARTITION_QUALITY"]
        assert len(w1) >= 1

        # Very high threshold — no warning expected
        t2 = AnalysisThresholds(max_cross_partition_ratio=0.99)
        r2 = PartitionAnalyzer(thresholds=t2).analyze(design)
        w2 = [i for i in r2.warnings if i.category == "PARTITION_QUALITY"]
        assert len(w2) == 0

    def test_issues_sorted_errors_first(self):
        """ERRORs must appear before WARNINGs in the issues list."""
        design = PartitionDesign("SortTest")
        # Empty design → ERROR(COMPLETENESS), plus no signals → WARNING
        result = PartitionAnalyzer().analyze(design)
        severities = [i.severity for i in result.issues]
        # Once we find the first WARNING there must be no ERROR after it
        found_warning = False
        for s in severities:
            if s == "WARNING":
                found_warning = True
            if found_warning and s == "ERROR":
                pytest.fail("ERROR found after WARNING in issues list")


# ---------------------------------------------------------------------------
# _coefficient_of_variation tests
# ---------------------------------------------------------------------------


class TestCoefficientOfVariation:
    def test_equal_values(self):
        cv = _coefficient_of_variation([10.0, 10.0, 10.0])
        assert cv == pytest.approx(0.0)

    def test_known_values(self):
        # mean=2, values=[1,2,3], std=sqrt(2/3)
        cv = _coefficient_of_variation([1.0, 2.0, 3.0])
        import math
        expected = math.sqrt(2 / 3) / 2.0
        assert cv == pytest.approx(expected, rel=1e-5)

    def test_single_non_zero(self):
        assert _coefficient_of_variation([5.0]) is None

    def test_all_zeros(self):
        assert _coefficient_of_variation([0.0, 0.0]) is None

    def test_one_non_zero_rest_zero(self):
        # Only one non-zero value → returns None
        assert _coefficient_of_variation([0.0, 5.0, 0.0]) is None

    def test_empty_list(self):
        assert _coefficient_of_variation([]) is None
