# Presentation Outline - Redis AOF Persistence

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
