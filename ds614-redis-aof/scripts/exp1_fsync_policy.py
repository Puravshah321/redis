#!/usr/bin/env python3
"""Experiment 1: AOF fsync policy comparison."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from helpers import get_aof_size_bytes, start_redis, stop_redis, cli, write_n_keys, save_result


EXPERIMENTS = [
    ("always", "configs/exp1_always.conf", "/tmp/ds614-exp1-always", "exp1_always.aof"),
    ("everysec", "configs/exp1_everysec.conf", "/tmp/ds614-exp1-everysec", "exp1_everysec.aof"),
    ("no", "configs/exp1_no.conf", "/tmp/ds614-exp1-no", "exp1_no.aof"),
]
N_WRITES = 5000


def run():
    print("=" * 60)
    print("EXPERIMENT 1: AOF fsync Policy Comparison")
    print("=" * 60)
    for label, config, workdir, aof_file in EXPERIMENTS:
        print(f"\n--- Running: appendfsync={label} ---")
        proc = start_redis(config, workdir, clean=True)
        cli(6399, "flushall")
        elapsed = write_n_keys(N_WRITES, prefix=f"exp1:{label}")
        time.sleep(1.2)
        aof_size = get_aof_size_bytes(workdir, aof_file)
        ops_per_sec = round(N_WRITES / elapsed, 2)
        print(f"  Time      : {elapsed:.4f} s")
        print(f"  Throughput: {ops_per_sec} ops/sec")
        print(f"  AOF size  : {aof_size} bytes")
        save_result("exp1", label, {
            "n_writes": N_WRITES,
            "elapsed_sec": round(elapsed, 4),
            "ops_per_sec": ops_per_sec,
            "aof_size_bytes": aof_size,
        })
        stop_redis(proc)
        time.sleep(0.5)


if __name__ == "__main__":
    run()
