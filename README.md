# mcp_partition_work
ISCP CKT partition review and analysis

A Python tool for **comprehensive analysis and review of Multi-Chip Package
(MCP) circuit partitions**.  It computes detailed metrics, identifies design
issues, and generates reports in plain text, JSON, and CSV formats.

---

## Features

| Category | Details |
|---|---|
| **Signal analysis** | Cross-partition signal count, bandwidth (Mbit/s), timing-critical paths, clock/reset crossings |
| **Interface analysis** | Per-interface bandwidth utilization, timing-critical signal routing |
| **Balance metrics** | Coefficient of variation for area, power, and cell count across partitions |
| **Issue detection** | ERRORs and WARNINGs for bandwidth over-subscription, clock domain crossings, data integrity, and partition quality |
| **Configurable thresholds** | All limits are overridable via CLI flags or the Python API |
| **Output formats** | Plain text, JSON, CSV |

---

## Project structure

```
mcp_partition_work/
├── partition_analysis/      # Core library
│   ├── __init__.py
│   ├── models.py            # Data models: Partition, Signal, Interface, PartitionDesign
│   ├── analyzer.py          # PartitionAnalyzer – computes metrics and issues
│   └── reporter.py          # PartitionReporter – text / JSON / CSV output
├── tests/
│   ├── test_models.py
│   ├── test_analyzer.py
│   └── test_reporter.py
├── examples/
│   └── sample_partition.json   # 3-die sample design (Compute + Memory + IO)
├── main.py                  # CLI entry point
├── requirements.txt
└── README.md
```

---

## Quick start

### Install dependencies

```bash
pip install -r requirements.txt
```

### Run analysis on the sample design

```bash
python main.py examples/sample_partition.json
```

### Write reports to files

```bash
python main.py examples/sample_partition.json \
    --text report.txt --json report.json --csv report.csv
```

### CLI options

```
usage: partition_analysis [-h] [--text FILE] [--json FILE] [--csv FILE]
                          [--max-xp-ratio RATIO] [--max-iface-util PCT]
                          [--max-iface-util-error PCT] [--max-balance-cv CV]
                          [--max-timing-critical N] [--max-clock-crossings N]
                          design_file

positional arguments:
  design_file              Path to a JSON design file

options:
  --text FILE              Write plain-text report to FILE (default: stdout)
  --json FILE              Write JSON report to FILE
  --csv  FILE              Write CSV partition summary to FILE
  --max-xp-ratio RATIO     Max cross-partition signal ratio (default: 0.30)
  --max-iface-util PCT     Interface utilization % warning threshold (default: 80)
  --max-iface-util-error PCT  Interface utilization % error threshold (default: 95)
  --max-balance-cv CV      Max balance CV (default: 0.40)
  --max-timing-critical N  Max timing-critical crossings (default: 10)
  --max-clock-crossings N  Max clock crossings per partition (default: 4)
```

Exit code is `1` when any ERROR-level issue is detected, `0` otherwise.

---

## Python API

```python
from partition_analysis import PartitionAnalyzer, PartitionReporter
from partition_analysis.models import PartitionDesign

# Load a design
design = PartitionDesign.load("examples/sample_partition.json")

# Analyse
result = PartitionAnalyzer().analyze(design)

# Report
reporter = PartitionReporter(result)
print(reporter.to_text())          # plain text
print(reporter.to_json())          # JSON string
print(reporter.to_csv())           # CSV string

# Programmatic access
print(result.design_metrics.cross_partition_ratio)
for issue in result.errors:
    print(issue.message)
```

---

## Design file format

Design files are JSON with the following top-level schema:

```json
{
  "name": "MyDesign",
  "description": "...",
  "partitions": {
    "COMPUTE": {
      "name": "COMPUTE", "die_type": "compute",
      "area_mm2": 45.2, "power_mw": 8500.0,
      "cell_count": 4200000, "flip_flop_count": 1050000,
      "combinational_cell_count": 3150000, "process_node": "3nm",
      "metadata": {}
    }
  },
  "signals": [
    {
      "name": "clk_core", "source_partition": "COMPUTE",
      "sink_partitions": ["MEMORY"],
      "width": 1, "frequency_mhz": 3200.0,
      "is_clock": true, "is_reset": false, "timing_critical": true
    }
  ],
  "interfaces": [
    {
      "name": "COMPUTE_MEMORY_UCIe",
      "partition_a": "COMPUTE", "partition_b": "MEMORY",
      "max_bandwidth_gbps": 2048.0, "latency_ns": 5.0,
      "protocol": "UCIe", "pin_count": 2048
    }
  ]
}
```

See [`examples/sample_partition.json`](examples/sample_partition.json) for a
complete 3-die example.

---

## Running tests

```bash
python -m pytest tests/ -v
```

