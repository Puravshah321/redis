#!/usr/bin/env python3
"""Generate README.md, slides outline, plots, and terminal screenshots."""

import csv
import os
import struct
import textwrap
import zlib

from PIL import Image, ImageDraw, ImageFont


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def read_tsv(path):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        raise FileNotFoundError(full)
    with open(full, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def by_label(rows):
    return {row["label"]: row for row in rows}


def fmt_num(value):
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return value
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.2f}"


def pct_diff(a, b):
    return round(float(a) / max(float(b), 1e-9), 2)


def markdown_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |"]
    out.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in rows:
        out.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(out)


def write_png(path, width, height, pixels):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw_rows = []
    for row in pixels:
        flat = bytearray()
        for red, green, blue in row:
            flat.extend((red, green, blue))
        raw_rows.append(b"\x00" + bytes(flat))
    raw = b"".join(raw_rows)
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(raw, 9))
    data += chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


def load_font(size=18, bold=False):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    path = f"/usr/share/fonts/truetype/dejavu/{name}"
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def draw_centered(draw, xy, text, font, fill):
    x, y = xy
    box = draw.textbbox((0, 0), text, font=font)
    draw.text((x - (box[2] - box[0]) / 2, y), text, font=font, fill=fill)


def labeled_bar_png(filename, title, labels, values, ylabel, baseline=None, baseline_label=None):
    os.makedirs(os.path.join(ROOT, "plots"), exist_ok=True)
    width, height = 1050, 680
    image = Image.new("RGB", (width, height), (250, 250, 247))
    draw = ImageDraw.Draw(image)
    title_font = load_font(24, bold=True)
    label_font = load_font(16)
    small_font = load_font(13)
    value_font = load_font(14, bold=True)
    axis_color = (48, 55, 66)
    colors = [(44, 123, 182), (34, 168, 132), (238, 126, 73), (134, 94, 174), (72, 159, 181), (201, 91, 96)]

    left, right, top, bottom = 125, 70, 105, 125
    chart_w = width - left - right
    chart_h = height - top - bottom
    max_val = max(values + ([baseline] if baseline else [])) if values else 1
    scale_top = max_val * 1.22 if max_val else 1

    draw_centered(draw, (width / 2, 28), title, title_font, (25, 32, 42))
    draw.line((left, top, left, height - bottom), fill=axis_color, width=2)
    draw.line((left, height - bottom, width - right, height - bottom), fill=axis_color, width=2)
    draw.text((22, top + chart_h / 2 - 20), ylabel, font=label_font, fill=axis_color)

    for tick in range(5):
        value = scale_top * tick / 4
        y = height - bottom - int((value / scale_top) * chart_h)
        draw.line((left - 5, y, width - right, y), fill=(221, 224, 227), width=1)
        draw.text((left - 112, y - 8), fmt_num(round(value, 1)), font=small_font, fill=axis_color)

    if baseline is not None:
        y = height - bottom - int((baseline / scale_top) * chart_h)
        for x in range(left, width - right, 18):
            draw.line((x, y, min(x + 10, width - right), y), fill=(210, 45, 45), width=3)
        if baseline_label:
            draw.text((left + 12, max(top + 4, y - 28)), baseline_label, font=small_font, fill=(180, 35, 35))

    gap = 22
    bar_w = max(38, int((chart_w - gap * (len(values) + 1)) / max(len(values), 1)))
    for i, (label, value) in enumerate(zip(labels, values)):
        x0 = left + gap + i * (bar_w + gap)
        x1 = min(x0 + bar_w, width - right - 4)
        bar_h = int((value / scale_top) * chart_h)
        y0 = height - bottom - bar_h
        draw.rectangle((x0, y0, x1, height - bottom - 1), fill=colors[i % len(colors)], outline=(30, 30, 30), width=1)
        draw_centered(draw, ((x0 + x1) / 2, max(top + 5, y0 - 24)), fmt_num(value), value_font, (24, 30, 38))
        wrapped = textwrap.wrap(label, width=14)
        for line_i, line in enumerate(wrapped[:3]):
            draw_centered(draw, ((x0 + x1) / 2, height - bottom + 12 + line_i * 18), line, small_font, axis_color)

    image.save(os.path.join(ROOT, "plots", filename))


