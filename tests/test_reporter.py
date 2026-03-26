"""Unit tests for partition_analysis.reporter."""

import json

import pytest

from partition_analysis.analyzer import PartitionAnalyzer
from partition_analysis.models import Interface, Partition, PartitionDesign, Signal
from partition_analysis.reporter import PartitionReporter


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _sample_design() -> PartitionDesign:
    design = PartitionDesign("ReporterTest", "Test design for reporter")
    design.add_partition(
        Partition("A", area_mm2=10.0, power_mw=100.0,
                  cell_count=500, flip_flop_count=125,
                  combinational_cell_count=375)
    )
    design.add_partition(
        Partition("B", area_mm2=12.0, power_mw=120.0,
                  cell_count=600, flip_flop_count=150,
                  combinational_cell_count=450)
    )
    design.add_signal(Signal("xp_sig", "A", ["B"],
                             width=32, frequency_mhz=500.0,
                             timing_critical=True))
    design.add_signal(Signal("int_sig", "A", ["A"],
                             width=8, frequency_mhz=100.0))
    design.add_interface(
        Interface("AB_iface", "A", "B",
                  max_bandwidth_gbps=100.0, latency_ns=10.0,
                  protocol="UCIe", pin_count=256)
    )
    return design


def _make_reporter() -> PartitionReporter:
    design = _sample_design()
    result = PartitionAnalyzer().analyze(design)
    return PartitionReporter(result)


# ---------------------------------------------------------------------------
# Text report tests
# ---------------------------------------------------------------------------


class TestTextReport:
    def test_text_contains_design_name(self):
        reporter = _make_reporter()
        text = reporter.to_text()
        assert "ReporterTest" in text

    def test_text_contains_partition_names(self):
        reporter = _make_reporter()
        text = reporter.to_text()
        assert "Partition: A" in text
        assert "Partition: B" in text

    def test_text_contains_interface_name(self):
        reporter = _make_reporter()
        text = reporter.to_text()
        assert "AB_iface" in text

    def test_text_contains_metrics_headers(self):
        reporter = _make_reporter()
        text = reporter.to_text()
        assert "Design Summary" in text
        assert "Partition Details" in text
        assert "Interface Details" in text
        assert "Issues and Recommendations" in text

    def test_text_no_issues_message(self):
        """A healthy design should show 'No issues found'."""
        design = PartitionDesign("HealthyDesign")
        design.add_partition(Partition("X", area_mm2=10.0, power_mw=50.0,
                                       cell_count=100, flip_flop_count=25,
                                       combinational_cell_count=75))
        design.add_signal(Signal("internal", "X", ["X"], width=4, frequency_mhz=100))
        result = PartitionAnalyzer().analyze(design)
        reporter = PartitionReporter(result)
        text = reporter.to_text()
        assert "No issues found" in text

    def test_text_shows_issue_severity(self):
        """A design with issues should show severity labels."""
        design = PartitionDesign("IssueDesign")
        # Empty design → ERROR
        result = PartitionAnalyzer().analyze(design)
        reporter = PartitionReporter(result)
        text = reporter.to_text()
        assert "[ERROR  ]" in text


# ---------------------------------------------------------------------------
# JSON report tests
# ---------------------------------------------------------------------------


class TestJsonReport:
    def test_json_is_valid(self):
        reporter = _make_reporter()
        data = json.loads(reporter.to_json())
        assert isinstance(data, dict)

    def test_json_contains_design_name(self):
        reporter = _make_reporter()
        data = json.loads(reporter.to_json())
        assert data["design_name"] == "ReporterTest"

    def test_json_has_all_top_level_keys(self):
        reporter = _make_reporter()
        data = json.loads(reporter.to_json())
        for key in ("design_name", "design_metrics", "partition_metrics",
                    "interface_metrics", "issues"):
            assert key in data, f"Missing key: {key}"

    def test_json_partition_metrics_present(self):
        reporter = _make_reporter()
        data = json.loads(reporter.to_json())
        assert "A" in data["partition_metrics"]
        assert "B" in data["partition_metrics"]

    def test_json_interface_metrics_present(self):
        reporter = _make_reporter()
        data = json.loads(reporter.to_json())
        assert "AB_iface" in data["interface_metrics"]


# ---------------------------------------------------------------------------
# CSV report tests
# ---------------------------------------------------------------------------


class TestCsvReport:
    def test_csv_has_header(self):
        reporter = _make_reporter()
        csv_text = reporter.to_csv()
        first_line = csv_text.splitlines()[0]
        assert "partition_name" in first_line
        assert "inbound_signal_count" in first_line

    def test_csv_row_count(self):
        reporter = _make_reporter()
        lines = [l for l in reporter.to_csv().splitlines() if l.strip()]
        # 1 header + 2 partitions
        assert len(lines) == 3

    def test_csv_contains_partition_names(self):
        reporter = _make_reporter()
        csv_text = reporter.to_csv()
        assert "A" in csv_text
        assert "B" in csv_text


# ---------------------------------------------------------------------------
# File-save tests
# ---------------------------------------------------------------------------


class TestFileSave:
    def test_save_text(self, tmp_path):
        reporter = _make_reporter()
        out = tmp_path / "report.txt"
        reporter.save_text(str(out))
        assert out.exists()
        assert len(out.read_text()) > 0

    def test_save_json(self, tmp_path):
        reporter = _make_reporter()
        out = tmp_path / "report.json"
        reporter.save_json(str(out))
        assert out.exists()
        data = json.loads(out.read_text())
        assert "design_name" in data

    def test_save_csv(self, tmp_path):
        reporter = _make_reporter()
        out = tmp_path / "report.csv"
        reporter.save_csv(str(out))
        assert out.exists()
        assert "partition_name" in out.read_text()
