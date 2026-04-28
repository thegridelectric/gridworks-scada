#!/usr/bin/env python3
"""
Plot RAM usage from monitor_ram.py output.

Usage:
    python scripts/plot_ram.py monitor_ram_20250304_123456.csv
    python scripts/plot_ram.py ram.csv -o ram_plot.png
"""

import argparse
import csv
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", help="CSV produced by monitor_ram.py")
    parser.add_argument("-o", "--output", help="Output image file (default: <csv>.png)")
    args = parser.parse_args()

    try:
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("Install matplotlib: pip install matplotlib")
        return 1

    path = Path(args.csv_file)
    if not path.exists():
        print(f"File not found: {path}")
        return 1
    out_path = args.output or path.with_suffix(".png")

    times = []
    used_gb = []
    avail_gb = []
    total_gb = []

    with open(path) as f:
        r = csv.DictReader(f)
        for row in r:
            times.append(datetime.fromisoformat(row["timestamp_iso"]))
            used_gb.append(float(row["used_gb"]))
            avail_gb.append(float(row["available_gb"]))
            total_gb.append(float(row["total_gb"]))

    if not times:
        print("No data in CSV")
        return 1

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.fill_between(times, 0, used_gb, alpha=0.7, label="Used")
    ax.fill_between(times, used_gb, [u + a for u, a in zip(used_gb, avail_gb)], alpha=0.5, label="Available")
    ax.set_ylabel("GB")
    ax.set_xlabel("Time")
    ax.set_title(f"RAM usage - {path.name}")
    ax.legend(loc="upper right")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    fig.autofmt_xdate()
    plt.tight_layout()
    plt.savefig(out_path, dpi=100)
    print(f"Saved {out_path}")
    return 0


if __name__ == "__main__":
    exit(main())
