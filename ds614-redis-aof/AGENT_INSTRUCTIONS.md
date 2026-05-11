# Redis AOF Persistence — DS614 Final Project
## Agent Instructions (VSCode Codex / Copilot Agent)

> **READ THIS ENTIRE FILE BEFORE DOING ANYTHING.**
> This file is the single source of truth. Follow every step in order.
> Do not skip sections. Do not use `sudo`. All commands run as a normal college PC user.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Environment Setup](#2-environment-setup)
3. [Repository Structure to Create](#3-repository-structure-to-create)
4. [Baseline: Understanding Redis AOF](#4-baseline-understanding-redis-aof)
5. [Experiment 1 — AOF fsync Policy Comparison](#5-experiment-1--aof-fsync-policy-comparison)
6. [Experiment 2 — AOF Rewrite Threshold Behavior](#6-experiment-2--aof-rewrite-threshold-behavior)
7. [Experiment 3 — AOF Recovery After Simulated Crash](#7-experiment-3--aof-recovery-after-simulated-crash)
8. [Experiment 4 — AOF vs RDB Write Throughput](#8-experiment-4--aof-vs-rdb-write-throughput)
9. [Experiment 5 — AOF Under Write Skew (Hot Key)](#9-experiment-5--aof-under-write-skew-hot-key)
10. [Final Report Generation](#10-final-report-generation)
11. [Presentation Slides Outline](#11-presentation-slides-outline)
12. [Penalization Checklist](#12-penalization-checklist)

---

## 1. Project Overview

**Topic:** Redis AOF (Append-Only File) Persistence  
**Course:** DS614 — Data Systems  
**System Under Study:** Redis (open-source, in-memory data store)  
**Focus:** How Redis guarantees durability using the AOF persistence mechanism

### What AOF Solves
Redis is an in-memory store — all data lives in RAM. If the process dies, data is lost.  
AOF fixes this by **appending every write command** to a log file on disk. On restart, Redis replays this log to reconstruct state.

### Key Source Files to Reference in the Report
These are real Redis source files. The agent must look them up on GitHub (`https://github.com/redis/redis`) and reference actual function names in all writeups.

| File | What it Does |
|---|---|
| `src/aof.c` | Core AOF logic: `feedAppendOnlyFile()`, `flushAppendOnlyFile()`, `rewriteAppendOnlyFileBackground()` |
| `src/server.h` | Config structs: `struct redisServer` — fields `aof_state`, `aof_fsync`, `aof_rewrite_perc` |
| `src/config.c` | Parses `appendfsync` config option |
| `src/rdb.c` | RDB (snapshot) persistence — used for comparison in Experiment 4 |

---

## 2. Environment Setup

> All steps use only user-level installs. No `sudo` at any point.

### 2.1 Check Prerequisites

```bash
# Check if Redis is installed
redis-server --version

# Check Python
python3 --version

# Check pip
pip3 --version
```

If `redis-server` is not found, install it locally:

```bash
# Download Redis source (no sudo needed to compile)
cd ~
wget https://download.redis.io/redis-stable.tar.gz
tar -xzf redis-stable.tar.gz
cd redis-stable
make
# Binaries are now at ~/redis-stable/src/redis-server and ~/redis-stable/src/redis-cli
# Add to PATH for this session:
export PATH="$HOME/redis-stable/src:$PATH"
# Verify
redis-server --version
```

### 2.2 Install Python Dependencies (user-level)

```bash
pip3 install redis matplotlib pandas tabulate --user
```

### 2.3 Create Project Directory

```bash
mkdir -p ~/ds614-redis-aof
cd ~/ds614-redis-aof
git init
```

---

## 3. Repository Structure to Create

The agent must create **exactly** this directory and file structure:

```
ds614-redis-aof/
├── AGENT_INSTRUCTIONS.md          ← this file (copy here)
├── configs/
│   ├── baseline.conf
│   ├── exp1_always.conf
│   ├── exp1_no.conf
│   ├── exp1_everysec.conf
│   ├── exp2_rewrite.conf
│   ├── exp3_crash.conf
│   ├── exp4_rdb.conf
│   └── exp5_skew.conf
├── scripts/
│   ├── helpers.py                 ← shared utility functions
│   ├── exp1_fsync_policy.py
│   ├── exp2_rewrite.py
│   ├── exp3_crash_recovery.py
│   ├── exp4_aof_vs_rdb.py
│   └── exp5_hot_key_skew.py
├── results/
│   ├── exp1/
│   ├── exp2/
│   ├── exp3/
│   ├── exp4/
│   └── exp5/
├── plots/
│   (generated PNG files land here)
└── README.md                      ← generated at the very end
```

Create it now:

```bash
cd ~/ds614-redis-aof
mkdir -p configs scripts results/exp1 results/exp2 results/exp3 results/exp4 results/exp5 plots
```

---

## 4. Baseline: Understanding Redis AOF

### 4.1 Create Baseline Redis Config

Create file `configs/baseline.conf`:

```conf
# configs/baseline.conf
# Baseline Redis configuration for DS614 AOF experiments
# NO sudo needed — all paths are relative to the project dir

port 6399
daemonize no
loglevel notice
logfile ""

# --- Persistence ---
# Enable AOF
appendonly yes
appendfilename "baseline.aof"
appendfsync everysec

# Disable RDB snapshots for clean AOF-only baseline
save ""

# AOF rewrite
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb

# Working directory — all AOF files land here
dir /tmp/ds614-baseline
```

### 4.2 Create the helpers.py Script

Create file `scripts/helpers.py`:

```python
# scripts/helpers.py
# Shared utilities for all DS614 Redis AOF experiments

import subprocess
import time
import os
import redis
import signal

REDIS_BIN = "redis-server"   # assumes in PATH; change to ~/redis-stable/src/redis-server if needed
REDIS_CLI = "redis-cli"

def start_redis(config_path, working_dir):
    """Start a Redis server with the given config. Returns the Popen process."""
    os.makedirs(working_dir, exist_ok=True)
    proc = subprocess.Popen(
        [REDIS_BIN, config_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    time.sleep(1.0)  # give Redis time to start
    return proc

def stop_redis(proc, port=6399):
    """Gracefully shut down Redis."""
    try:
        r = redis.Redis(host='127.0.0.1', port=port)
        r.shutdown(nosave=True)
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        pass

def kill_redis_hard(proc):
    """Simulate a crash — SIGKILL, no clean shutdown."""
    try:
        os.kill(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

def get_redis_client(port=6399):
    """Return a connected redis-py client."""
    return redis.Redis(host='127.0.0.1', port=port, decode_responses=True)

def flush_and_prepare(port=6399):
    """Flush all keys before an experiment."""
    r = get_redis_client(port)
    r.flushall()

def write_n_keys(r, n, prefix="key"):
    """Write n string keys and return elapsed time in seconds."""
    start = time.time()
    pipe = r.pipeline(transaction=False)
    for i in range(n):
        pipe.set(f"{prefix}:{i}", f"value-{i}-{'x'*50}")
        if i % 500 == 0:
            pipe.execute()
    pipe.execute()
    return time.time() - start

def get_aof_size_bytes(working_dir, aof_filename):
    """Return the size of the AOF file in bytes, or 0 if not found."""
    path = os.path.join(working_dir, aof_filename)
    if os.path.exists(path):
        return os.path.getsize(path)
    return 0

def save_result(exp_name, label, data: dict):
    """Append a result row to results/<exp_name>/results.tsv"""
    os.makedirs(f"results/{exp_name}", exist_ok=True)
    filepath = f"results/{exp_name}/results.tsv"
    write_header = not os.path.exists(filepath)
    with open(filepath, "a") as f:
        if write_header:
            f.write("\t".join(["label"] + list(data.keys())) + "\n")
        f.write("\t".join([label] + [str(v) for v in data.values()]) + "\n")
    print(f"[SAVED] {exp_name}/{label}: {data}")
```

---

## 5. Experiment 1 — AOF fsync Policy Comparison

### What We Are Testing
Redis has three `appendfsync` modes:

| Mode | Behavior | Durability | Performance |
|---|---|---|---|
| `always` | fsync after every write | Strongest (0 data loss) | Slowest |
| `everysec` | fsync once per second | At most 1 second of loss | Balanced |
| `no` | OS decides when to fsync | Weakest (OS buffer) | Fastest |

**Code reference:** `src/aof.c` → `flushAppendOnlyFile()` — the `force` parameter controls whether fsync is called.  
**Config reference:** `src/config.c` → parsing of `appendfsync` maps to `server.aof_fsync`.

### 5.1 Create the Three Config Files

Create `configs/exp1_always.conf`:
```conf
port 6399
daemonize no
appendonly yes
appendfilename "exp1_always.aof"
appendfsync always
save ""
auto-aof-rewrite-percentage 0
dir /tmp/ds614-exp1-always
```

Create `configs/exp1_everysec.conf`:
```conf
port 6399
daemonize no
appendonly yes
appendfilename "exp1_everysec.aof"
appendfsync everysec
save ""
auto-aof-rewrite-percentage 0
dir /tmp/ds614-exp1-everysec
```

Create `configs/exp1_no.conf`:
```conf
port 6399
daemonize no
appendonly yes
appendfilename "exp1_no.aof"
appendfsync no
save ""
auto-aof-rewrite-percentage 0
dir /tmp/ds614-exp1-no
```

### 5.2 Create the Experiment Script

Create `scripts/exp1_fsync_policy.py`:

```python
#!/usr/bin/env python3
"""
Experiment 1 — AOF fsync Policy Comparison
===========================================
Hypothesis: 'appendfsync always' is significantly slower than 'everysec' and 'no'
            because it calls fsync() after every single write command.

Baseline:   appendfsync everysec  (Redis default recommendation)
Variants:   appendfsync always, appendfsync no

Method:
  - Start Redis with each config
  - Write 5000 SET commands via pipeline
  - Measure total wall-clock time
  - Record AOF file size after writes
  - Compare throughput (ops/sec)

Code References:
  - src/aof.c: flushAppendOnlyFile() — line ~1000 in Redis 7.x
    The 'force' flag triggers fsync() immediately when appendfsync=always
  - src/server.h: AOF_FSYNC_ALWAYS, AOF_FSYNC_EVERYSEC, AOF_FSYNC_NO constants
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from helpers import (start_redis, stop_redis, get_redis_client,
                     write_n_keys, get_aof_size_bytes, save_result)
import time

EXPERIMENTS = [
    {
        "label": "always",
        "config": "configs/exp1_always.conf",
        "workdir": "/tmp/ds614-exp1-always",
        "aof_file": "exp1_always.aof",
        "port": 6399,
    },
    {
        "label": "everysec",
        "config": "configs/exp1_everysec.conf",
        "workdir": "/tmp/ds614-exp1-everysec",
        "aof_file": "exp1_everysec.aof",
        "port": 6399,
    },
    {
        "label": "no",
        "config": "configs/exp1_no.conf",
        "workdir": "/tmp/ds614-exp1-no",
        "aof_file": "exp1_no.aof",
        "port": 6399,
    },
]

N_WRITES = 5000

def run():
    print("=" * 60)
    print("EXPERIMENT 1: AOF fsync Policy Comparison")
    print(f"Writes per run: {N_WRITES}")
    print("=" * 60)

    for exp in EXPERIMENTS:
        print(f"\n--- Running: appendfsync={exp['label']} ---")
        proc = start_redis(exp["config"], exp["workdir"])
        time.sleep(0.5)

        r = get_redis_client(exp["port"])
        r.flushall()

        elapsed = write_n_keys(r, N_WRITES)
        aof_size = get_aof_size_bytes(exp["workdir"], exp["aof_file"])
        ops_per_sec = round(N_WRITES / elapsed, 2)

        print(f"  Time      : {elapsed:.3f} s")
        print(f"  Throughput: {ops_per_sec} ops/sec")
        print(f"  AOF size  : {aof_size} bytes")

        save_result("exp1", exp["label"], {
            "n_writes": N_WRITES,
            "elapsed_sec": round(elapsed, 4),
            "ops_per_sec": ops_per_sec,
            "aof_size_bytes": aof_size,
        })

        stop_redis(proc, exp["port"])
        time.sleep(1)

    print("\n[DONE] Results saved to results/exp1/results.tsv")

if __name__ == "__main__":
    run()
```

### 5.3 Run Experiment 1

```bash
cd ~/ds614-redis-aof
python3 scripts/exp1_fsync_policy.py
cat results/exp1/results.tsv
```

### 5.4 What to Observe and Record
- `always` should be **3–10x slower** than `everysec` due to per-write fsync syscall overhead.
- `no` should be fastest since the OS buffers writes.
- AOF file sizes should be nearly identical (same commands written regardless of fsync mode).
- **Record actual numbers** in the final README as a table.

---

## 6. Experiment 2 — AOF Rewrite Threshold Behavior

### What We Are Testing
AOF files grow forever as new commands are appended. Redis compacts the file via **AOF Rewrite** (`BGREWRITEAOF`):  
- It forks a child process  
- The child writes a **minimal equivalent** of current dataset  
- The parent keeps serving writes  
- On completion, the compact file replaces the old AOF  

**Code reference:**  
- `src/aof.c` → `rewriteAppendOnlyFileBackground()` — triggers the fork  
- `src/aof.c` → `rewriteAppendOnlyFile()` — the child's write loop  
- `src/server.h` → `aof_rewrite_perc`, `aof_rewrite_min_size`  

**Config trigger:** `auto-aof-rewrite-percentage 100` means: rewrite when AOF is 100% larger than after the last rewrite.

### 6.1 Create Config

Create `configs/exp2_rewrite.conf`:
```conf
port 6399
daemonize no
appendonly yes
appendfilename "exp2.aof"
appendfsync everysec
save ""

# Aggressive rewrite threshold so we can observe it quickly
auto-aof-rewrite-percentage 50
auto-aof-rewrite-min-size 1mb

dir /tmp/ds614-exp2
```

### 6.2 Create the Experiment Script

Create `scripts/exp2_rewrite.py`:

```python
#!/usr/bin/env python3
"""
Experiment 2 — AOF Rewrite Threshold Behavior
==============================================
Hypothesis: AOF file size grows linearly with writes, then drops sharply
            when a BGREWRITEAOF completes. The compacted file is much smaller
            because it stores only current key-value state, not full history.

Method:
  - Write 1000 keys
  - Then overwrite the SAME 1000 keys 5 times (simulating updates)
  - Without rewrite: AOF = 6x the data (1 create + 5 updates per key)
  - Trigger BGREWRITEAOF manually
  - Measure size before vs after rewrite

Code References:
  - src/aof.c: rewriteAppendOnlyFileBackground()
    Forks a child; child calls rewriteAppendOnlyFile()
  - src/aof.c: aofRewriteBufferAppend()
    Parent buffers new writes during rewrite, then appends to new file
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from helpers import start_redis, stop_redis, get_redis_client, save_result

CONFIG  = "configs/exp2_rewrite.conf"
WORKDIR = "/tmp/ds614-exp2"
AOF     = "exp2.aof"
PORT    = 6399
N_KEYS  = 1000
N_OVERWRITES = 5

def get_size():
    p = os.path.join(WORKDIR, AOF)
    return os.path.getsize(p) if os.path.exists(p) else 0

def run():
    print("=" * 60)
    print("EXPERIMENT 2: AOF Rewrite Threshold Behavior")
    print("=" * 60)

    proc = start_redis(CONFIG, WORKDIR)
    r = get_redis_client(PORT)
    r.flushall()

    # Step 1: Initial write of N_KEYS
    print(f"\nStep 1: Writing {N_KEYS} keys (initial)")
    pipe = r.pipeline(transaction=False)
    for i in range(N_KEYS):
        pipe.set(f"key:{i}", f"value-initial-{i}-{'x'*100}")
    pipe.execute()
    time.sleep(0.5)
    size_after_initial = get_size()
    print(f"  AOF size after initial writes: {size_after_initial:,} bytes")

    # Step 2: Overwrite same keys N_OVERWRITES times
    print(f"\nStep 2: Overwriting same {N_KEYS} keys {N_OVERWRITES} times")
    for pass_num in range(N_OVERWRITES):
        pipe = r.pipeline(transaction=False)
        for i in range(N_KEYS):
            pipe.set(f"key:{i}", f"value-overwrite-{pass_num}-{i}-{'y'*100}")
        pipe.execute()
    time.sleep(0.5)
    size_before_rewrite = get_size()
    print(f"  AOF size after {N_OVERWRITES} overwrites: {size_before_rewrite:,} bytes")
    print(f"  Growth factor vs initial: {size_before_rewrite/max(size_after_initial,1):.2f}x")

    # Step 3: Trigger rewrite and wait
    print("\nStep 3: Triggering BGREWRITEAOF ...")
    r.bgrewriteaof()
    # Wait for rewrite to complete (poll INFO persistence)
    for attempt in range(30):
        info = r.info("persistence")
        if info.get("aof_rewrite_in_progress") == 0:
            break
        time.sleep(0.5)
    time.sleep(1.0)
    size_after_rewrite = get_size()
    print(f"  AOF size after rewrite: {size_after_rewrite:,} bytes")
    compression_ratio = round(size_before_rewrite / max(size_after_rewrite, 1), 2)
    print(f"  Compression ratio: {compression_ratio}x")

    save_result("exp2", "rewrite_experiment", {
        "n_keys": N_KEYS,
        "n_overwrites": N_OVERWRITES,
        "size_after_initial_bytes": size_after_initial,
        "size_before_rewrite_bytes": size_before_rewrite,
        "size_after_rewrite_bytes": size_after_rewrite,
        "compression_ratio": compression_ratio,
    })

    stop_redis(proc, PORT)
    print("\n[DONE] Results saved to results/exp2/results.tsv")

if __name__ == "__main__":
    run()
```

### 6.3 Run Experiment 2

```bash
cd ~/ds614-redis-aof
python3 scripts/exp2_rewrite.py
cat results/exp2/results.tsv
```

### 6.4 What to Observe and Record
- AOF grows linearly through overwrites (every command is appended — even for the same key).
- After `BGREWRITEAOF`, the file should shrink dramatically — only one SET per key survives.
- Record: initial size, pre-rewrite size, post-rewrite size, compression ratio.

---

## 7. Experiment 3 — AOF Recovery After Simulated Crash

### What We Are Testing
The entire point of AOF is recovery. This experiment:
1. Writes known data
2. **Kills Redis with SIGKILL** (simulates a hard crash — no clean shutdown)
3. Restarts Redis with the same AOF file
4. Verifies all data is intact

**Code reference:**  
- `src/aof.c` → `loadAppendOnlyFile()` — called at startup to replay AOF  
- Each command in the AOF is parsed and re-executed via `src/server.c` → `processCommand()`  
- `src/aof.c` → `aofCheckAndFixIfNeeded()` — checks for truncated AOF (crash mid-write) and truncates to last valid command

### 7.1 Create Config

Create `configs/exp3_crash.conf`:
```conf
port 6399
daemonize no
appendonly yes
appendfilename "exp3.aof"
appendfsync everysec
save ""
auto-aof-rewrite-percentage 0
dir /tmp/ds614-exp3
```

### 7.2 Create the Experiment Script

Create `scripts/exp3_crash_recovery.py`:

```python
#!/usr/bin/env python3
"""
Experiment 3 — AOF Recovery After Simulated Crash
==================================================
Hypothesis: After a SIGKILL (hard crash), Redis can fully recover all
            data that was fsynced to the AOF file. Data written in the
            last ~1 second (buffered, not yet fsynced) may be lost
            when using appendfsync=everysec.

Method:
  - Write 2000 known keys with known values
  - Wait 2 seconds (ensure fsync has happened)
  - SIGKILL the Redis process (hard crash)
  - Restart Redis with the same AOF file
  - Verify every key exists and has the correct value
  - Report: keys recovered, keys lost, recovery rate %

Code References:
  - src/aof.c: loadAppendOnlyFile() — replays every command from the AOF
  - src/aof.c: aofCheckAndFixIfNeeded() — handles truncation at crash boundary
"""

import sys, os, time, signal
sys.path.insert(0, os.path.dirname(__file__))
from helpers import start_redis, stop_redis, get_redis_client, kill_redis_hard, save_result

CONFIG  = "configs/exp3_crash.conf"
WORKDIR = "/tmp/ds614-exp3"
PORT    = 6399
N_KEYS  = 2000

def run():
    print("=" * 60)
    print("EXPERIMENT 3: AOF Recovery After Simulated Crash")
    print("=" * 60)

    # --- Phase 1: Write data ---
    print(f"\nPhase 1: Starting Redis and writing {N_KEYS} keys ...")
    proc = start_redis(CONFIG, WORKDIR)
    r = get_redis_client(PORT)
    r.flushall()

    expected = {}
    pipe = r.pipeline(transaction=False)
    for i in range(N_KEYS):
        val = f"verified-value-{i}"
        expected[f"crash:key:{i}"] = val
        pipe.set(f"crash:key:{i}", val)
        if i % 500 == 0:
            pipe.execute()
    pipe.execute()
    print(f"  Written {N_KEYS} keys.")

    # --- Phase 2: Wait for fsync then hard kill ---
    print("\nPhase 2: Waiting 2.5s for fsync, then SIGKILL ...")
    time.sleep(2.5)
    kill_redis_hard(proc)
    time.sleep(1.0)
    print("  Redis killed (SIGKILL).")

    # --- Phase 3: Restart and verify ---
    print("\nPhase 3: Restarting Redis (AOF replay) ...")
    proc2 = start_redis(CONFIG, WORKDIR)
    time.sleep(2.0)   # AOF replay takes time proportional to file size
    r2 = get_redis_client(PORT)

    recovered = 0
    lost = 0
    wrong_value = 0

    for key, expected_val in expected.items():
        actual = r2.get(key)
        if actual is None:
            lost += 1
        elif actual != expected_val:
            wrong_value += 1
        else:
            recovered += 1

    recovery_rate = round(recovered / N_KEYS * 100, 2)
    print(f"\n  Keys written   : {N_KEYS}")
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

    stop_redis(proc2, PORT)
    print("\n[DONE] Results saved to results/exp3/results.tsv")

if __name__ == "__main__":
    run()
```

### 7.3 Run Experiment 3

```bash
cd ~/ds614-redis-aof
python3 scripts/exp3_crash_recovery.py
cat results/exp3/results.tsv
```

### 7.4 What to Observe and Record
- With `appendfsync everysec` and a 2.5s wait, almost all (ideally 100%) of keys should recover.
- If kill happens immediately after write, you may see some loss — that's the fsync window.
- Record: recovery rate, any lost keys.

---

## 8. Experiment 4 — AOF vs RDB Write Throughput

### What We Are Testing
Redis has two persistence modes:
- **AOF:** Appends every command → better durability, more disk writes
- **RDB:** Periodic point-in-time snapshots → better performance, lower durability

This experiment runs the **same workload** against both modes and compares throughput.

**Code reference:**  
- `src/aof.c` → `feedAppendOnlyFile()` — called on every write when AOF is enabled  
- `src/rdb.c` → `rdbSaveBackground()` — spawns a child for snapshot  
- `src/server.c` → `call()` — after executing a command, calls `propagate()` which routes to AOF  

### 8.1 Create Configs

Create `configs/exp4_rdb.conf`:
```conf
port 6399
daemonize no
appendonly no

# RDB snapshot every 60 seconds (or 1000 keys changed)
save 60 1000

rdbfilename "exp4.rdb"
dir /tmp/ds614-exp4-rdb
```

Create a copy for AOF mode in `configs/exp1_everysec.conf` (already created) or create `configs/exp4_aof.conf`:
```conf
port 6399
daemonize no
appendonly yes
appendfilename "exp4.aof"
appendfsync everysec
save ""
auto-aof-rewrite-percentage 0
dir /tmp/ds614-exp4-aof
```

### 8.2 Create the Experiment Script

Create `scripts/exp4_aof_vs_rdb.py`:

```python
#!/usr/bin/env python3
"""
Experiment 4 — AOF vs RDB Write Throughput
===========================================
Hypothesis: RDB mode has higher write throughput than AOF (everysec)
            because it does not write to disk on the critical path.
            AOF incurs overhead on every write due to feedAppendOnlyFile().

Method:
  - Run 3 batch sizes: 1000, 5000, 10000 writes
  - Each batch run under AOF (everysec) and RDB (snapshot) mode
  - Measure wall-clock time per batch
  - Compare ops/sec

Code References:
  - src/server.c: call() → propagate() → feedAppendOnlyFile()
    Every SET/DEL/etc goes through propagate() which writes to AOF buffer
  - src/aof.c: flushAppendOnlyFile() — called from serverCron() every 1s
    (for everysec mode) to actually fsync
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from helpers import start_redis, stop_redis, get_redis_client, write_n_keys, save_result

MODES = [
    {
        "label": "AOF_everysec",
        "config": "configs/exp4_aof.conf",
        "workdir": "/tmp/ds614-exp4-aof",
        "port": 6399,
    },
    {
        "label": "RDB_snapshot",
        "config": "configs/exp4_rdb.conf",
        "workdir": "/tmp/ds614-exp4-rdb",
        "port": 6399,
    },
]

BATCH_SIZES = [1000, 5000, 10000]

def run():
    print("=" * 60)
    print("EXPERIMENT 4: AOF vs RDB Write Throughput")
    print("=" * 60)

    for mode in MODES:
        print(f"\n--- Mode: {mode['label']} ---")
        proc = start_redis(mode["config"], mode["workdir"])
        r = get_redis_client(mode["port"])

        for n in BATCH_SIZES:
            r.flushall()
            elapsed = write_n_keys(r, n)
            ops_per_sec = round(n / elapsed, 2)
            print(f"  n={n:>6} | {elapsed:.3f}s | {ops_per_sec} ops/sec")
            save_result("exp4", mode["label"], {
                "n_writes": n,
                "elapsed_sec": round(elapsed, 4),
                "ops_per_sec": ops_per_sec,
            })

        stop_redis(proc, mode["port"])
        time.sleep(1)

    print("\n[DONE] Results saved to results/exp4/results.tsv")

if __name__ == "__main__":
    run()
```

### 8.3 Run Experiment 4

```bash
cd ~/ds614-redis-aof
python3 scripts/exp4_aof_vs_rdb.py
cat results/exp4/results.tsv
```

### 8.4 What to Observe and Record
- RDB should be faster at all batch sizes.
- The throughput gap should be visible but not extreme with `everysec` (because fsync is async).
- At `appendfsync always`, the gap would be massive.
- Record the actual ops/sec numbers.

---

## 9. Experiment 5 — AOF Under Write Skew (Hot Key)

### What We Are Testing
**Write skew** = one key receives a disproportionate share of writes (hot key problem).  
In AOF, every write appends a line. A hot key = the same key name appearing thousands of times in the AOF → AOF file is large, rewrite helps little (only 1 key survives regardless).

This experiment also tests the interaction between **hot key writes** and AOF rewrite compression.

**Code reference:**  
- `src/aof.c` → `feedAppendOnlyFile()` — no special handling for hot keys; every write gets appended equally  
- `src/aof.c` → `rewriteAppendOnlyFileBackground()` — hot key becomes a SINGLE SET in the rewritten file regardless of how many times it was updated

### 9.1 Create Config

Create `configs/exp5_skew.conf`:
```conf
port 6399
daemonize no
appendonly yes
appendfilename "exp5.aof"
appendfsync everysec
save ""
auto-aof-rewrite-percentage 0
dir /tmp/ds614-exp5
```

### 9.2 Create the Experiment Script

Create `scripts/exp5_hot_key_skew.py`:

```python
#!/usr/bin/env python3
"""
Experiment 5 — AOF Under Write Skew (Hot Key)
==============================================
Hypothesis 1: A hot-key workload (all writes to 1 key) produces an AOF
              file nearly as large as a uniform workload (N different keys)
              because AOF appends every command regardless.

Hypothesis 2: After BGREWRITEAOF, the hot-key AOF compresses to almost
              nothing (1 key's final state), while the uniform AOF
              compresses to N keys' state.

Method:
  - Uniform workload: write 5000 writes to 5000 different keys
  - Skewed workload: write 5000 writes to the SAME 1 key (hot key)
  - Measure AOF size before and after rewrite for each
  - Compare compression ratio

Code References:
  - src/aof.c: feedAppendOnlyFile()
    Every SET is appended regardless of whether key is the same or different
  - src/aof.c: rewriteAppendOnlyFile()
    Iterates over the current keyspace (dictScan) — hot key = 1 entry
"""

import sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from helpers import start_redis, stop_redis, get_redis_client, save_result

CONFIG  = "configs/exp5_skew.conf"
WORKDIR = "/tmp/ds614-exp5"
AOF     = "exp5.aof"
PORT    = 6399
N       = 5000

def get_size():
    p = os.path.join(WORKDIR, AOF)
    return os.path.getsize(p) if os.path.exists(p) else 0

def run():
    print("=" * 60)
    print("EXPERIMENT 5: AOF Under Write Skew (Hot Key)")
    print("=" * 60)

    for label, hot in [("uniform", False), ("hot_key", True)]:
        print(f"\n--- Workload: {label} ---")
        proc = start_redis(CONFIG, WORKDIR)
        r = get_redis_client(PORT)
        r.flushall()
        time.sleep(0.5)

        # Write N commands
        pipe = r.pipeline(transaction=False)
        for i in range(N):
            key = "hotkey:ONE" if hot else f"uniform:key:{i}"
            pipe.set(key, f"value-{i}-{'z'*80}")
            if i % 500 == 0:
                pipe.execute()
        pipe.execute()
        time.sleep(0.5)

        size_before = get_size()
        print(f"  AOF size before rewrite: {size_before:,} bytes")

        # Trigger rewrite
        r.bgrewriteaof()
        for _ in range(30):
            info = r.info("persistence")
            if info.get("aof_rewrite_in_progress") == 0:
                break
            time.sleep(0.5)
        time.sleep(1.0)

        size_after = get_size()
        ratio = round(size_before / max(size_after, 1), 2)
        print(f"  AOF size after  rewrite: {size_after:,} bytes")
        print(f"  Compression ratio       : {ratio}x")

        save_result("exp5", label, {
            "n_writes": N,
            "is_hot_key": hot,
            "size_before_bytes": size_before,
            "size_after_bytes": size_after,
            "compression_ratio": ratio,
        })

        stop_redis(proc, PORT)
        time.sleep(1)

    print("\n[DONE] Results saved to results/exp5/results.tsv")

if __name__ == "__main__":
    run()
```

### 9.3 Run Experiment 5

```bash
cd ~/ds614-redis-aof
python3 scripts/exp5_hot_key_skew.py
cat results/exp5/results.tsv
```

### 9.4 What to Observe and Record
- Both uniform and hot-key AOFs should be **similar in size before rewrite** (same number of commands appended).
- **After rewrite:** hot-key AOF should be **tiny** (1 key), uniform AOF stays large (5000 keys).
- This illustrates how AOF is blind to skew during writes, but rewrite is extremely effective for hot keys.

---

## 10. Final Report Generation

### Instructions for the Agent
After **all 5 experiments have been run** and all `results/expN/results.tsv` files exist, the agent must:

1. Read every TSV file from `results/`
2. Generate the final `README.md` in the project root

The README must follow **exactly** this structure:

---

### README.md Template (Agent must fill in real numbers from TSV files)

```markdown
# DS614 Final Project — Redis AOF Persistence
**Topic:** Redis Append-Only File (AOF) Persistence  
**System:** Redis 7.x (open source, https://github.com/redis/redis)  
**Team:** [Your Name(s)]

---

## 1. What Problem Does This System Solve?

Redis is an in-memory key-value store. Without persistence, all data is lost when the process terminates. The **Append-Only File (AOF)** mechanism solves the durability problem by writing every write command to a sequential log on disk. On restart, Redis replays this log to reconstruct exact in-memory state.

**Entry point in code:** `src/aof.c` → `feedAppendOnlyFile()`  
Called from `src/server.c` → `propagate()` after every successful write command.

---

## 2. Execution Path Trace: Write Path

```
Client sends: SET foo bar
       ↓
src/server.c: processCommand()         ← parses and validates command
       ↓
src/server.c: call()                   ← executes the command
       ↓
src/server.c: propagate()              ← decides what to persist
       ↓
src/aof.c: feedAppendOnlyFile()        ← formats command as RESP protocol
                                          appends to server.aof_buf (memory buffer)
       ↓
src/aof.c: flushAppendOnlyFile()       ← called from serverCron() (event loop)
           ├── write() syscall         ← writes buffer to kernel buffer
           └── fsync() (conditional)  ← flushes kernel buffer to disk
                                          controlled by appendfsync config
```

AOF format example (what lands in the file):
```
*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n
```

---

## 3. Design Decisions

### Decision 1: Three-Level fsync Control (`appendfsync`)

| Setting | Code Location | Behavior | Trade-off |
|---|---|---|---|
| `always` | `aof.c:flushAppendOnlyFile()` — `force=1` | fsync after every write | Zero data loss vs very low throughput |
| `everysec` | Same function — background thread fsync | fsync every 1 second | At most 1s data loss; balanced |
| `no` | Same function — skip fsync | OS decides | Highest throughput; durability depends on OS |

**Problem solved:** Lets operators tune the durability-performance tradeoff for their workload.  
**Tradeoff:** `always` can reduce throughput by 3–10x (see Experiment 1 results).

### Decision 2: AOF Rewrite via Fork

**Code:** `src/aof.c` → `rewriteAppendOnlyFileBackground()` uses `fork()`.  
**Problem solved:** AOF files grow unboundedly. Rewrite compacts to minimal equivalent state.  
**Tradeoff:** Fork creates a full copy-on-write clone of memory. On large datasets, this can cause memory spikes (Linux COW pages). The parent keeps serving writes into an `aof_rewrite_buf`, appended to the new file on completion.

### Decision 3: RESP Protocol in AOF (Not Binary)

**Code:** `src/aof.c` → `catAppendOnlyGenericCommand()` — formats using RESP text protocol.  
**Problem solved:** Human-readable log; `redis-check-aof` tool can scan and truncate corrupted AOF.  
**Tradeoff:** Text encoding is larger than binary. A SET command with a 10-byte key and value takes ~40 bytes in AOF vs ~20 bytes in binary.

---

## 4. Concept Mapping

| DS614 Concept | Redis AOF Implementation |
|---|---|
| **Write-Ahead Log (WAL)** | AOF is a WAL: every mutation is logged before being considered committed |
| **Log-Structured Storage (LSM-like)** | AOF appends sequentially like an LSM memtable WAL; compaction via BGREWRITEAOF mirrors LSM compaction |
| **Fault Tolerance / Crash Recovery** | `loadAppendOnlyFile()` replays log; `aofCheckAndFixIfNeeded()` handles truncated tail |
| **Partitioning / Replication** | In Redis Cluster, each shard maintains its own AOF; replicas replicate via command replication, not AOF shipping |
| **Streaming / Ingestion** | AOF is a continuous append stream; reads from it are sequential (replay mode only) |
| **Storage — Sequential vs Random I/O** | AOF is sequential write (fast); RDB is a full-dataset snapshot (random read, sequential write) |

---

## 5. Experiments and Results

### Baseline

**Config:** `appendfsync everysec`, AOF enabled, RDB disabled  
**Workload:** 5000 SET operations via pipeline  
**Purpose:** Establish baseline throughput and AOF file growth under normal conditions.

---

### Experiment 1 — AOF fsync Policy Comparison

**Hypothesis:** `appendfsync always` will be significantly slower than `everysec` due to per-write fsync syscall overhead.

**Code reference:** `src/aof.c:flushAppendOnlyFile()` — the `force` flag on line ~1080 determines whether `redis_fsync()` is called immediately.

**Results:**

| fsync Mode | Time (s) | Throughput (ops/sec) | AOF Size (bytes) |
|---|---|---|---|
| always | [FILL FROM results/exp1/results.tsv] | [FILL] | [FILL] |
| everysec (baseline) | [FILL] | [FILL] | [FILL] |
| no | [FILL] | [FILL] | [FILL] |

**Observation:** [Agent: describe what the numbers show. Was always significantly slower? By how much?]

**Explanation:** With `appendfsync always`, `flushAppendOnlyFile(force=1)` is called for every command, issuing a `fsync()` syscall which flushes the OS write buffer to disk. This is a blocking I/O operation. With `everysec`, fsync is called at most once per second in the background timer, decoupled from the write path.

---

### Experiment 2 — AOF Rewrite Threshold Behavior

**Hypothesis:** After multiple overwrites of the same keys, AOF contains redundant history. BGREWRITEAOF will produce a file dramatically smaller than the pre-rewrite AOF.

**Code reference:** `src/aof.c:rewriteAppendOnlyFile()` iterates the keyspace via `dictScan`, writing only the current value of each key — not its history.

**Results:**

| Metric | Value |
|---|---|
| Keys written | 1000 |
| Overwrites | 5 |
| AOF size after initial write | [FILL] bytes |
| AOF size before rewrite | [FILL] bytes |
| AOF size after rewrite | [FILL] bytes |
| Compression ratio | [FILL]x |

**Observation:** [Agent: describe the compression ratio and what it means]

**Explanation:** Each overwrite appends a new SET command for the same key. After 5 overwrites, the AOF contains 6 copies of each key's command. Rewrite scans the live keyspace and emits exactly one SET per key, collapsing all history.

---

### Experiment 3 — AOF Recovery After Simulated Crash

**Hypothesis:** After SIGKILL (hard crash with no clean shutdown), Redis can recover data that was fsynced to the AOF. At most 1 second of writes (the fsync window) may be lost.

**Code reference:** `src/aof.c:loadAppendOnlyFile()` is called during startup (`src/server.c:initServer()`). It reads and re-executes every command in the AOF file.

**Results:**

| Metric | Value |
|---|---|
| Keys written before crash | 2000 |
| Keys recovered | [FILL] |
| Keys lost | [FILL] |
| Recovery rate | [FILL]% |

**Observation:** [Agent: was recovery complete? Any loss?]

**Explanation:** The 2.5 second wait before SIGKILL ensures at least 2 fsync cycles have completed (fsync interval = 1s). Any writes buffered in the sub-second window before the kill may be lost, but the `aofCheckAndFixIfNeeded()` function handles a truncated tail at the crash boundary by seeking to the last valid command boundary.

---

### Experiment 4 — AOF vs RDB Write Throughput

**Hypothesis:** RDB mode will have higher throughput than AOF at all batch sizes because it does not touch disk on the write path.

**Code reference:**  
- AOF path: `src/server.c:propagate()` → `feedAppendOnlyFile()` on every write  
- RDB path: writes go only to memory; `rdbSaveBackground()` is triggered separately by config timer

**Results:**

| Mode | n=1000 ops/sec | n=5000 ops/sec | n=10000 ops/sec |
|---|---|---|---|
| AOF (everysec) (baseline) | [FILL] | [FILL] | [FILL] |
| RDB snapshot | [FILL] | [FILL] | [FILL] |

**Observation:** [Agent: which was faster, by how much?]

**Explanation:** With AOF, every write appends to `server.aof_buf` and is flushed via `write()` syscall in the main event loop. While fsync is deferred (everysec), the `write()` itself still copies data from userspace to the kernel buffer on every event loop iteration. RDB mode skips this entirely during normal operation.

---

### Experiment 5 — AOF Under Write Skew (Hot Key)

**Hypothesis:**  
- Before rewrite: hot-key AOF ≈ uniform AOF (same number of commands appended)  
- After rewrite: hot-key AOF is tiny (1 key); uniform AOF stays large (5000 keys)

**Code reference:** `src/aof.c:feedAppendOnlyFile()` appends every SET regardless of key uniqueness. `src/aof.c:rewriteAppendOnlyFile()` iterates the live keyspace — hot-key workload has 1 live key.

**Results:**

| Workload | AOF Before Rewrite (bytes) | AOF After Rewrite (bytes) | Compression Ratio |
|---|---|---|---|
| Uniform (5000 keys) (baseline) | [FILL] | [FILL] | [FILL]x |
| Hot Key (1 key, 5000 writes) | [FILL] | [FILL] | [FILL]x |

**Observation:** [Agent: compare the compression ratios and discuss what this means for hot-key workloads]

**Explanation:** AOF has no concept of key cardinality — it is a pure command log. The hot-key scenario demonstrates that a skewed write pattern produces a large AOF that is almost entirely redundant history. After rewrite, the hot-key file collapses to near-zero because the keyspace contains only a single entry. This is analogous to LSM compaction collapsing tombstones.

---

## 6. Failure Analysis

### What happens when data size increases significantly?
- AOF file grows linearly with the number of unique keys × number of mutations.
- `BGREWRITEAOF` forks the process → at large data sizes (e.g., 10GB dataset), the fork can trigger significant Linux copy-on-write page faults if the parent is actively writing during the rewrite.
- Replay time on restart scales linearly with AOF file size — a 10GB AOF could take minutes to replay, increasing recovery time objective (RTO).

### What happens under skew?
- As shown in Experiment 5, AOF file grows based on write count, not key count.
- A single hot key with millions of updates produces a large AOF that compresses to almost nothing after rewrite.
- During the pre-rewrite window, this is a storage cost with no benefit.

### What happens if a component fails mid-rewrite?
- If Redis crashes during `BGREWRITEAOF`, the **old AOF file is still intact** — the new file is written to a temp file and renamed atomically only on completion (`rename()` syscall in `src/aof.c:renameTmpLog()`).
- If the AOF itself is truncated (crash mid-write), `aofCheckAndFixIfNeeded()` truncates to the last valid command boundary, preventing replay errors.

### What assumptions does this system rely on?
- The disk is **not full** (AOF write failure puts Redis in a read-only error state).
- The filesystem supports `fsync()` semantics (some network filesystems do not).
- The OS does not reorder writes between `write()` and `fsync()` — Linux ext4 with `data=ordered` provides this guarantee.

---

## 7. Key Insights

1. **AOF is a Write-Ahead Log** — the same fundamental primitive used in PostgreSQL (WAL), LevelDB (ChangeLog), and Kafka (log segments). The core insight — append mutations sequentially, replay to reconstruct state — is universal.

2. **The fsync tradeoff is real** — `appendfsync always` sacrifices orders-of-magnitude throughput for zero data loss. Most production systems use `everysec` and accept 1 second of potential loss.

3. **Rewrite is the AOF's garbage collector** — without it, AOF is a monotonically growing log. The fork-based rewrite is elegant but has memory pressure implications at scale.

4. **AOF + RDB together** — Redis best practice is to use both: RDB for fast restarts (binary snapshot, fast to load) and AOF for durability (command log, slow to replay). This mirrors the WAL + checkpoint pattern in databases.

5. **How I would improve it:** Implement incremental AOF rewrite (no fork required) using a background thread and log-structured merge similar to RocksDB's compaction, eliminating the memory spike from COW during fork on large datasets.

---

## 8. References

- Redis source: https://github.com/redis/redis (tag: 7.2.0)
- `src/aof.c` — All AOF logic
- `src/server.h` — `struct redisServer` persistence fields
- `src/rdb.c` — RDB snapshot logic (Experiment 4 comparison)
- Redis persistence documentation: https://redis.io/docs/management/persistence/
- Designing Data-Intensive Applications, Kleppmann — Chapter 3 (Log-Structured Storage), Chapter 7 (Durability)

---

*Generated by experiment pipeline. All numbers from live runs on college PC. See `results/` directory for raw TSV data.*
```

---

## 11. Presentation Slides Outline

The agent does **not** generate slides automatically, but must create `slides_outline.md`:

```markdown
# Presentation Outline — Redis AOF Persistence

## Slide Deck Structure (35 minutes total)

### Section 1: System Overview (10 min) — Slides 1-6
1. Title + team
2. What is Redis? (in-memory, key-value, no disk = data loss)
3. AOF in one sentence: "Every write command is appended to a file on disk"
4. The Write Path (show the trace: processCommand → propagate → feedAppendOnlyFile → flushAppendOnlyFile)
5. The Recovery Path (loadAppendOnlyFile replays every command on startup)
6. Three Design Decisions (fsync policy / rewrite-via-fork / RESP text format)

### Section 2: Deep Dive — AOF fsync (10 min) — Slides 7-12
7. The fsync problem: write() vs fsync() — explain OS kernel buffer
8. Three modes: always / everysec / no — show code from flushAppendOnlyFile()
9. Experiment 1 results: throughput table + bar chart
10. Why always is so slow: per-call fsync() is a blocking I/O barrier
11. Production recommendation: everysec + replica for safety
12. Concept link: WAL durability guarantees (ACID D)

### Section 3: Experiments / Demo (10 min) — Slides 13-18
13. Experiment 2: AOF rewrite — show before/after sizes (the "garbage collection" analogy)
14. Experiment 3: Crash recovery — show 100% recovery after SIGKILL
15. Experiment 4: AOF vs RDB throughput — show ops/sec comparison
16. Experiment 5: Hot key skew — show that skew blows up AOF but rewrite fixes it
17. Combined insights table (all 5 experiments in one view)
18. What breaks under real-world conditions (failure analysis)

### Section 4: Key Insights (5 min) — Slides 19-20
19. 5 key takeaways (AOF is WAL, fsync tradeoff, rewrite = GC, AOF+RDB together, how to improve)
20. Q&A prompt: "Why not always use appendfsync=always?"
```

---

## 12. Penalization Checklist

Before submitting, the agent must verify every item:

- [ ] Every claim in the README references a specific file + function in Redis source (`src/aof.c:functionName()`)
- [ ] All 5 experiments have been run and results TSV files exist in `results/`
- [ ] README contains real numbers (not `[FILL]` placeholders) — agent must substitute actual values from TSV files
- [ ] No documentation copy-paste — all descriptions are original analysis
- [ ] Experiment 3 (crash recovery) was actually run, not simulated
- [ ] Concept mapping covers at least 4 DS614 concepts (WAL, LSM, fault tolerance, partitioning)
- [ ] Failure analysis answers at least 2 questions
- [ ] Presentation outline exists in `slides_outline.md`
- [ ] All files committed to git:

```bash
cd ~/ds614-redis-aof
git add -A
git commit -m "DS614 Final Project: Redis AOF Persistence - all experiments complete"
```

---

## Agent: Final Step — Generate README.md

After all experiments run, execute this to auto-fill the README:

```bash
cd ~/ds614-redis-aof
python3 scripts/generate_readme.py
```

The agent must create `scripts/generate_readme.py` that:
1. Reads all TSV files from `results/`
2. Parses the numbers
3. Fills in the README template above with real values
4. Writes the completed `README.md` to the project root
5. Prints a summary table to terminal

```python
#!/usr/bin/env python3
"""
generate_readme.py
Reads all experiment TSV results and generates the final README.md
"""
import os, csv

def read_tsv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        reader = csv.DictReader(f, delimiter='\t')
        return list(reader)

def main():
    results = {
        "exp1": read_tsv("results/exp1/results.tsv"),
        "exp2": read_tsv("results/exp2/results.tsv"),
        "exp3": read_tsv("results/exp3/results.tsv"),
        "exp4": read_tsv("results/exp4/results.tsv"),
        "exp5": read_tsv("results/exp5/results.tsv"),
    }

    print("\n=== EXPERIMENT RESULTS SUMMARY ===\n")
    for exp, rows in results.items():
        print(f"--- {exp.upper()} ---")
        for row in rows:
            print("  " + " | ".join(f"{k}={v}" for k,v in row.items()))
        print()

    # Agent must use these values to fill the README template
    # and write the completed README.md file
    print("[INFO] Use the above values to fill in README.md template.")
    print("[INFO] Replace all [FILL] placeholders with actual numbers.")
    print("[INFO] Save final README.md to project root.")

if __name__ == "__main__":
    main()
```

---

*End of Agent Instructions. The agent must execute all steps in order, run all 5 experiments, collect real numbers, and produce a completed README.md with no placeholder values remaining.*
