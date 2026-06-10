# Trajectory Memory Ledger

## Schema-Normalized Experience Replay for Self-Improving Coding Agents

**Mohamed Diomande**

June 2026

---

## Abstract

Coding agents generate a continuous stream of operational experience: prompts, file reads, code edits, shell commands, failures, retries, verification steps, and user corrections. Most of this experience is discarded after the session ends. Trajectory Memory Ledger turns that stream into a durable learning signal. It records coding-agent tool-use trajectories, normalizes heterogeneous logs into a stable append-only schema, scores each trajectory with an interpretable six-signal reward model, and exports high-advantage examples for routing, analysis, and supervised fine-tuning.

This paper presents the public reference artifact and the current evaluation evidence. The Rust daemon, `trajectory-ledgerd`, ingests gateway events, tracks date-scoped cursors, normalizes schema-v2 trajectory cards, scores records at emit time, appends under a file lock, and exports Prometheus metrics. On the checked synthetic daemon benchmark, it ingests 8,000 event envelopes in 6.287 seconds, reaching 1,272.385 events/sec and 159.048 trajectory cards/sec with p95 append latency of 4.027 ms. The originating private deployment corpus contains 7,468 scored trajectories, 67,409 observed tool events, 73,470 recovered tool steps, and 3,678 exported ChatML training examples.

The current empirical evidence supports five measured claims and one important negative boundary: the artifact is operationally reproducible, the reward model selects cleaner trajectories than random sampling, a real held-out coding-agent model-quality benchmark can be reproduced from aggregate rows in the repository, real model-output candidates can be evaluated on executable held-out tasks, and reward-selected private training data gives the best small-adapter validation loss. The strongest checked held-out model-quality result evaluates 10 model conditions over 5 coding-agent session contexts each, with `GPT-5.4-mini` selected as the best tied condition by mean score and latency. The prompt-conditioned executable benchmark evaluates Claude Sonnet and Gemini 2.5 Flash outputs over a six-task Python stdlib held-out set, with hidden verifier tests and `synthetic_rows=0`. Claude Sonnet saturates the benchmark at 6/6 for all context conditions. Gemini 2.5 Flash reaches 5/6 for `random`, 5/6 for `reward_selected`, and 4/6 for `full_ledger`. The trained-adapter gate then trains three MLX LoRA adapters with `mlx-community/gemma-3-1b-it-4bit`: `reward_selected` achieves the best validation loss at 1.484 versus `full_ledger` at 1.843 and `random` at 2.031, but all three adapters score 0/6 on the same executable held-out tasks. Stronger local base-model sanity runs reach 3/6 with `mlx-community/gemma-4-E2B-it-qat-4bit` and 5/6 with `mlx-community/gemma-4-12B-it-qat-4bit` on that same held-out executable set before ledger fine-tuning. Therefore the artifact now proves adapter training and executable adapter evaluation, but it still does not prove downstream reward-selected task-completion lift over random selection.

---

## Claim Status

| Claim | Status | Evidence | Boundary |
|---|---|---|---|
| Durable trajectory ingestion is implemented and reproducible | Proven for the public artifact | Rust tests, clippy, one-shot ingestion, cursor rollover, locked append, daemon benchmark | Daemon benchmark uses synthetic gateway events |
| The runtime is fast enough for live collection | Supported | 8,000 event envelopes in 6.287s, 1,272.385 events/sec, 159.048 cards/sec, p95 append latency 4.027 ms | Measured on Apple M4, macOS 15.6.1, rustc 1.95.0 |
| Reward selection chooses cleaner trajectories than random sampling | Supported | Top-35 reward-selected mean reward 0.7734 vs random-35 mean reward 0.6771, Cohen's d 2.7159 | This is selection-quality evidence, not model improvement by itself |
| Reward components are interpretable and ablatable | Supported | Leave-one-out ablation over 7,468 scored trajectories, verification is most load-bearing with rank correlation 0.5666 when removed | Historical outcome annotations are sparse, so outcome defaults often dominate less than desired |
| Held-out coding-agent model-quality evaluation is real | Proven for response-quality scoring | 10 model conditions, 5 held-out coding-agent contexts each, 50 total scored contexts | Does not execute repository tasks or measure SWE task completion |
| Executable benchmark runner works | Proven for harness mechanics | 3 Python stdlib smoke tasks x 3 conditions, isolated temp workspaces, verifier commands, pass/fail aggregation | Smoke rows are synthetic |
| Real executable model-output evaluation | Proven for prompt-conditioned model outputs | Claude Sonnet and Gemini 2.5 Flash, 6 held-out tasks x 3 context conditions each, 36 non-synthetic rows total | Measures executable pass/fail for generated candidates |
| Reward-selected context improves over full-ledger context | Partially supported | Gemini 2.5 Flash: `reward_selected` 5/6 vs `full_ledger` 4/6 | Single backend and small task set |
| Reward-selected training data improves adapter validation loss over random | Supported for the private split | Mac5 MLX LoRA run: `reward_selected` validation loss 1.484 vs `random` 2.031, a 26.93% reduction | Validation loss is not executable task completion |
| Stronger local base-model sanity is non-zero | Supported | Gemma 4 E2B QAT base: 3/6; Gemma 4 12B QAT base: 5/6 on the same hidden-test executable task set | Not ledger-trained, not evidence of reward-selected lift |
| Reward-selected trajectory data improves executable coding-task completion over random | Not proven; current adapter run is negative | Mac5 adapter-conditioned executable benchmark: `random` 0/6, `reward_selected` 0/6, `full_ledger` 0/6 | Requires stronger training/generation setup and a larger or harder task set |