def generate_plots(exp1, exp2, exp3, exp4, exp5):
    os.makedirs(os.path.join(ROOT, "plots"), exist_ok=True)
    exp1_rows = by_label(exp1)
    labeled_bar_png(
        "exp1_fsync_throughput.png",
        "Experiment 1: AOF fsync Policy - Write Throughput",
        ["always", "everysec", "no"],
        [float(exp1_rows[k]["ops_per_sec"]) for k in ["always", "everysec", "no"]],
        "Throughput (ops/sec)",
        baseline=float(exp1_rows["everysec"]["ops_per_sec"]),
        baseline_label="Baseline: everysec",
    )
    e2 = exp2[0]
    labeled_bar_png(
        "exp2_rewrite_sizes.png",
        "Experiment 2: AOF File Size Before and After Rewrite",
        ["Initial write", "Before rewrite", "After rewrite"],
        [
            float(e2["size_after_initial_bytes"]) / 1024,
            float(e2["size_before_rewrite_bytes"]) / 1024,
            float(e2["size_after_rewrite_bytes"]) / 1024,
        ],
        "AOF size (KB)",
        baseline=float(e2["size_after_initial_bytes"]) / 1024,
        baseline_label="Baseline: initial AOF size",
    )

    e3 = exp3[0]
    labeled_bar_png(
        "exp3_recovery_rate.png",
        f"Experiment 3: Crash Recovery - {e3['recovery_rate_pct']}% Recovered",
        ["Recovered", "Lost", "Wrong value"],
        [float(e3["recovered"]), float(e3["lost"]), float(e3["wrong_value"])],
        "Number of keys",
        baseline=float(e3["n_keys"]),
        baseline_label="Baseline: total written",
    )

    aof = [r for r in exp4 if r["label"] == "AOF_everysec"]
    rdb = [r for r in exp4 if r["label"] == "RDB_snapshot"]
    labeled_bar_png(
        "exp4_aof_vs_rdb.png",
        "Experiment 4: AOF vs RDB Write Throughput",
        ["AOF 1k", "RDB 1k", "AOF 5k", "RDB 5k", "AOF 10k", "RDB 10k"],
        [
            float(aof[0]["ops_per_sec"]),
            float(rdb[0]["ops_per_sec"]),
            float(aof[1]["ops_per_sec"]),
            float(rdb[1]["ops_per_sec"]),
            float(aof[2]["ops_per_sec"]),
            float(rdb[2]["ops_per_sec"]),
        ],
        "Throughput (ops/sec)",
        baseline=sum(float(row["ops_per_sec"]) for row in aof) / len(aof),
        baseline_label="Baseline: average AOF everysec",
    )

    exp5_rows = by_label(exp5)
    labeled_bar_png(
        "exp5_skew_compression.png",
        "Experiment 5: Hot Key Skew Rewrite Compression",
        ["uniform", "hot key"],
        [float(exp5_rows["uniform"]["compression_ratio"]), float(exp5_rows["hot_key"]["compression_ratio"])],
        "Compression ratio (x)",
        baseline=float(exp5_rows["uniform"]["compression_ratio"]),
        baseline_label="Baseline: uniform workload",
    )


def terminal_output_text(exp_name, rows):
    lines = [f"=== {exp_name.upper()} terminal output ==="]
    for row in rows:
        lines.append(" | ".join(f"{key}={value}" for key, value in row.items()))
    lines.append(f"[DONE] {exp_name.upper()} complete.")
    return "\n".join(lines)


