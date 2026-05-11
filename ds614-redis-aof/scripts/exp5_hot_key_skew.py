#!/usr/bin/env python3
"""Experiment 5: AOF under write skew / hot key workload."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from helpers import cli, get_aof_size_bytes, pipe_commands, save_result, start_redis, stop_redis, wait_for_aof_rewrite


CONFIG = "configs/exp5_skew.conf"
WORKDIR = "/tmp/ds614-exp5"
AOF = "exp5.aof"
N = 5000


def run():
    print("=" * 60)
    print("EXPERIMENT 5: AOF Under Write Skew (Hot Key)")
    print("=" * 60)
    for label, hot in [("uniform", False), ("hot_key", True)]:
        print(f"\n--- Workload: {label} ---")
        proc = start_redis(CONFIG, WORKDIR, clean=True)
        try:
            cli(6399, "flushall")
            commands = []
            for i in range(N):
                key = "hotkey:ONE" if hot else f"uniform:key:{i}"
                commands.append(f"SET {key} value-{i}-{'z' * 80}\n")
            pipe_commands(commands)
            time.sleep(1.2)
            size_before = get_aof_size_bytes(WORKDIR, AOF)
            print(f"  AOF size before rewrite: {size_before:,} bytes")

            cli(6399, "bgrewriteaof")
            wait_for_aof_rewrite()
            time.sleep(1.0)
            size_after = get_aof_size_bytes(WORKDIR, AOF)
            ratio = round(size_before / max(size_after, 1), 2)
            print(f"  AOF size after rewrite : {size_after:,} bytes")
            print(f"  Compression ratio      : {ratio}x")
            save_result("exp5", label, {
                "n_writes": N,
                "is_hot_key": hot,
                "size_before_bytes": size_before,
                "size_after_bytes": size_after,
                "compression_ratio": ratio,
            })
        finally:
            stop_redis(proc)
            time.sleep(0.5)


if __name__ == "__main__":
    run()