The short answer: performance and evaluation are now proven for the artifact/runtime, held-out model-quality scoring, real executable model-output measurement, and the mechanics of training/evaluating adapters from controlled private splits. The stronger claim, that ledger-selected training data improves real executable coding-task completion over random selection, is not proven; the first adapter-conditioned executable result is negative. The local all-zero result should be interpreted narrowly as a weak Gemma 3 1B adapter/training-recipe failure, not as proof that the executable task set or the ledger hypothesis is dead; Gemma 4 12B QAT solves 5/6 before any ledger fine-tuning.

---

## 1. Introduction

Large language model coding agents now perform real software engineering work: reading repositories, modifying source files, running tests, deploying services, debugging infrastructure, and coordinating multi-step plans. These sessions contain rich process data. A successful session is not only the final answer. It is the sequence of operations that led there: which files were inspected, which edits were made, whether tests were run, how failures were handled, and whether the user later corrected the agent.

Most agent systems discard this trajectory data. They may keep chat transcripts, but they do not convert operational behavior into a normalized, queryable, scored experience store. As a result, the agent that succeeds today does not automatically improve tomorrow's routing, planning, or training data.

Trajectory Memory Ledger addresses that gap. It treats coding-agent work as experience replay. The system captures tool-use trajectories, normalizes them into schema-v2 trajectory cards, scores them using a six-signal reward model, and exports high-advantage records for training and routing loops.

This paper contributes:

1. A schema-normalized ledger format for coding-agent trajectories.
2. A Rust daemon for durable live ingestion, scoring, append safety, cursor state, and metrics.
3. A six-signal reward model covering outcome, process, efficiency, verification, consistency, and wasted motion.
4. A deployment-backed corpus summary from 7,468 scored trajectories.
5. A reproducible evaluation suite with daemon throughput, reward-selection checks, held-out model-quality aggregation, and executable task benchmark tooling.
6. A clear empirical boundary separating proven artifact behavior from future downstream model-lift claims.

---

## 2. System Overview

The system is a closed loop:

```text
Agent Work
  -> Trajectory Capture
  -> Schema-v2 Normalization
  -> Reward Scoring
  -> Ledger Append
  -> Analysis / Routing / Training Export
  -> Better Agent Behavior
```

The public artifact focuses on the durable middle of this loop. `trajectory-ledgerd` owns the infrastructure-sensitive live path:

- reads dated gateway event files,
- tracks cursor state by `(date, seq)`,
- groups flow events into completed trajectories,
- normalizes them into schema-v2 cards,
- scores trajectories at emit time,
- appends JSONL records under a file lock,
- emits Prometheus text metrics.

Research scripts, notebooks, trainers, and routing logic can then consume the normalized store without needing to handle live ingestion correctness.

---

## 3. Trajectory Schema

Each schema-v2 record is an append-only trajectory card. A simplified example:

