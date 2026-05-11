#!/usr/bin/env python3
"""Experiment 2: AOF rewrite threshold behavior."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from helpers import cli, get_aof_size_bytes, save_result, set_many, start_redis, stop_redis, wait_for_aof_rewrite


CONFIG = "configs/exp2_rewrite.conf"
WORKDIR = "/tmp/ds614-exp2"
AOF = "exp2.aof"
N_KEYS = 1000
N_OVERWRITES = 5


def run():
    print("=" * 60)
    print("EXPERIMENT 2: AOF Rewrite Threshold Behavior")
    print("=" * 60)
    proc = start_redis(CONFIG, WORKDIR, clean=True)
    try:
        cli(6399, "flushall")
        print(f"\nStep 1: Writing {N_KEYS} keys")
        set_many(
            [(f"key:{i}", f"value-initial-{i}-{'x' * 100}") for i in range(N_KEYS)]
        )
        time.sleep(1.2)
        size_after_initial = get_aof_size_bytes(WORKDIR, AOF)
        print(f"  AOF size after initial writes: {size_after_initial:,} bytes")

        print(f"\nStep 2: Overwriting the same keys {N_OVERWRITES} times")
        for pass_num in range(N_OVERWRITES):
            set_many(
                [
                    (f"key:{i}", f"value-overwrite-{pass_num}-{i}-{'y' * 100}")
                    for i in range(N_KEYS)
                ]
            )
        time.sleep(1.2)
        size_before_rewrite = get_aof_size_bytes(WORKDIR, AOF)
        print(f"  AOF size before rewrite: {size_before_rewrite:,} bytes")

        print("\nStep 3: Triggering BGREWRITEAOF")
        cli(6399, "bgrewriteaof", check=False)
        wait_for_aof_rewrite()
        time.sleep(1.0)
        size_after_rewrite = get_aof_size_bytes(WORKDIR, AOF)
        ratio = round(size_before_rewrite / max(size_after_rewrite, 1), 2)
        print(f"  AOF size after rewrite: {size_after_rewrite:,} bytes")
        print(f"  Compression ratio: {ratio}x")

        save_result("exp2", "rewrite_experiment", {
            "n_keys": N_KEYS,
            "n_overwrites": N_OVERWRITES,
            "size_after_initial_bytes": size_after_initial,
            "size_before_rewrite_bytes": size_before_rewrite,
            "size_after_rewrite_bytes": size_after_rewrite,
            "compression_ratio": ratio,
        })
    finally:
        stop_redis(proc)


if __name__ == "__main__":
    run()