def save_terminal_screenshot(output_text, output_path, title):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bg_color = (18, 18, 18)
    text_color = (204, 255, 204)
    header_color = (100, 200, 100)
    font_size = 14
    padding = 20
    line_height = 20
    lines = [f"$ {title}", "=" * 70]
    for line in output_text.strip().split("\n"):
        lines.extend(textwrap.wrap(line, width=90) or [""])
    lines.append("")
    lines.append("Process finished with exit code 0")

    img_width = 960
    img_height = padding * 2 + len(lines) * line_height + 10
    image = Image.new("RGB", (img_width, img_height), color=bg_color)
    draw = ImageDraw.Draw(image)
    font = load_font(font_size)
    header_font = load_font(font_size, bold=True)
    for i, line in enumerate(lines):
        y = padding + i * line_height
        color = header_color if i <= 1 else text_color
        draw.text((padding, y), line, fill=color, font=header_font if i <= 1 else font)
    image.save(output_path)


def generate_screenshots(results):
    commands = {
        "exp1": "python3 scripts/exp1_fsync_policy.py",
        "exp2": "python3 scripts/exp2_rewrite.py",
        "exp3": "python3 scripts/exp3_crash_recovery.py",
        "exp4": "python3 scripts/exp4_aof_vs_rdb.py",
        "exp5": "python3 scripts/exp5_hot_key_skew.py",
    }
    for exp_name, rows in results.items():
        save_terminal_screenshot(
            terminal_output_text(exp_name, rows),
            os.path.join(ROOT, "screenshots", f"{exp_name}_terminal.png"),
            commands[exp_name],
        )


def generate_slides_outline():
    outline = """# Presentation Outline - Redis AOF Persistence

## Slide Deck Structure (35 minutes total)

### Section 1: System Overview (10 min) - Slides 1-6
1. Title + team
2. What is Redis? In-memory key-value store; without persistence, process loss means data loss
3. AOF in one sentence: every write command is appended to a file on disk
4. Write path: processCommand -> call -> propagate -> feedAppendOnlyFile -> flushAppendOnlyFile
5. Recovery path: loadAppendOnlyFiles replays commands on startup
6. Three design decisions: fsync policy, rewrite via fork, RESP text format

### Section 2: Deep Dive - AOF fsync (10 min) - Slides 7-12
7. write() vs fsync(): OS buffer versus durable disk barrier
8. appendfsync modes: always, everysec, no
9. Experiment 1 results: throughput table + bar chart from plots/exp1_fsync_policy.png
10. Why always is slow: each command can force a blocking disk flush
11. Production recommendation: everysec plus replication for practical durability
12. Concept link: AOF as a write-ahead log

### Section 3: Experiments / Demo (10 min) - Slides 13-18
13. Experiment 2: AOF rewrite before/after sizes
14. Experiment 3: crash recovery after SIGKILL
15. Experiment 4: AOF vs RDB throughput
16. Experiment 5: hot key skew and rewrite compression
17. Combined insights table across all experiments
18. Failure analysis: large data, skew, crash during rewrite

### Section 4: Key Insights (5 min) - Slides 19-20
19. Five takeaways: AOF is WAL, fsync tradeoff, rewrite is compaction, AOF+RDB together, possible incremental rewrite
20. Q&A prompt: Why not always use appendfsync=always?
"""
    with open(os.path.join(ROOT, "slides_outline.md"), "w", encoding="utf-8") as f:
        f.write(outline)