```json
{
  "schema_version": 2,
  "id": "traj_session_1717420000",
  "session_id": "session_uuid",
  "source": "verbose-all",
  "channel": "live",
  "domain": "ops",
  "recorded_at": "2026-06-03T12:00:00Z",
  "skill": {
    "name": "ops:deploy",
    "domain": "ops"
  },
  "context": {
    "prompt_text": "deploy the service",
    "cwd": "/Users/dev/project",
    "git_repo": "service"
  },
  "trajectory": {
    "tool_sequence": ["Read", "Edit", "Bash"],
    "tool_counts": {
      "Read": 1,
      "Edit": 1,
      "Bash": 1
    },
    "total_tools": 3,
    "successes": 3,
    "failures": 0,
    "bash_errors": 0,
    "observed_event_count": 3,
    "placeholder_event_count": 0,
    "events": []
  },
  "outcome": {
    "annotation_status": "scored",
    "correction_detected": false,
    "build_success": true,
    "reward_score": 0.78,
    "advantage": 0.28,
    "reward_components": {}
  },
  "timing": {
    "duration_s": 65.0
  }
}
```

Historical rows from earlier writers are normalized into the same schema. When older logs were capped, the system records explicit placeholder events so recovered tool-step counts remain length-consistent while preserving the distinction between directly observed events and recovered slots.

---

## 4. Reward Model

The deployed reward model combines six bounded signals:

```text
R =
  0.25 * outcome
+ 0.22 * process
+ 0.13 * efficiency
+ 0.13 * verification
+ 0.13 * consistency
+ 0.14 * wasted_motion
```

The design goals are:

- no mandatory human annotation,
- interpretable component scores,
- bounded values in `[0, 1]`,
- resistance to single-axis reward hacking,
- compatibility with both live and backfilled trajectories.

### 4.1 Outcome

Outcome estimates whether the user accepted the work. Signals include absence of correction, absence of redo request, build success, and continuation. When a signal is unavailable, the score renormalizes over available signals. If no outcome signal exists, the component defaults to neutral `0.5`.

### 4.2 Process

Process rewards clean execution. It uses tool success rate, shell-command cleanliness, and a penalty for consecutive failures. A trajectory that reaches the final result but loops through failed commands is scored lower than a direct, adaptive trajectory.

### 4.3 Efficiency

Efficiency measures shape: tool diversity, duration efficiency, and file touch rate. It does not reward being short at all costs. It rewards having enough context, making purposeful edits, and avoiding stalled or excessively rapid tool use.

### 4.4 Verification

Verification rewards tests, builds, read-after-write checks, and other evidence that the agent inspected its own work. In the current corpus, this is the most load-bearing reward component.

### 4.5 Consistency

Consistency penalizes contradictory ordering and thrashing, such as repeated failed commands without adaptation or mutation before sufficient context has been gathered.

### 4.6 Wasted Motion

Wasted motion penalizes low-linearity behavior: avoidable retries, repeated reads after the relevant answer is already known, and circular tool patterns.

---

## 5. Training Export

The ledger supports an OAPL-Lite export strategy, a simplified offline advantage-weighted supervised fine-tuning pipeline:

1. Filter trajectories with too few observed tool events.
2. Score each trajectory.
3. Compute domain-relative advantage.
4. Oversample positive-advantage trajectories.
5. Convert selected records into ChatML tool-plan examples.
6. Split into train and validation sets.

The normalized deployment export contains 3,678 ChatML examples, split into 3,310 train rows and 368 validation rows. Exported plans average 9.26 observed tool steps after placeholder events are excluded from plan text.

This export is evidence that the ledger can produce training data. It is not, by itself, proof that a fine-tuned model completes more tasks. That requires the executable downstream experiment described in Section 9.

---

## 6. Deployment Corpus

The originating deployment corpus is private and excluded from the public repository. Aggregate statistics are included:

| Metric | Value |
|---|---:|
| Scored trajectories | 7,468 |
| Observed tool events | 67,409 |
| Recovered tool steps | 73,470 |
| Explicit placeholder steps from capped logs | 6,061 |
| Exported ChatML examples | 3,678 |
| Train / validation examples | 3,310 / 368 |
| Mean reward | 0.6632 |
| Median reward | 0.6675 |
| Reward standard deviation | 0.0498 |
| Reward range | 0.4666 to 0.8165 |

Raw trajectories, prompts, private files, and raw generations are intentionally not included in the public artifact.

---

## 7. Evaluation

The current evaluation has four layers:

1. Artifact correctness and performance.
2. Reward-selection quality.
3. Held-out coding-agent model-quality scoring.
4. Real executable model-output task-completion measurement.

All four layers now contain checked evidence. The fourth layer proves real executable model-output measurement, not trained model-lift.

### 7.1 Runtime Performance

The daemon benchmark runs `trajectory-ledgerd` against synthetic gateway events.

Command:

