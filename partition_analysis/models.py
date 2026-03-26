"""Data models for MCP circuit partition analysis."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Signal:
    """Represents a signal that may cross partition boundaries.

    Attributes:
        name: Unique signal identifier.
        source_partition: Name of the partition that drives this signal.
        sink_partitions: List of partition names that receive this signal.
        width: Bus width in bits (default 1).
        frequency_mhz: Operating frequency in MHz (default 0 = unknown).
        is_clock: Whether the signal is a clock net.
        is_reset: Whether the signal is a reset net.
        timing_critical: Whether the signal lies on a timing-critical path.
    """

    name: str
    source_partition: str
    sink_partitions: List[str]
    width: int = 1
    frequency_mhz: float = 0.0
    is_clock: bool = False
    is_reset: bool = False
    timing_critical: bool = False

    @property
    def is_cross_partition(self) -> bool:
        """Return True when the signal crosses at least one partition boundary."""
        return any(p != self.source_partition for p in self.sink_partitions)

    @property
    def bandwidth_mbps(self) -> float:
        """Estimated bandwidth in Mbit/s (width × frequency)."""
        return self.width * self.frequency_mhz

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "source_partition": self.source_partition,
            "sink_partitions": self.sink_partitions,
            "width": self.width,
            "frequency_mhz": self.frequency_mhz,
            "is_clock": self.is_clock,
            "is_reset": self.is_reset,
            "timing_critical": self.timing_critical,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Signal":
        return cls(
            name=data["name"],
            source_partition=data["source_partition"],
            sink_partitions=data["sink_partitions"],
            width=data.get("width", 1),
            frequency_mhz=data.get("frequency_mhz", 0.0),
            is_clock=data.get("is_clock", False),
            is_reset=data.get("is_reset", False),
            timing_critical=data.get("timing_critical", False),
        )


@dataclass
class Interface:
    """Describes a physical interface between two partitions.

    Attributes:
        name: Unique interface identifier.
        partition_a: First partition name.
        partition_b: Second partition name.
        max_bandwidth_gbps: Maximum interface bandwidth in Gbit/s.
        latency_ns: Interface latency in nanoseconds.
        protocol: Communication protocol (e.g. ``"UCIe"``, ``"HBM"``,
            ``"PCIe"``).
        pin_count: Number of physical pins/bumps on the interface.
    """

    name: str
    partition_a: str
    partition_b: str
    max_bandwidth_gbps: float = 0.0
    latency_ns: float = 0.0
    protocol: str = "unknown"
    pin_count: int = 0

    def connects(self, partition_a: str, partition_b: str) -> bool:
        """Return True when this interface connects the two named partitions."""
        pair = {partition_a, partition_b}
        return {self.partition_a, self.partition_b} == pair

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "partition_a": self.partition_a,
            "partition_b": self.partition_b,
            "max_bandwidth_gbps": self.max_bandwidth_gbps,
            "latency_ns": self.latency_ns,
            "protocol": self.protocol,
            "pin_count": self.pin_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Interface":
        return cls(
            name=data["name"],
            partition_a=data["partition_a"],
            partition_b=data["partition_b"],
            max_bandwidth_gbps=data.get("max_bandwidth_gbps", 0.0),
            latency_ns=data.get("latency_ns", 0.0),
            protocol=data.get("protocol", "unknown"),
            pin_count=data.get("pin_count", 0),
        )


@dataclass
class Partition:
    """Represents a single chip/die partition in an MCP design.

    Attributes:
        name: Unique partition identifier.
        die_type: Technology node or die type (e.g. ``"compute"``,
            ``"memory"``, ``"io"``).
        area_mm2: Physical area in mm².
        power_mw: Estimated power consumption in mW.
        cell_count: Number of logic cells.
        flip_flop_count: Number of flip-flops (registers).
        combinational_cell_count: Number of combinational cells.
        process_node: Manufacturing process node (e.g. ``"3nm"``,
            ``"5nm"``).
        metadata: Additional key/value annotations.
    """

    name: str
    die_type: str = "unknown"
    area_mm2: float = 0.0
    power_mw: float = 0.0
    cell_count: int = 0
    flip_flop_count: int = 0
    combinational_cell_count: int = 0
    process_node: str = "unknown"
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def register_ratio(self) -> Optional[float]:
        """Fraction of cells that are flip-flops, or ``None`` if no cells."""
        if self.cell_count == 0:
            return None
        return self.flip_flop_count / self.cell_count

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "die_type": self.die_type,
            "area_mm2": self.area_mm2,
            "power_mw": self.power_mw,
            "cell_count": self.cell_count,
            "flip_flop_count": self.flip_flop_count,
            "combinational_cell_count": self.combinational_cell_count,
            "process_node": self.process_node,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Partition":
        return cls(
            name=data["name"],
            die_type=data.get("die_type", "unknown"),
            area_mm2=data.get("area_mm2", 0.0),
            power_mw=data.get("power_mw", 0.0),
            cell_count=data.get("cell_count", 0),
            flip_flop_count=data.get("flip_flop_count", 0),
            combinational_cell_count=data.get("combinational_cell_count", 0),
            process_node=data.get("process_node", "unknown"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class PartitionDesign:
    """Top-level container for a complete MCP partition design.

    Attributes:
        name: Design/project name.
        description: Human-readable description.
        partitions: Dictionary mapping partition name to :class:`Partition`.
        signals: List of all signals in the design.
        interfaces: List of physical interfaces between partitions.
    """

    name: str
    description: str = ""
    partitions: Dict[str, Partition] = field(default_factory=dict)
    signals: List[Signal] = field(default_factory=list)
    interfaces: List[Interface] = field(default_factory=list)

    def add_partition(self, partition: Partition) -> None:
        """Add or replace a partition in the design."""
        self.partitions[partition.name] = partition

    def add_signal(self, signal: Signal) -> None:
        """Append a signal to the design."""
        self.signals.append(signal)

    def add_interface(self, interface: Interface) -> None:
        """Append an interface to the design."""
        self.interfaces.append(interface)

    def get_cross_partition_signals(self) -> List[Signal]:
        """Return all signals that cross at least one partition boundary."""
        return [s for s in self.signals if s.is_cross_partition]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "partitions": {k: v.to_dict() for k, v in self.partitions.items()},
            "signals": [s.to_dict() for s in self.signals],
            "interfaces": [i.to_dict() for i in self.interfaces],
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize the design to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "PartitionDesign":
        design = cls(
            name=data["name"],
            description=data.get("description", ""),
        )
        for p_data in data.get("partitions", {}).values():
            design.add_partition(Partition.from_dict(p_data))
        for s_data in data.get("signals", []):
            design.add_signal(Signal.from_dict(s_data))
        for i_data in data.get("interfaces", []):
            design.add_interface(Interface.from_dict(i_data))
        return design

    @classmethod
    def from_json(cls, json_str: str) -> "PartitionDesign":
        """Deserialize a design from a JSON string."""
        return cls.from_dict(json.loads(json_str))

    @classmethod
    def load(cls, filepath: str) -> "PartitionDesign":
        """Load a design from a JSON file."""
        with open(filepath, "r", encoding="utf-8") as fh:
            return cls.from_json(fh.read())

    def save(self, filepath: str) -> None:
        """Save the design to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(self.to_json())
