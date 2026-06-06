# Evaluation

Trajectory Memory Ledger currently has four levels of evidence:

1. Artifact correctness: the Rust runtime builds, passes tests, passes clippy, performs one-shot ingestion, normalizes schema-v2 records, scores trajectories, handles `(date, seq)` cursor rollover, and appends under a file lock.
2. Corpus and reward evidence: the originating deployment corpus contains 7,468 scored trajectories, 67,409 observed tool events, 73,470 recovered tool steps, and 3,678 exported ChatML examples. Reward-selected trajectories are substantially stronger than a deterministic random control on the current selection metric.
3. Held-out coding-agent model-quality evidence: the repository now includes a real KARL V7 benchmark over 10 models and 5 held-out coding-agent session contexts. It measures scored response quality, not executed task completion.
4. Executed downstream task completion: not established yet. A same-task comparison of random trajectory selection, reward-selected trajectory selection, and full-ledger export still needs to be run before claiming SWE-style task-completion lift.

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

## Held-Out Coding-Agent Model Benchmark

`heldout-agent-bench` aggregates real held-out coding-agent benchmark score rows. The checked-in fixture is a privacy-preserving aggregate conversion of the KARL V7 model benchmark generated on `2026-04-02` by `~/Desktop/karl/karl/v7/model_benchmark.py`.

Run:

```bash
cargo run --bin heldout-agent-bench -- \
  --input examples/evaluation/karl-v7-heldout-coding-agent-model-scores.jsonl \
  --output benchmarks/karl-v7-heldout-agent-benchmark-2026-04-02.json
```

Protocol:

| Field | Value |
|---|---:|
| Benchmark kind | `karl-v7-heldout-coding-agent-model-quality` |
| Task set | `karl-v7-5-session-contexts` |
| Conditions | 10 model backends |
| Held-out contexts | 5 per model, 50 total scored contexts |
| Score metric | `karl.v7.style_validator.overall` |
| Quality pass threshold | 0.4 |
| Raw generations included | No |
| Executed task completion measured | No |

Checked-in result:

| Condition | Model id | Contexts | Quality pass | Mean score | Mean latency |
|---|---|---:|---:|---:|---:|
| GPT-5.4-mini | `gpt-5.4-mini` | 5 | 100% | 1.0000 | 1.5688s |
| GPT-OSS 120B | `openai/gpt-oss-120b` | 5 | 100% | 1.0000 | 5.5191s |
| MiniMax M2.5 | `MiniMaxAI/MiniMax-M2.5` | 5 | 100% | 1.0000 | 7.0485s |
| DeepSeek R1 | `deepseek-ai/DeepSeek-R1-0528` | 5 | 100% | 1.0000 | 10.4395s |
| DeepSeek V3.1 | `deepseek-ai/DeepSeek-V3.1` | 5 | 100% | 0.9850 | 2.7698s |
| GLM 4.7 | `zai-org/GLM-4.7` | 5 | 100% | 0.9850 | 5.5894s |
| GPT-OSS 20B | `openai/gpt-oss-20b` | 5 | 100% | 0.9840 | 4.4039s |
| GLM-5 | `zai-org/GLM-5` | 5 | 80% | 0.8000 | 16.5684s |
| Kimi K2.5 | `moonshotai/Kimi-K2.5` | 5 | 40% | 0.3850 | 21.2216s |
| Qwen3.5 397B | `Qwen/Qwen3.5-397B-A17B` | 5 | 0% | 0.0000 | 25.4496s |

The aggregate report selects `GPT-5.4-mini` as `best_condition_by_mean_score` because four models tied at mean score 1.0000 and `GPT-5.4-mini` had the lowest mean latency among the tied models.

This is real held-out model-quality evidence over coding-agent contexts. It is not evidence that the ledger's reward-selected trajectories improve executed coding-task success, because the benchmark does not run tests in target repositories and does not compare random versus reward-selected training data on the same executable task set.

## Required Downstream Experiment

The next empirical gate is an executable held-out coding-agent evaluation with the same task set across three ledger-data conditions:

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

Only after this experiment should the paper claim downstream executed task-performance lift from trajectory replay.