```bash
cargo run --release --bin daemon-bench -- \
  --flows 1000 \
  --steps 3 \
  --concurrent-writers 8 \
  --records-per-writer 100 \
  --output benchmarks/daemon-benchmark-2026-06-03.json
```

Environment:

| Field | Value |
|---|---|
| Platform | Apple M4 |
| OS | macOS 15.6.1 |
| Rust | rustc 1.95.0 |
| Cargo | cargo 1.95.0 |

Result:

| Metric | Value |
|---|---:|
| Flows | 1,000 |
| Steps per flow | 3 |
| Event envelopes | 8,000 |
| Ingest time | 6.287 s |
| Events/sec | 1,272.385 |
| Cards/sec | 159.048 |
| Append latency mean | 3.627 ms |
| Append latency p95 | 4.027 ms |
| Duplicate reprocess skip | 1,000 duplicate cards skipped |
| Cursor rollover | Passed |
| Concurrent append | 800/800 records, 800 unique IDs |

This supports the claim that the daemon is fast enough for live trajectory collection and handles critical durability behavior: duplicate skipping, date-scoped cursor rollover, and concurrent append safety.

### 7.2 Reward-Selection Quality

On the normalized exportable subset, the top 35 domain-advantage trajectories are substantially stronger than a deterministic random-35 control:

| Metric | Reward-selected top 35 | Random 35 |
|---|---:|---:|
| Mean reward | 0.7734 | 0.6771 |
| Reward Cohen's d | 2.7159 | n/a |
| Advantage Cohen's d | 2.7917 | n/a |

This is a selection-quality result. It shows that the reward model selects cleaner examples than random sampling according to the deployed scoring function. It does not prove downstream task-completion improvement.

### 7.3 Reward Ablation

A leave-one-out ablation over all 7,468 scored trajectories measures how much each reward component affects ranking. Lower rank correlation after removing a component means that component carries more ranking signal.

| Rank | Removed signal | Rank correlation | Top-20 overlap | Rank impact |
|---:|---|---:|---:|---:|
| 1 | Verification | 0.5666 | 2/20 | 0.4334 |
| 2 | Process | 0.8909 | 19/20 | 0.1091 |
| 3 | Efficiency | 0.8938 | 15/20 | 0.1062 |
| 4 | Wasted motion | 0.8949 | 15/20 | 0.1051 |
| 5 | Consistency | 0.9346 | 12/20 | 0.0654 |
| 6 | Outcome | 1.0000 | 20/20 | 0.0000 |

Component means:

| Signal | Mean |
|---|---:|
| Outcome | 0.5000 |
| Process | 0.9502 |
| Efficiency | 0.5571 |
| Verification | 0.3799 |
| Consistency | 0.6430 |
| Wasted motion | 0.8836 |

Verification is the strongest current differentiator. Outcome has zero rank impact in this historical backfill because most records do not contain cross-turn correction or redo annotations, so the outcome channel often defaults to neutral `0.5`. This is a data-availability limitation, not evidence that outcome feedback is unimportant.

### 7.4 Held-Out Coding-Agent Model-Quality Benchmark

The repository includes aggregate rows from a real KARL V7 held-out coding-agent model-quality benchmark generated on 2026-04-02 from `~/Desktop/karl/v7-model-benchmark.json` by `~/Desktop/karl/karl/v7/model_benchmark.py`.

Command:

```bash
cargo run --bin heldout-agent-bench -- \
  --input examples/evaluation/karl-v7-heldout-coding-agent-model-scores.jsonl \
  --output benchmarks/karl-v7-heldout-agent-benchmark-2026-04-02.json
```

Protocol:

| Field | Value |
|---|---|
| Benchmark kind | `karl-v7-heldout-coding-agent-model-quality` |
| Task set | `karl-v7-5-session-contexts` |
| Conditions | 10 model backends |
| Held-out contexts | 5 per model |
| Total scored contexts | 50 |
| Score metric | `karl.v7.style_validator.overall` |
| Quality pass threshold | 0.4 |
| Raw generations included | No |
| Executed task completion measured | No |

Result:

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

Four models tie at mean score 1.0000. The aggregate runner selects `GPT-5.4-mini` as `best_condition_by_mean_score` because it is the fastest tied condition.

This is real held-out model-quality evidence over coding-agent contexts. It is not evidence that reward-selected trajectory training improves executable SWE-style task completion, because the benchmark does not run tests in target repositories and does not compare random-selected, reward-selected, and full-ledger training conditions.

### 7.5 Executable Task Benchmark Smoke