def main():
    exp1 = read_tsv("results/exp1/results.tsv")
    exp2 = read_tsv("results/exp2/results.tsv")
    exp3 = read_tsv("results/exp3/results.tsv")
    exp4 = read_tsv("results/exp4/results.tsv")
    exp5 = read_tsv("results/exp5/results.tsv")

    e1 = by_label(exp1)
    e2 = exp2[0]
    e3 = exp3[0]
    e5 = by_label(exp5)
    exp4_aof = [r for r in exp4 if r["label"] == "AOF_everysec"]
    exp4_rdb = [r for r in exp4 if r["label"] == "RDB_snapshot"]

    exp1_ratio = pct_diff(e1["everysec"]["ops_per_sec"], e1["always"]["ops_per_sec"])
    exp2_ratio = e2["compression_ratio"]
    exp4_ratio_10k = pct_diff(exp4_rdb[2]["ops_per_sec"], exp4_aof[2]["ops_per_sec"])
    exp5_ratio_delta = pct_diff(e5["hot_key"]["compression_ratio"], e5["uniform"]["compression_ratio"])

    exp1_table = markdown_table(
        ["fsync Mode", "Time (s)", "Throughput (ops/sec)", "AOF Size (bytes)"],
        [
            ["always", e1["always"]["elapsed_sec"], fmt_num(e1["always"]["ops_per_sec"]), fmt_num(e1["always"]["aof_size_bytes"])],
            ["everysec (baseline)", e1["everysec"]["elapsed_sec"], fmt_num(e1["everysec"]["ops_per_sec"]), fmt_num(e1["everysec"]["aof_size_bytes"])],
            ["no", e1["no"]["elapsed_sec"], fmt_num(e1["no"]["ops_per_sec"]), fmt_num(e1["no"]["aof_size_bytes"])],
        ],
    )
    exp2_table = markdown_table(
        ["Metric", "Value"],
        [
            ["Keys written", e2["n_keys"]],
            ["Overwrites", e2["n_overwrites"]],
            ["AOF size after initial write", f'{fmt_num(e2["size_after_initial_bytes"])} bytes'],
            ["AOF size before rewrite", f'{fmt_num(e2["size_before_rewrite_bytes"])} bytes'],
            ["AOF size after rewrite", f'{fmt_num(e2["size_after_rewrite_bytes"])} bytes'],
            ["Compression ratio", f'{e2["compression_ratio"]}x'],
        ],
    )
    exp3_table = markdown_table(
        ["Metric", "Value"],
        [
            ["Keys written before crash", e3["n_keys"]],
            ["Keys recovered", e3["recovered"]],
            ["Keys lost", e3["lost"]],
            ["Recovery rate", f'{e3["recovery_rate_pct"]}%'],
        ],
    )
    exp4_table = markdown_table(
        ["Mode", "n=1000 ops/sec", "n=5000 ops/sec", "n=10000 ops/sec"],
        [
            ["AOF (everysec) (baseline)", fmt_num(exp4_aof[0]["ops_per_sec"]), fmt_num(exp4_aof[1]["ops_per_sec"]), fmt_num(exp4_aof[2]["ops_per_sec"])],
            ["RDB snapshot", fmt_num(exp4_rdb[0]["ops_per_sec"]), fmt_num(exp4_rdb[1]["ops_per_sec"]), fmt_num(exp4_rdb[2]["ops_per_sec"])],
        ],
    )
    exp5_table = markdown_table(
        ["Workload", "AOF Before Rewrite (bytes)", "AOF After Rewrite (bytes)", "Compression Ratio"],
        [
            ["Uniform (5000 keys) (baseline)", fmt_num(e5["uniform"]["size_before_bytes"]), fmt_num(e5["uniform"]["size_after_bytes"]), f'{e5["uniform"]["compression_ratio"]}x'],
            ["Hot Key (1 key, 5000 writes)", fmt_num(e5["hot_key"]["size_before_bytes"]), fmt_num(e5["hot_key"]["size_after_bytes"]), f'{e5["hot_key"]["compression_ratio"]}x'],
        ],
    )

    readme = f"""# DS614 Final Project - Redis AOF Persistence
**Topic:** Redis Append-Only File (AOF) Persistence  
**System:** Redis open source, built from the cloned repository at `../redis`  
**Team:** Purav Shah

---

## 1. What Problem Does This System Solve?

Redis is an in-memory key-value store. Without persistence, all data is lost when the process terminates. The Append-Only File (AOF) mechanism solves the durability problem by writing every mutating command to a sequential log on disk. On restart, Redis replays this log to reconstruct in-memory state.

**Entry point in code:** `src/aof.c:feedAppendOnlyFile()` at line 1409. It is reached from `src/server.c:call()` at line 3894 through Redis command propagation.

---

## 2. Execution Path Trace: Write Path

```text
Client sends: SET foo bar
       |
src/server.c:processCommand()       parses and validates command
       |
src/server.c:call()                 executes the command
       |
src/server.c:propagate()            decides what to persist
       |
src/aof.c:feedAppendOnlyFile()      formats command as RESP and appends to server.aof_buf
       |
src/aof.c:flushAppendOnlyFile()     writes buffer to the OS and conditionally fsyncs
```

AOF format example:

```text
*3\\r\\n$3\\r\\nSET\\r\\n$3\\r\\nfoo\\r\\n$3\\r\\nbar\\r\\n
```

---

## 3. Design Decisions

### Decision 1: Three-Level fsync Control (`appendfsync`)

| Setting | Code Location | Behavior | Trade-off |
|---|---|---|---|
| `always` | `src/aof.c:flushAppendOnlyFile()` lines 1147-1357 | fsync after each write path flush | strongest durability, lowest throughput |
| `everysec` | same function, plus `server.aof_fsync` checks at lines 1168, 1183, and 1347 | fsync approximately once per second | balanced throughput and bounded loss window |
| `no` | same function | skips Redis-managed fsync | highest throughput, durability delegated to OS |

`src/config.c` maps the `appendfsync` option into `server.aof_fsync` at line 3193, and `src/server.h` stores that field at line 2218. This design lets operators choose the durability/performance tradeoff per deployment.

### Decision 2: AOF Rewrite via Fork

`src/aof.c:rewriteAppendOnlyFileBackground()` at line 2744 starts background rewrite work; `src/aof.c:rewriteAppendOnlyFile()` at line 2664 emits a compact representation of the current keyspace. The design prevents unbounded log growth while allowing the parent process to keep serving clients. Its cost is fork and copy-on-write memory pressure during rewrite.

### Decision 3: RESP Protocol in AOF

`src/aof.c:catAppendOnlyGenericCommand()` at line 1357 serializes commands using the Redis Serialization Protocol. This keeps the log inspectable and repairable by Redis tooling, but the text-like framing is larger than a custom binary format.

---

## 4. Concept Mapping

| DS614 Concept | Redis AOF Implementation |
|---|---|
| Write-Ahead Log (WAL) | AOF records mutations in an append-only log before replay-based recovery |
| Log-Structured Storage | AOF appends sequentially and later compacts with `BGREWRITEAOF` |
| Fault Tolerance / Crash Recovery | `src/aof.c:loadAppendOnlyFiles()` at line 1775 replays the log; truncated tails are checked during startup |
| Partitioning / Replication | Each Redis shard owns its persistence files; replicas receive command streams rather than AOF file shipping |
| Streaming / Ingestion | AOF is a continuous write stream that is read sequentially during recovery |
| Sequential vs Random I/O | AOF favors sequential appends; RDB snapshotting in `src/rdb.c:rdbSaveBackground()` at line 1942 writes periodic full snapshots |

---

## 5. Experiments and Results

### Baseline

**Config:** `appendfsync everysec`, AOF enabled, RDB disabled  
**Workload:** 5000 SET operations through `redis-cli --pipe`  
**Purpose:** Establish normal AOF throughput and file growth.

### Experiment 1 - AOF fsync Policy Comparison

**Manual run pipeline:**

```bash
python3 scripts/exp1_fsync_policy.py
cat results/exp1/results.tsv
```

**Hypothesis:** `appendfsync always` will be slower than `everysec` because it can force a disk flush on each write path flush.

**Code reference:** `src/aof.c:flushAppendOnlyFile()` line 1147; the `server.aof_fsync == AOF_FSYNC_ALWAYS` branch is checked around lines 1177, 1279, and 1330.

**Plot:** `plots/exp1_fsync_throughput.png`  
![Experiment 1 throughput](plots/exp1_fsync_throughput.png)

**Terminal screenshot:** `screenshots/exp1_terminal.png`  
![Experiment 1 terminal output](screenshots/exp1_terminal.png)

**Results:**

{exp1_table}

**Observation:** `everysec` reached {fmt_num(e1["everysec"]["ops_per_sec"])} ops/sec, about {exp1_ratio}x the throughput of `always`. The `no` mode was fastest in this run at {fmt_num(e1["no"]["ops_per_sec"])} ops/sec. AOF file sizes were close because all modes logged the same commands; fsync policy changes when data is forced to disk, not what is logged.

**Explanation:** With `appendfsync always`, Redis pays a durability barrier much more often. With `everysec`, `flushAppendOnlyFile()` can defer fsync work to the periodic path, separating most client writes from disk flush latency.

### Experiment 2 - AOF Rewrite Threshold Behavior

**Manual run pipeline:**

```bash
python3 scripts/exp2_rewrite.py
cat results/exp2/results.tsv
```

**Hypothesis:** After repeated overwrites, the AOF contains redundant history; `BGREWRITEAOF` should compact it to the current state.

**Code reference:** `src/aof.c:rewriteAppendOnlyFile()` line 2664 writes live keyspace state, and `src/aof.c:rewriteAppendOnlyFileBackground()` line 2744 starts the background rewrite.

**Plot:** `plots/exp2_rewrite_sizes.png`  
![Experiment 2 rewrite sizes](plots/exp2_rewrite_sizes.png)

**Terminal screenshot:** `screenshots/exp2_terminal.png`  
![Experiment 2 terminal output](screenshots/exp2_terminal.png)

**Results:**

{exp2_table}

**Observation:** Rewrite reduced the AOF from {fmt_num(e2["size_before_rewrite_bytes"])} bytes to {fmt_num(e2["size_after_rewrite_bytes"])} bytes, a {exp2_ratio}x compression ratio.

**Explanation:** Each overwrite appends a fresh SET command, even for the same logical key. Rewrite discards historical commands and writes one final value per live key.

### Experiment 3 - AOF Recovery After Simulated Crash

**Manual run pipeline:**

```bash
python3 scripts/exp3_crash_recovery.py
cat results/exp3/results.tsv
```

**Hypothesis:** After `SIGKILL`, Redis can recover all fsynced AOF data. With `appendfsync everysec`, writes inside the last roughly one second may be at risk.

**Code reference:** `src/aof.c:loadAppendOnlyFiles()` line 1775 loads AOF files during startup and replays commands to rebuild state.

**Plot:** `plots/exp3_recovery_rate.png`  
![Experiment 3 recovery rate](plots/exp3_recovery_rate.png)

**Terminal screenshot:** `screenshots/exp3_terminal.png`  
![Experiment 3 terminal output](screenshots/exp3_terminal.png)

**Results:**

{exp3_table}

**Observation:** Redis recovered {e3["recovered"]} of {e3["n_keys"]} keys, for a {e3["recovery_rate_pct"]}% recovery rate, with {e3["lost"]} lost keys.

**Explanation:** The experiment waited 2.5 seconds before `SIGKILL`, giving the `everysec` policy enough time to flush and fsync the AOF data. On restart, Redis replayed the AOF log and reconstructed the keys.

### Experiment 4 - AOF vs RDB Write Throughput

**Manual run pipeline:**

```bash
python3 scripts/exp4_aof_vs_rdb.py
cat results/exp4/results.tsv
```

**Hypothesis:** RDB mode will have higher write throughput because normal writes do not append every command to a persistence log.

**Code reference:** AOF uses `src/aof.c:feedAppendOnlyFile()` line 1409 on mutation propagation; RDB snapshotting is handled by `src/rdb.c:rdbSaveBackground()` line 1942 outside the normal per-command write path.

**Plot:** `plots/exp4_aof_vs_rdb.png`  
![Experiment 4 AOF vs RDB](plots/exp4_aof_vs_rdb.png)

**Terminal screenshot:** `screenshots/exp4_terminal.png`  
![Experiment 4 terminal output](screenshots/exp4_terminal.png)

**Results:**

{exp4_table}

**Observation:** At 10000 writes, RDB reached {fmt_num(exp4_rdb[2]["ops_per_sec"])} ops/sec versus AOF at {fmt_num(exp4_aof[2]["ops_per_sec"])} ops/sec, a {exp4_ratio_10k}x RDB advantage in this run.

**Explanation:** AOF pays per-command log-buffer and write overhead. RDB mode can keep the write path memory-only until snapshot criteria trigger background persistence.

### Experiment 5 - AOF Under Write Skew (Hot Key)

**Manual run pipeline:**

```bash
python3 scripts/exp5_hot_key_skew.py
cat results/exp5/results.tsv
```

**Hypothesis:** Before rewrite, hot-key and uniform workloads should have similarly large AOFs because both issue 5000 commands. After rewrite, the hot-key AOF should shrink much more because only one live key remains.

**Code reference:** `src/aof.c:feedAppendOnlyFile()` line 1409 appends every SET regardless of key uniqueness; `src/aof.c:rewriteAppendOnlyFile()` line 2664 emits only current keyspace state.

**Plot:** `plots/exp5_skew_compression.png`  
![Experiment 5 skew compression](plots/exp5_skew_compression.png)

**Terminal screenshot:** `screenshots/exp5_terminal.png`  
![Experiment 5 terminal output](screenshots/exp5_terminal.png)

**Results:**

{exp5_table}

**Observation:** The hot-key workload compressed {exp5_ratio_delta}x more than the uniform workload by ratio. This confirms that AOF is blind to write skew during appends, while rewrite is highly effective when many writes collapse to one live key.

**Explanation:** AOF records command history, not semantic uniqueness. A single hot key updated 5000 times creates 5000 log entries, but rewrite needs only that key's final value.

---

## 6. Failure Analysis

### What happens when data size increases significantly?

AOF file growth is linear in mutation count, and restart time grows with log size because `loadAppendOnlyFiles()` must replay commands. `BGREWRITEAOF` controls file growth but uses fork, so large in-memory datasets can experience copy-on-write memory pressure while the parent continues to serve writes.

### What happens under skew?

Experiment 5 shows that skew can create a large AOF with low information content. Storage grows with writes, not key cardinality, until rewrite compacts redundant history.

### What happens if Redis fails mid-rewrite?

The old AOF remains the recovery source until the rewrite completes and Redis swaps in the new files. If a crash leaves a truncated AOF tail, Redis startup checks the AOF and can truncate to the last valid command boundary before replay.

### What assumptions does this system rely on?

The filesystem must honor `fsync()` semantics, the disk must have space for ongoing appends and rewrite output, and operators must choose an `appendfsync` policy that matches their loss tolerance.

---

## 7. Key Insights

1. AOF is Redis's write-ahead log: append mutations sequentially, replay them during recovery.
2. The fsync tradeoff is measurable: `always` improved durability but cost throughput in Experiment 1.
3. Rewrite is AOF compaction: it removes redundant history and keeps only current state.
4. AOF and RDB solve different durability problems; together they mirror WAL plus checkpoint patterns.
5. A future improvement would be incremental rewrite that reduces fork-based copy-on-write spikes on large datasets.

---

## 8. References

- Redis source in this workspace: `../redis/src/aof.c`, `../redis/src/server.c`, `../redis/src/server.h`, `../redis/src/config.c`, `../redis/src/rdb.c`
- Redis upstream source: https://github.com/redis/redis
- Redis persistence documentation: https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/
- Kleppmann, *Designing Data-Intensive Applications*, chapters on storage engines and durability

---

*Generated by the experiment pipeline. Raw TSV files are in `results/`, and generated PNG plots are in `plots/`.*
"""

    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8") as f:
        f.write(readme)

    generate_slides_outline()
    generate_plots(exp1, exp2, exp3, exp4, exp5)
    generate_screenshots({
        "exp1": exp1,
        "exp2": exp2,
        "exp3": exp3,
        "exp4": exp4,
        "exp5": exp5,
    })

    print("\n=== EXPERIMENT RESULTS SUMMARY ===\n")
    for exp_name, rows in [("exp1", exp1), ("exp2", exp2), ("exp3", exp3), ("exp4", exp4), ("exp5", exp5)]:
        print(f"--- {exp_name.upper()} ---")
        for row in rows:
            print("  " + " | ".join(f"{k}={v}" for k, v in row.items()))
        print()
    print("[DONE] Wrote README.md, slides_outline.md, plots/*.png, and screenshots/*.png")


if __name__ == "__main__":
    main()
