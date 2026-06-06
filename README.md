# Trajectory Memory Ledger

Schema-normalized experience replay for self-improving coding agents.

Trajectory Memory Ledger is a systems architecture and Rust runtime for turning real coding-agent work into a durable learning signal. It records tool-use trajectories, normalizes heterogeneous logs into a stable schema, scores each trajectory with a six-signal reward model, and exports the resulting ledger for training, routing, analysis, and evaluation.

The reference daemon is `trajectory-ledgerd`, a Rust binary that owns the infrastructure-sensitive live path:

- ingest dated gateway event files
- normalize records to schema v2
- score trajectories at emit time
- track cursor state by `(date, seq)`
- append JSONL records with file locking
- export Prometheus text metrics

Python, notebooks, and training scripts can then consume the normalized ledger for SFT export, ablation reports, and model training.

## Why This Exists

Most coding-agent evaluations are point-in-time benchmarks. Real agents, however, produce a continuous stream of behavior: reads, edits, tests, retries, failures, corrections, and successful completions. The ledger treats those trajectories as experience replay.

The core claim is simple: if agent work is recorded in a stable schema, scored with interpretable process signals, and replayed into training/routing loops, the system can improve from its own operating history without requiring human preference labeling for every step.

## Current Artifact

This repository contains:

- `crates/trajectory-ledgerd`: Rust daemon and library
- `docs/schema-v2.md`: canonical trajectory schema
- `docs/reward-model.md`: six-signal reward model
- `docs/architecture.md`: system architecture
- `docs/metrics.md`: Prometheus metrics
- `docs/evaluation.md`: benchmark results and downstream evaluation protocol
- `examples/`: synthetic event and trajectory examples
- `paper/trajectory-memory-ledger.md`: paper draft

The originating deployment corpus, not included here, contains 7,468 scored trajectories, 67,409 observed tool events, and 73,470 recovered tool steps. Raw private trajectories are intentionally excluded from this public artifact.

## Install

```bash
git clone https://github.com/Diomandeee/trajectory-memory-ledger.git
cd trajectory-memory-ledger
cargo build --release
```

## Run One Ingestion Pass

```bash
cargo run --release --bin trajectory-ledgerd -- run \
  --once \
  --date 2026-06-03 \
  --events-dir examples \
  --cursor /tmp/trajectory-ledgerd.cursor \
  --store /tmp/trajectory-ledgerd-trajectories.jsonl \
  --metrics /tmp/trajectory-ledgerd.prom
```

Inspect the output:

```bash
cat /tmp/trajectory-ledgerd-trajectories.jsonl | jq .
cat /tmp/trajectory-ledgerd.prom
```

Run continuously by omitting `--once` and pointing `--events-dir` at a live gateway event directory.

## Evaluation

Run the daemon benchmark:

```bash
cargo run --release --bin daemon-bench -- \
  --flows 1000 \
  --steps 3 \
  --concurrent-writers 8 \
  --records-per-writer 100 \
  --output benchmarks/daemon-benchmark-2026-06-03.json
```

Current checked-in result on Apple M4 / macOS 15.6.1 / rustc 1.95.0:

- 8,000 synthetic event envelopes ingested in 6.287s
- 1,272.385 events/sec
- 159.048 trajectory cards/sec
- append latency mean/p95: 3.627ms / 4.027ms
- duplicate reprocess skip: 1,000 duplicate cards skipped
- date-scoped cursor rollover: passed
- concurrent append: 800/800 records, 800 unique IDs

Run the agent-evaluation aggregation harness:

```bash
cargo run --bin agent-eval -- \
  --input examples/evaluation/tool-plan-generations.jsonl \
  --output benchmarks/agent-eval-example-2026-06-03.json
```

The checked-in `agent-eval` example is synthetic. It demonstrates the measurement protocol, not downstream model improvement. The next empirical gate is a held-out coding-agent benchmark comparing random trajectory selection, reward-selected trajectory selection, and the full normalized ledger export.

## Test

```bash
cargo test
cargo clippy -- -D warnings
```

## Architecture

```text
Gateway Events
    |
    v
trajectory-ledgerd
    |-- date-scoped cursor
    |-- flow grouping
    |-- schema-v2 normalization
    |-- six-signal reward scoring
    |-- locked JSONL append
    |-- Prometheus metrics
    v
Trajectory Memory Ledger
    |
    +--> SFT / preference export
    +--> reward ablations
    +--> skill/entity routing
    +--> paper metrics
```

## Publication Positioning

This is best treated as a systems and artifact paper first:

**Trajectory Memory Ledger: Schema-Normalized Experience Replay for Self-Improving Coding Agents**

The Rust daemon makes the artifact reproducible. The next research step is stronger downstream evaluation: train/evaluate agent models against held-out tasks and quantify improvement from trajectory replay versus random or unscored data selection.

## License

MIT