The artifact includes two binaries for executable downstream evaluation:

- `materialize-executable-bench`, which joins canonical task specs with condition-specific candidate rows.
- `executable-task-bench`, which materializes each candidate in an isolated temp workspace and runs verifier commands.

Command:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-smoke.jsonl \
  --candidates examples/evaluation/executable-candidates-smoke.jsonl \
  --output examples/evaluation/executable-task-smoke.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-smoke.jsonl \
  --output benchmarks/executable-task-smoke-2026-06-06.json
```

Smoke result:

| Condition | Tasks | Passed | Pass rate | Failed task ids |
|---|---:|---:|---:|---|
| `reward_selected` | 3 | 3 | 100% | none |
| `full_ledger` | 3 | 2 | 66.67% | `py_unique_sorted` |
| `random` | 3 | 0 | 0% | `py_add_ints`, `py_slugify`, `py_unique_sorted` |

The smoke report proves:

- verifier commands run,
- candidates are isolated in temp workspaces,
- passing code passes,
- failing code fails,
- results are aggregated by condition,
- stdout and stderr previews are captured,
- unsafe paths are rejected by the runner.

It does not prove model-lift. All 9 checked rows are synthetic candidate rows. They exist to validate mechanics before running real model outputs.

### 7.6 Real Executable Model-Output Benchmark

The non-synthetic executable benchmark uses six held-out Python standard-library tasks. Public task prompts are stored separately from hidden verifier tests. The generator sends only the public prompts and condition-specific trajectory context to the model backend. The hidden verifier tests are introduced later by `materialize-executable-bench` and executed by `executable-task-bench` in isolated temporary workspaces.

The three context conditions are:

| Condition | Prompt context |
|---|---|
| `random` | Six randomly sampled trajectory summaries from the private KARL trajectory store |
| `reward_selected` | Six high-reward trajectory summaries from the same store |
| `full_ledger` | Six mixed trajectory summaries spanning low, medium, and high reward records |

The held-out task set contains:

| Task id | Behavior |
|---|---|
| `py_parse_duration` | Parse h/m/s duration strings and reject malformed inputs |
| `py_merge_intervals` | Merge overlapping or adjacent intervals |
| `py_topological_sort` | Return deterministic lexical topological order and reject cycles |
| `py_group_by_key` | Group dictionaries by key while preserving order and missing-key behavior |
| `py_chunked` | Chunk list or generator input into tuples |
| `py_redact_secrets` | Redact API keys, bearer tokens, and password assignments |

Checked reports:

| Backend | Condition | Rows | Passed | Pass rate | Failed task ids |
|---|---|---:|---:|---:|---|
| Claude Sonnet | `random` | 6 | 6 | 100% | none |
| Claude Sonnet | `reward_selected` | 6 | 6 | 100% | none |
| Claude Sonnet | `full_ledger` | 6 | 6 | 100% | none |
| Gemini 2.5 Flash | `random` | 6 | 5 | 83.33% | `py_parse_duration` |
| Gemini 2.5 Flash | `reward_selected` | 6 | 5 | 83.33% | `py_chunked` |
| Gemini 2.5 Flash | `full_ledger` | 6 | 4 | 66.67% | `py_parse_duration`, `py_chunked` |
| Gemma 4 E2B QAT base | `gemma4_e2b_qat_base` | 6 | 3 | 50.00% | `py_topological_sort`, `py_chunked`, `py_redact_secrets` |
| Gemma 4 12B QAT base | `gemma4_12b_qat_base` | 6 | 5 | 83.33% | `py_redact_secrets` |

These executable reports have `synthetic_rows=0` and `measures_executed_task_completion=true`. This proves that the artifact can evaluate real model-generated source files on hidden executable tasks. The result is useful but bounded. Claude Sonnet saturates the task set, so it cannot separate context conditions. Gemini 2.5 Flash shows a real difference between `reward_selected` and `full_ledger`, but `reward_selected` ties `random`. Gemma 4 E2B QAT gives a non-zero local base-model sanity line at 3/6, and Gemma 4 12B QAT reaches 5/6, which helps interpret the later 0/6 adapter result as a weak-model/training-recipe failure rather than a harness failure. Therefore this benchmark establishes real executable performance measurement and a baseline for future comparisons, but it does not yet establish reward-selected lift over random.

---

## 8. Discussion

Trajectory Memory Ledger is best understood as an artifact and systems paper at the current stage. The runtime and data pipeline are implemented. The scoring model has interpretable selection and ablation evidence. The held-out model-quality benchmark is real and reproducible from aggregate rows. The executable task-completion path has now been fed prompt-conditioned model outputs, stronger local Gemma 4 E2B/12B base models, and trained-adapter outputs, producing checked non-synthetic pass/fail reports.

The strongest empirical result inside the reward model is the verification signal. Removing verification changes the top-ranked set more than removing any other component. This matches the practical coding-agent intuition: the best sessions do not merely edit code, they close the loop with tests, builds, or inspection.

The weakest current empirical signal is outcome. In live future data, user corrections and redo requests should be highly valuable. In the historical backfill, those annotations are sparse, so outcome often defaults to neutral. This makes outcome underrepresented in current ablations.

The most important research boundary is downstream training lift. The repository now has a trained-adapter experiment, and the result is mixed: the reward-selected private split gives the best validation loss, but the adapter-conditioned executable benchmark is 0/6 for every condition. Stronger Gemma 4 base models reach 3/6 and 5/6, so the right diagnosis is not that the held-out executable benchmark is impossible; it is that the first adapter setup was too weak. The honest claim is not "ledger training improves coding agents" yet. The honest claim is "the ledger records, scores, exports, trains from, and evaluates the data needed to test that hypothesis, and the first adapter-conditioned executable evaluation is negative."

---

## 9. Training-Lift Adapter Experiment

The trained-adapter gate evaluates whether reward-selected trajectory data improves a model trained on private ledger exports. It uses the same six held-out executable Python stdlib tasks as Section 7 and the same three conditions:

| Condition | Training data |
|---|---|
| `random` | Randomly sampled eligible private trajectories |
| `reward_selected` | Positive-advantage private trajectories selected by the reward model |
| `full_ledger` | Full normalized export after leakage filtering |

The gate has three stages: prepare private train/validation splits, train one adapter per condition, then generate held-out candidate files from each adapter using only public task prompts. Hidden verifier tests are introduced only by `materialize-executable-bench`.

### 9.1 Split Preparation

Running `scripts/prepare_training_lift_experiment.py` against the private KARL trajectory store creates three private train/validation splits under ignored `output/private-*` paths and writes public-safe aggregate reports under `benchmarks/`. The script records only counts, means, hashes, and trainer reachability. It does not write raw private prompts or tool plans into the repository.

The checked preflight selected 96 records per condition, split into 86 train rows and 10 validation rows. The resulting condition statistics were:

| Condition | Mean reward | Mean advantage |
|---|---:|---:|
| `random` | 0.6750 | 0.7333 |
| `reward_selected` | 0.7408 | 1.6182 |
| `full_ledger` | 0.6787 | 0.8774 |

The preflight found 2,920 eligible private records after minimum-tool, prompt, plan, and held-out leakage filters. It also recorded 2,138 held-out leakage-risk exclusions, 749 missing-prompt exclusions, and 1,663 too-few-tool exclusions. The initial remote trainer probe timed out on `mac5`; a local preflight then recorded a fallback status of `ready_for_local_adapter_training`. Mac5 later became reachable, so the adapter run was executed there.

### 9.2 Adapter Training

The Mac5 run trained three MLX LoRA adapters from `mlx-community/gemma-3-1b-it-4bit`. The checked public summary is `benchmarks/training-lift-adapter-training-mlx-gemma3-1b-mac5-2026-06-10.json`. Adapter weights, raw training rows, and raw generation logs remain in ignored private output directories.

Training settings:

| Setting | Value |
|---|---:|
| Iterations | 500 |
| Batch size | 1 |
| LoRA layers | 4 |
| Max sequence length | 256 |
| Learning rate | 1e-5 |
| Validation rows per condition | 10 |

Final training result:

| Condition | Final train loss | Final validation loss | Validation rank |
|---|---:|---:|---:|
| `reward_selected` | 1.129 | 1.484 | 1 |
| `full_ledger` | 0.973 | 1.843 | 2 |
| `random` | 0.918 | 2.031 | 3 |

Relative to `random`, `reward_selected` reduces validation loss by 26.93%, and `full_ledger` reduces validation loss by 9.26%. This supports the narrower claim that the reward-selected split better matches the private validation objective under this small-adapter setup.

### 9.3 Executable Adapter Evaluation

Candidate generation used `scripts/generate_executable_candidates_mlx_adapter.py` with only the public prompts in `examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl`. The checked candidate generation report is `benchmarks/executable-candidate-generation-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.json`; it records `synthetic_rows=0` and `hidden_tests_sent_to_model=false`.

The candidates were materialized against the hidden-test task specs and executed with:

```bash
cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl \
  --output benchmarks/executable-task-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.json \
  --require-real
