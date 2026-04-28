#!/usr/bin/env python3
"""
Monitor RAM usage on Linux, logging for later analysis/plotting.

Usage:
    python scripts/monitor_ram.py                    # logs to monitor_ram_<timestamp>.csv
    python scripts/monitor_ram.py -o ram.csv        # custom output file
    python scripts/monitor_ram.py -i 5 -t 100       # sample every 5s, log when change > 100 MB

Runs until Ctrl+C. Run in tmux or: nohup python scripts/monitor_ram.py &
"""

import argparse
import signal
import sys
import time
from datetime import datetime
from pathlib import Path


def get_mem_info():
    """Read /proc/meminfo (Linux). Returns dict with bytes."""
    result = {}
    with open("/proc/meminfo") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                # values are in kB
                val_kb = int(parts[1])
                result[key] = val_kb * 1024
    return result


def sample_ram():
    """Return (used_gb, available_gb, total_gb) for system RAM."""
    mem = get_mem_info()
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", mem.get("MemFree", 0))
    used = total - available
    return used / (1024**3), available / (1024**3), total / (1024**3)


def main():
    parser = argparse.ArgumentParser(description="Monitor RAM usage, log for plotting.")
    parser.add_argument("-o", "--output", help="Output CSV file (default: monitor_ram_<timestamp>.csv)")
    parser.add_argument("-i", "--interval", type=float, default=2.0, help="Sample interval in seconds (default: 2)")
    parser.add_argument(
        "-t",
        "--threshold-mb",
        type=float,
        default=0,
        help="Only log when used RAM changes by more than this many MB (0 = log every sample)",
    )
    args = parser.parse_args()

    out_path = Path(
        args.output or f"monitor_ram_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )
    interval = max(0.5, args.interval)
    threshold_bytes = args.threshold_mb * 1024 * 1024 if args.threshold_mb else 0

    last_used = None
    running = [True]

    def stop(signum, frame):
        running[0] = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    try:
        with open(out_path, "w") as f:
            f.write("timestamp_iso,unix_ts,used_gb,available_gb,total_gb\n")
            f.flush()

            print(f"Logging RAM to {out_path} every {interval}s (Ctrl+C to stop)", file=sys.stderr)

            while running[0]:
                ts = time.time()
                used_gb, avail_gb, total_gb = sample_ram()
                used_bytes = used_gb * (1024**3)

                should_log = True
                if threshold_bytes > 0 and last_used is not None:
                    should_log = abs(used_bytes - last_used) >= threshold_bytes
                last_used = used_bytes

                if should_log:
                    iso = datetime.now().isoformat()
                    f.write(f"{iso},{ts:.1f},{used_gb:.4f},{avail_gb:.4f},{total_gb:.4f}\n")
                    f.flush()
                    print(f"{iso}  used={used_gb:.2f} GB  avail={avail_gb:.2f} GB", file=sys.stderr)

                time.sleep(interval)

    except FileNotFoundError:
        print("Error: /proc/meminfo not found. This script is for Linux.", file=sys.stderr)
        sys.exit(1)
    finally:
        print(f"Stopped. Data saved to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
