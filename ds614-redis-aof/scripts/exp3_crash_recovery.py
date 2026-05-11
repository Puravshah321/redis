#!/usr/bin/env python3
"""Experiment 3: AOF recovery after simulated crash."""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from helpers import cli, kill_redis_hard, pipe_commands, save_result, start_redis, stop_redis


CONFIG = "configs/exp3_crash.conf"
WORKDIR = "/tmp/ds614-exp3"
N_KEYS = 2000


def run():
    print("=" * 60)
    print("EXPERIMENT 3: AOF Recovery After Simulated Crash")
    print("=" * 60)

    print(f"\nPhase 1: Starting Redis and writing {N_KEYS} keys")
    proc = start_redis(CONFIG, WORKDIR, clean=True)
    cli(6399, "flushall")
    expected = {}
    commands = []
    for i in range(N_KEYS):
        key = f"crash:key:{i}"
        value = f"verified-value-{i}"
        expected[key] = value
        commands.append(f"SET {key} {value}\n")
    pipe_commands(commands)
    print(f"  Written {N_KEYS} keys.")

    print("\nPhase 2: Waiting for fsync, then SIGKILL")
    time.sleep(2.5)
    kill_redis_hard(proc)
    time.sleep(1.0)
    print("  Redis killed with SIGKILL.")

    print("\nPhase 3: Restarting Redis and verifying replayed keys")
    proc2 = start_redis(CONFIG, WORKDIR, clean=False)
    time.sleep(1.0)
    recovered = 0
    lost = 0
    wrong_value = 0
    for key, expected_val in expected.items():
        actual = cli(6399, "get", key, check=False)
        if actual == "":
            lost += 1
        elif actual != expected_val:
            wrong_value += 1
        else:
            recovered += 1

    recovery_rate = round(recovered / N_KEYS * 100, 2)
    print(f"  Keys recovered : {recovered}")
    print(f"  Keys lost      : {lost}")
    print(f"  Wrong values   : {wrong_value}")
    print(f"  Recovery rate  : {recovery_rate}%")
    save_result("exp3", "crash_recovery", {
        "n_keys": N_KEYS,
        "recovered": recovered,
        "lost": lost,
        "wrong_value": wrong_value,
        "recovery_rate_pct": recovery_rate,
    })
    stop_redis(proc2)


if __name__ == "__main__":
    run()