```

Checked adapter-conditioned executable result:

| Condition | Rows | Passed | Pass rate | Failed task ids |
|---|---:|---:|---:|---|
| `random` | 6 | 0 | 0% | all six tasks |
| `reward_selected` | 6 | 0 | 0% | all six tasks |
| `full_ledger` | 6 | 0 | 0% | all six tasks |

This is a real downstream executable evaluation, and it is negative. The training objective separates conditions in the expected direction, but the trained adapters do not complete the held-out executable tasks. The newer Gemma 4 base sanity runs reach 3/6 for E2B QAT and 5/6 for 12B QAT on the same benchmark, so the negative result is best attributed to the small Gemma 3 1B adapter setup, small split size, 256-token training context, and weak generation loop. Therefore this paper must not claim downstream executable task-completion lift from reward-selected trajectory training. The next valid gate is a stronger base model or training recipe, plus public-only repair and a larger and harder held-out executable task set.

---

## 10. Threats to Validity

**Private corpus.** The largest corpus is a private deployment store. Aggregate statistics are reported, but raw rows are not public.

**Synthetic runtime benchmark.** The daemon benchmark measures throughput and durability using synthetic gateway events. It is valid for artifact performance, not for downstream agent quality.

**Aggregate held-out benchmark.** The held-out model-quality benchmark includes aggregate score rows, not raw private prompts or generations. This protects privacy but limits external audit depth.

**Small held-out context count.** The model-quality benchmark uses 5 contexts per model. It is useful as a real sanity check, but it is not a broad benchmark like SWE-bench.

**Outcome sparsity.** Historical backfill records often lack cross-turn correction labels, so outcome contributes less ranking signal than it should in future live data.

**Synthetic executable candidates.** The executable benchmark smoke suite is synthetic. It validates the runner, not the research hypothesis. The separate Claude Sonnet and Gemini 2.5 Flash reports are non-synthetic and should be cited for real model-output performance instead.

**Training-lift downstream result is negative.** The current artifact exports SFT-ready examples, includes prompt-conditioned executable model-output reports, stronger Gemma 4 base-model sanity reports, and a controlled small-adapter experiment. Reward-selected training data achieves the best validation loss, but the adapter-conditioned executable task result is 0/6 for every condition. The Gemma 4 base lines reach 3/6 and 5/6, so the negative adapter result should be treated as a weak training setup, not as a reason to discard the benchmark. This limits the claim to training-objective improvement, not downstream task-completion lift.

---

## 11. Reproducibility

Build and test:

```bash
cargo fmt -- --check
cargo test
cargo clippy -- -D warnings
```

Run one ingestion pass:

```bash
cargo run --release --bin trajectory-ledgerd -- run \
  --once \
  --date 2026-06-03 \
  --events-dir examples \
  --cursor /tmp/trajectory-ledgerd.cursor \
  --store /tmp/trajectory-ledgerd-trajectories.jsonl \
  --metrics /tmp/trajectory-ledgerd.prom
