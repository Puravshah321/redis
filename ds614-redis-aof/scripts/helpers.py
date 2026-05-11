#!/usr/bin/env python3
"""Shared utilities for DS614 Redis AOF experiments."""

import os
import shutil
import signal
import subprocess
import time


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REDIS_BIN = os.environ.get(
    "REDIS_BIN",
    os.path.abspath(os.path.join(PROJECT_ROOT, "..", "redis", "src", "redis-server")),
)
REDIS_CLI = os.environ.get(
    "REDIS_CLI",
    os.path.abspath(os.path.join(PROJECT_ROOT, "..", "redis", "src", "redis-cli")),
)


def clean_working_dir(working_dir):
    """Remove stale persistence files from one experiment work directory."""
    if os.path.exists(working_dir):
        shutil.rmtree(working_dir)
    os.makedirs(working_dir, exist_ok=True)


def cli(port=6399, *args, check=True):
    """Run redis-cli and return stdout."""
    result = subprocess.run(
        [REDIS_CLI, "-p", str(port), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"redis-cli {' '.join(map(str, args))} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def pipe_commands(commands, port=6399):
    """Send inline Redis commands through redis-cli --pipe."""
    payload = "".join(commands)
    result = subprocess.run(
        [REDIS_CLI, "-p", str(port), "--pipe"],
        input=payload,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0 or "errors: 0" not in result.stdout:
        raise RuntimeError(
            f"redis-cli --pipe failed:\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result.stdout


def start_redis(config_path, working_dir, clean=False, port=6399):
    """Start Redis with the given config. Returns the Popen process."""
    if clean:
        clean_working_dir(working_dir)
    else:
        os.makedirs(working_dir, exist_ok=True)

    cli(port, "shutdown", "nosave", check=False)
    time.sleep(0.2)

    proc = subprocess.Popen(
        [REDIS_BIN, config_path],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    deadline = time.time() + 8
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=1)
            raise RuntimeError(
                f"redis-server exited early for {config_path}\n{stdout}\n{stderr}"
            )
        try:
            if cli(port, "ping") == "PONG":
                return proc
        except Exception:
            time.sleep(0.1)
    raise TimeoutError(f"Redis did not start on port {port}")


def stop_redis(proc, port=6399):
    """Gracefully shut down Redis."""
    try:
        cli(port, "shutdown", "nosave", check=False)
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


def kill_redis_hard(proc):
    """Simulate a crash with SIGKILL."""
    try:
        os.kill(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)
    except ProcessLookupError:
        pass


def flush_and_prepare(port=6399):
    cli(port, "flushall")


def write_n_keys(n, prefix="key", port=6399, value_char="x"):
    """Write n string keys and return elapsed time in seconds."""
    start = time.time()
    commands = []
    for i in range(n):
        commands.append(f"SET {prefix}:{i} value-{i}-{value_char * 50}\n")
    pipe_commands(commands, port)
    return time.time() - start


def set_many(items, port=6399):
    commands = [f"SET {key} {value}\n" for key, value in items]
    pipe_commands(commands, port)


def get_aof_size_bytes(working_dir, aof_filename=None):
    """Return logical AOF size, including Redis multi-part AOF files."""
    direct = os.path.join(working_dir, aof_filename or "")
    if aof_filename and os.path.exists(direct):
        return os.path.getsize(direct)

    total = 0
    for root, _, files in os.walk(working_dir):
        for name in files:
            if name.endswith(".aof") or ".aof." in name:
                total += os.path.getsize(os.path.join(root, name))
    return total


def wait_for_aof_rewrite(port=6399, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = cli(port, "info", "persistence")
        values = {}
        for line in info.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                values[key] = value.strip()
        if values.get("aof_rewrite_in_progress") == "0":
            return
        time.sleep(0.5)
    raise TimeoutError("Timed out waiting for BGREWRITEAOF")


def save_result(exp_name, label, data):
    """Append a result row to results/<exp_name>/results.tsv."""
    os.makedirs(os.path.join(PROJECT_ROOT, "results", exp_name), exist_ok=True)
    filepath = os.path.join(PROJECT_ROOT, "results", exp_name, "results.tsv")
    write_header = not os.path.exists(filepath)
    with open(filepath, "a", encoding="utf-8") as f:
        if write_header:
            f.write("\t".join(["label"] + list(data.keys())) + "\n")
        f.write("\t".join([label] + [str(v) for v in data.values()]) + "\n")
    print(f"[SAVED] {exp_name}/{label}: {data}")
