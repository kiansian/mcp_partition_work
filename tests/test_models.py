"""Unit tests for partition_analysis.models."""

import json
import os
import tempfile

import pytest

from partition_analysis.models import (
    Interface,
    Partition,
    PartitionDesign,
    Signal,
)


# ---------------------------------------------------------------------------
# Signal tests
# ---------------------------------------------------------------------------


class TestSignal:
    def test_is_cross_partition_true(self):
        sig = Signal("s1", "A", ["B"])
        assert sig.is_cross_partition is True

    def test_is_cross_partition_false(self):
        sig = Signal("s1", "A", ["A"])
        assert sig.is_cross_partition is False

    def test_is_cross_partition_mixed(self):
        # Source also in sinks, but other sinks differ — still cross-partition.
        sig = Signal("s1", "A", ["A", "B"])
        assert sig.is_cross_partition is True

    def test_bandwidth_mbps(self):
        sig = Signal("s1", "A", ["B"], width=64, frequency_mhz=1000.0)
        assert sig.bandwidth_mbps == pytest.approx(64000.0)

    def test_bandwidth_mbps_zero_frequency(self):
        sig = Signal("s1", "A", ["B"], width=32, frequency_mhz=0.0)
        assert sig.bandwidth_mbps == pytest.approx(0.0)

    def test_to_dict_roundtrip(self):
        sig = Signal(
            "clk",
            "COMPUTE",
            ["MEMORY", "IO"],
            width=1,
            frequency_mhz=3200.0,
            is_clock=True,
            is_reset=False,
            timing_critical=True,
        )
        d = sig.to_dict()
        sig2 = Signal.from_dict(d)
        assert sig2.name == sig.name
        assert sig2.source_partition == sig.source_partition
        assert sig2.sink_partitions == sig.sink_partitions
        assert sig2.width == sig.width
        assert sig2.frequency_mhz == sig.frequency_mhz
        assert sig2.is_clock == sig.is_clock
        assert sig2.timing_critical == sig.timing_critical

    def test_from_dict_defaults(self):
        sig = Signal.from_dict({"name": "x", "source_partition": "A", "sink_partitions": ["B"]})
        assert sig.width == 1
        assert sig.frequency_mhz == 0.0
        assert sig.is_clock is False
        assert sig.is_reset is False
        assert sig.timing_critical is False


# ---------------------------------------------------------------------------
# Interface tests
# ---------------------------------------------------------------------------


class TestInterface:
    def test_connects_true(self):
        iface = Interface("i1", "A", "B")
        assert iface.connects("A", "B") is True
        assert iface.connects("B", "A") is True  # order-independent

    def test_connects_false(self):
        iface = Interface("i1", "A", "B")
        assert iface.connects("A", "C") is False

    def test_to_dict_roundtrip(self):
        iface = Interface(
            "UCIe_AB", "COMPUTE", "MEMORY",
            max_bandwidth_gbps=1024.0,
            latency_ns=5.0,
            protocol="UCIe",
            pin_count=1024,
        )
        iface2 = Interface.from_dict(iface.to_dict())
        assert iface2.name == iface.name
        assert iface2.max_bandwidth_gbps == iface.max_bandwidth_gbps
        assert iface2.protocol == iface.protocol

    def test_from_dict_defaults(self):
        iface = Interface.from_dict({"name": "i1", "partition_a": "A", "partition_b": "B"})
        assert iface.max_bandwidth_gbps == 0.0
        assert iface.latency_ns == 0.0
        assert iface.protocol == "unknown"
        assert iface.pin_count == 0


# ---------------------------------------------------------------------------
# Partition tests
# ---------------------------------------------------------------------------


class TestPartition:
    def test_register_ratio(self):
        p = Partition("P", cell_count=1000, flip_flop_count=250)
        assert p.register_ratio == pytest.approx(0.25)

    def test_register_ratio_zero_cells(self):
        p = Partition("P", cell_count=0, flip_flop_count=0)
        assert p.register_ratio is None

    def test_to_dict_roundtrip(self):
        p = Partition(
            "COMPUTE",
            die_type="compute",
            area_mm2=45.2,
            power_mw=8500.0,
            cell_count=4000000,
            flip_flop_count=1000000,
            combinational_cell_count=3000000,
            process_node="3nm",
            metadata={"team": "Core"},
        )
        p2 = Partition.from_dict(p.to_dict())
        assert p2.name == p.name
        assert p2.area_mm2 == p.area_mm2
        assert p2.process_node == p.process_node
        assert p2.metadata == p.metadata

    def test_from_dict_defaults(self):
        p = Partition.from_dict({"name": "X"})
        assert p.die_type == "unknown"
        assert p.area_mm2 == 0.0
        assert p.cell_count == 0
        assert p.metadata == {}


# ---------------------------------------------------------------------------
# PartitionDesign tests
# ---------------------------------------------------------------------------


class TestPartitionDesign:
    def _simple_design(self) -> PartitionDesign:
        design = PartitionDesign("TestDesign", "A test design")
        design.add_partition(Partition("A", area_mm2=10.0, power_mw=100.0))
        design.add_partition(Partition("B", area_mm2=12.0, power_mw=120.0))
        design.add_signal(Signal("s1", "A", ["B"], width=8, frequency_mhz=100.0))
        design.add_signal(Signal("s2", "A", ["A"]))  # internal
        design.add_interface(Interface("iface_AB", "A", "B"))
        return design

    def test_get_cross_partition_signals(self):
        design = self._simple_design()
        xp = design.get_cross_partition_signals()
        assert len(xp) == 1
        assert xp[0].name == "s1"

    def test_to_json_from_json_roundtrip(self):
        design = self._simple_design()
        json_str = design.to_json()
        data = json.loads(json_str)
        design2 = PartitionDesign.from_json(json_str)
        assert design2.name == design.name
        assert set(design2.partitions.keys()) == set(design.partitions.keys())
        assert len(design2.signals) == len(design.signals)
        assert len(design2.interfaces) == len(design.interfaces)

    def test_save_and_load(self):
        design = self._simple_design()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "design.json")
            design.save(path)
            assert os.path.exists(path)
            loaded = PartitionDesign.load(path)
            assert loaded.name == design.name
            assert len(loaded.partitions) == len(design.partitions)
            assert len(loaded.signals) == len(design.signals)

    def test_load_sample_file(self):
        """Load the bundled sample design file."""
        sample_path = os.path.join(
            os.path.dirname(__file__), "..", "examples", "sample_partition.json"
        )
        design = PartitionDesign.load(os.path.abspath(sample_path))
        assert design.name == "SampleMCPDesign"
        assert len(design.partitions) == 3
        assert "COMPUTE" in design.partitions
        assert "MEMORY" in design.partitions
        assert "IO" in design.partitions
        assert len(design.signals) > 0
        assert len(design.interfaces) == 2