```

Run the daemon benchmark:

```bash
cargo run --release --bin daemon-bench -- \
  --flows 1000 \
  --steps 3 \
  --concurrent-writers 8 \
  --records-per-writer 100 \
  --output benchmarks/daemon-benchmark-2026-06-03.json
```

Run the held-out coding-agent model-quality benchmark:

```bash
cargo run --bin heldout-agent-bench -- \
  --input examples/evaluation/karl-v7-heldout-coding-agent-model-scores.jsonl \
  --output benchmarks/karl-v7-heldout-agent-benchmark-2026-04-02.json
```

Run the executable smoke benchmark:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-smoke.jsonl \
  --candidates examples/evaluation/executable-candidates-smoke.jsonl \
  --output examples/evaluation/executable-task-smoke.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-smoke.jsonl \
  --output benchmarks/executable-task-smoke-2026-06-06.json
```

Run a real executable model-output benchmark:

```bash
python3 scripts/generate_executable_candidates_cli.py \
  --public-tasks examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl \
  --trajectory-store "$KARL_TRAJECTORY_STORE" \
  --output examples/evaluation/executable-candidates-claude-sonnet-karl-context-2026-06-07.jsonl \
  --raw-dir /tmp/tml-real-model-output-2026-06-07 \
  --report benchmarks/executable-candidate-generation-claude-sonnet-2026-06-07.json \
  --backend claude \
  --model sonnet \
  --max-budget-usd 2.00

cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --candidates examples/evaluation/executable-candidates-claude-sonnet-karl-context-2026-06-07.jsonl \
  --output examples/evaluation/executable-task-claude-sonnet-karl-context-2026-06-07.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-claude-sonnet-karl-context-2026-06-07.jsonl \
  --output benchmarks/executable-task-claude-sonnet-karl-context-2026-06-07.json \
  --require-real
```

