#!/usr/bin/env python3
"""Experiment 4: AOF vs RDB write throughput."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from helpers import cli, save_result, start_redis, stop_redis, write_n_keys


MODES = [
    ("AOF_everysec", "configs/exp4_aof.conf", "/tmp/ds614-exp4-aof"),
    ("RDB_snapshot", "configs/exp4_rdb.conf", "/tmp/ds614-exp4-rdb"),
]
BATCH_SIZES = [1000, 5000, 10000]


def run():
    print("=" * 60)
    print("EXPERIMENT 4: AOF vs RDB Write Throughput")
    print("=" * 60)
    for label, config, workdir in MODES:
        print(f"\n--- Mode: {label} ---")
        proc = start_redis(config, workdir, clean=True)
        try:
            for n in BATCH_SIZES:
                cli(6399, "flushall")
                elapsed = write_n_keys(n, prefix=f"exp4:{label}:{n}")
                ops_per_sec = round(n / elapsed, 2)
                print(f"  n={n:>6} | {elapsed:.4f}s | {ops_per_sec} ops/sec")
                save_result("exp4", label, {
                    "n_writes": n,
                    "elapsed_sec": round(elapsed, 4),
                    "ops_per_sec": ops_per_sec,
                })
        finally:
            stop_redis(proc)
            time.sleep(0.5)


if __name__ == "__main__":
    run()
