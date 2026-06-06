# Evaluation

Trajectory Memory Ledger currently has three levels of evidence:

1. Artifact correctness: the Rust runtime builds, passes tests, passes clippy, performs one-shot ingestion, normalizes schema-v2 records, scores trajectories, handles `(date, seq)` cursor rollover, and appends under a file lock.
2. Corpus and reward evidence: the originating deployment corpus contains 7,468 scored trajectories, 67,409 observed tool events, 73,470 recovered tool steps, and 3,678 exported ChatML examples. Reward-selected trajectories are substantially stronger than a deterministic random control on the current selection metric.
3. Downstream agent/model performance: not established yet. The repository includes an evaluation harness, but a held-out model or routing benchmark still needs to be run before claiming task-completion lift.

## Daemon Benchmark

Run:

```bash
cargo run --release --bin daemon-bench -- \
  --flows 1000 \
  --steps 3 \
  --concurrent-writers 8 \
  --records-per-writer 100 \
  --output benchmarks/daemon-benchmark-2026-06-03.json
```

Environment for the checked-in result:

| Field | Value |
|---|---:|
| Platform | Apple M4 |
| OS | macOS 15.6.1 |
| Rust | rustc 1.95.0 |
| Cargo | cargo 1.95.0 |

Checked-in result:

| Metric | Value |
|---|---:|
| Workload | 1,000 flows, 3 steps/flow |
| Event envelopes | 8,000 |
| Ingest time | 6.287 s |
| Events/sec | 1,272.385 |
| Cards/sec | 159.048 |
| Append latency mean | 3.627 ms |
| Append latency p95 | 4.027 ms |
| Duplicate reprocess skip | 1,000 duplicate cards skipped |
| Cursor rollover | Passed |
| Concurrent append | 800/800 records, 800 unique IDs |

The benchmark uses synthetic gateway events. It measures daemon throughput, duplicate handling, date-scoped cursor behavior, and concurrent JSONL append safety. It does not measure downstream model improvement.

## Reward Selection Evidence

The normalized private deployment corpus is not included in this public repository, but its aggregate statistics are:

| Metric | Value |
|---|---:|
| Scored trajectories | 7,468 |
| Observed tool events | 67,409 |
| Recovered tool steps | 73,470 |
| Exported ChatML examples | 3,678 |
| Train / validation split | 3,310 / 368 |
| Top-35 vs random reward Cohen's d | 2.7159 |
| Top-35 vs random advantage Cohen's d | 2.7917 |

The strongest leave-one-out ablation signal is verification. Removing verification changes the ranking most sharply, which supports the design choice to reward tested and inspected edits over unverified mutation.

This is evidence that the reward function selects cleaner training examples than random sampling. It is not, by itself, evidence that a trained model completes more tasks.

## Agent Evaluation Harness

`agent-eval` aggregates evaluated tool-plan generations by experimental condition.

Expected input format:

```json
{"condition":"reward_selected","task_id":"task_001","generated_tools":["Read","Edit","Bash"],"task_passed":true,"tests_included":true,"build_included":true,"reward_score":0.74}
```

Run the synthetic example:

```bash
cargo run --bin agent-eval -- \
  --input examples/evaluation/tool-plan-generations.jsonl \
  --output benchmarks/agent-eval-example-2026-06-03.json
```

The checked-in example contains synthetic rows only. It verifies the harness shape and output metrics; it should not be cited as model performance evidence.

## Required Downstream Experiment

The next empirical gate is a held-out coding-agent evaluation with the same task set across three conditions:

| Condition | Description |
|---|---|
| `random` | Tool-plan or training examples sampled randomly from eligible trajectories |
| `reward_selected` | Examples selected by positive domain advantage |
| `full_ledger` | Full normalized export, filtered for train/eval leakage |

Recommended metrics:

| Metric | Meaning |
|---|---|
| `task_pass_rate` | Held-out coding task passed its tests or verifier |
| `valid_tool_plan_rate` | Generated plan contains executable, non-empty tool steps |
| `test_inclusion_rate` | Plan includes test or verification behavior |
| `build_inclusion_rate` | Plan includes build or compile behavior when appropriate |
| `retry_loop_rate` | Plan repeats the same tool pattern excessively |
| `mean_reward_score` | Reward model score on held-out generated plans |

Only after this experiment should the paper claim downstream agent-performance lift.