Run the adapter-conditioned executable benchmark after training the private adapters:

```bash
python3 scripts/generate_executable_candidates_mlx_adapter.py \
  --public-tasks examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl \
  --model mlx-community/gemma-3-1b-it-4bit \
  --adapter-root output/private-adapters-gemma3-1b-2026-06-10 \
  --output examples/evaluation/executable-candidates-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl \
  --raw-dir output/private-generation-raw-gemma3-1b-clean-2026-06-10 \
  --report benchmarks/executable-candidate-generation-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.json \
  --max-tokens 1024 \
  --timeout-s 360 \
  --seed 42

cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --candidates examples/evaluation/executable-candidates-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl \
  --output examples/evaluation/executable-task-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl \
  --output benchmarks/executable-task-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.json \
  --require-real
```

Run the Gemma 4 E2B/12B QAT base-model sanity benchmark:

```bash
python3 scripts/generate_executable_candidates_mlx_vlm.py \
  --public-tasks examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl \
  --model-path ~/Desktop/tml-gemma4-models/gemma-4-E2B-it-qat-4bit \
  --model-label mlx-community/gemma-4-E2B-it-qat-4bit \
  --condition gemma4_e2b_qat_base \
  --output examples/evaluation/executable-candidates-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.jsonl \
  --raw-dir output/private-generation-raw-gemma4-e2b-qat-base-2026-06-10 \
  --report benchmarks/executable-candidate-generation-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.json \
  --max-tokens 2048 \
  --temperature 0.0 \
  --repair-attempts 2

cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --candidates examples/evaluation/executable-candidates-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.jsonl \
  --output examples/evaluation/executable-task-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.jsonl \
  --output benchmarks/executable-task-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.json \
  --require-real
```

For the 12B run, replace the model path/label, condition, and output/report filenames with the `gemma-4-12B-it-qat-4bit` equivalents and use `--max-tokens 4096`.

---

## 12. Conclusion

Trajectory Memory Ledger shows that coding-agent experience can be recorded, normalized, scored, and reused as a durable improvement substrate. The public artifact proves the runtime path: ingestion, cursor safety, schema normalization, reward scoring, locked append, metrics, tests, and benchmarked throughput. The deployment evidence shows a meaningful private corpus of scored trajectories and exported training examples. The reward analysis supports the selection logic, especially the importance of verification behavior. The held-out KARL V7 benchmark adds real model-quality evidence across 50 coding-agent context evaluations. The executable reports add real model-output task-completion evidence across 36 prompt-conditioned non-synthetic candidate rows, 12 Gemma 4 base-model non-synthetic candidate rows, and 18 adapter-conditioned non-synthetic candidate rows.

The remaining research step is clear: improve the training/generation setup until trained models complete held-out executable coding tasks under random, reward-selected, and full-ledger conditions, then compare those pass rates. The first controlled adapter run is valuable because it is real and falsifiable: reward-selected data improves validation loss, but no condition solves the executable tasks. The Gemma 4 base lines show that stronger local generation can solve most of the set before fine-tuning, so the next lift test should start at the 12B capability tier or above. Until a future gate shows `reward_selected` beating `random` on executed tasks, this work should be claimed as a reproducible trajectory-ledger artifact with real model-quality evaluation, real executable model-output baseline results, and a negative first adapter-conditioned downstream result, not as completed proof of trained reward-selected task-completion lift.

---

## References

1. Bai, Y., et al. "Constitutional AI: Harmlessness from AI Feedback." arXiv:2212.08073, 2022.
2. Jimenez, C. E., et al. "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" ICLR, 2024.
3. Lightman, H., et al. "Let's Verify Step by Step." arXiv:2305.20050, 2023.
4. Ouyang, L., et al. "Training language models to follow instructions with human feedback." NeurIPS, 2022.
5. Shazeer, N., et al. "Outrageously Large Neural Networks: The Sparsely-Gated Mixture-of-Experts Layer." ICLR, 2017.
