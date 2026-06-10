# Evaluation

Trajectory Memory Ledger currently has four levels of evidence:

1. Artifact correctness: the Rust runtime builds, passes tests, passes clippy, performs one-shot ingestion, normalizes schema-v2 records, scores trajectories, handles `(date, seq)` cursor rollover, and appends under a file lock.
2. Corpus and reward evidence: the originating deployment corpus contains 7,468 scored trajectories, 67,409 observed tool events, 73,470 recovered tool steps, and 3,678 exported ChatML examples. Reward-selected trajectories are substantially stronger than a deterministic random control on the current selection metric.
3. Held-out coding-agent model-quality evidence: the repository now includes a real KARL V7 benchmark over 10 models and 5 held-out coding-agent session contexts. It measures scored response quality, not executed task completion.
4. Executed downstream task completion: the executable benchmark runner now has a checked synthetic smoke report, real prompt-conditioned model-output reports, Gemma 4 E2B/12B QAT base-model sanity reports, and two real adapter-conditioned reports over a six-task held-out Python stdlib task set. The first Gemma 3 1B/256-token adapter lane was negative at 0/6 for every condition. The stronger Gemma 4 E2B/512-row/4096-token adapter lane is positive for reward-selected data: `reward_selected` scores 5/6, `random` scores 3/6, and `full_ledger` scores 2/6 with `synthetic_rows=0` and `hidden_tests_sent_to_model=false`. This is a real downstream lift signal on the small executable gate; the next validity step is replication on a larger task set and stronger model tier.

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

## Executable Task Benchmark Runner

`materialize-executable-bench` and `executable-task-bench` are the execution gate for downstream task-completion evidence. The materializer joins canonical task specs with condition-specific candidate/model-output rows. The executor then materializes each joined row into an isolated temp workspace, writes setup files and candidate files, runs a verifier command with a timeout, and aggregates pass/fail by condition.

Run the checked smoke suite:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-smoke.jsonl \
  --candidates examples/evaluation/executable-candidates-smoke.jsonl \
  --output examples/evaluation/executable-task-smoke.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-smoke.jsonl \
  --output benchmarks/executable-task-smoke-2026-06-06.json
```

Task spec row shape:

```json
{
  "task_id": "py_add_ints",
  "setup_files": {"tests/test_math_tools.py": "..."},
  "verifier_command": "python3 -m unittest discover -s tests",
  "timeout_ms": 5000,
  "benchmark_kind": "executable-task-bench-smoke",
  "task_set": "python-stdlib-smoke-v0"
}
```

Candidate row shape:

```json
{
  "condition": "reward_selected",
  "task_id": "py_add_ints",
  "candidate_files": {"src/math_tools.py": "..."},
  "generated_tools": ["Read", "Edit", "Bash"],
  "tests_included": true,
  "source_artifact": "model-output-run.jsonl",
  "synthetic": true
}
```

Safety and reproducibility properties:

| Property | Behavior |
|---|---|
| Workspace isolation | Each row runs in a fresh temp directory |
| Path safety | Absolute paths, parent directories, and non-normal path components are rejected |
| Timeout | Hung verifier commands are killed and reported as timeouts |
| Evidence | Report includes exit code, timeout flag, duration, stdout/stderr previews, and failed task ids |
| Task/candidate split | Held-out test fixtures are stored once, separate from model candidate files |
| Synthetic marking | Input rows can be marked `synthetic`; the checked smoke fixture marks every row synthetic |

Checked smoke result:

| Condition | Tasks | Passed | Pass rate | Failed task ids |
|---|---:|---:|---:|---|
| `reward_selected` | 3 | 3 | 100% | none |
| `full_ledger` | 3 | 2 | 66.67% | `py_unique_sorted` |
| `random` | 3 | 0 | 0% | `py_add_ints`, `py_slugify`, `py_unique_sorted` |

This report proves the executable benchmark path works: verifier commands run, failing candidates fail, passing candidates pass, and aggregation is condition-aware. It is intentionally not downstream model-lift evidence because all 9 checked rows are synthetic smoke rows.

## Real Model-Output Executable Benchmark

The first non-synthetic executable benchmark uses the held-out task set in `examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl` and public task prompts in `examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl`. Public prompts were sent to real model CLIs with trajectory context built from the private KARL trajectory store. Hidden verifier tests were not included in the prompts.

Candidate generation:

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
```

Materialization and execution:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --candidates examples/evaluation/executable-candidates-claude-sonnet-karl-context-2026-06-07.jsonl \
  --output examples/evaluation/executable-task-claude-sonnet-karl-context-2026-06-07.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-claude-sonnet-karl-context-2026-06-07.jsonl \
  --output benchmarks/executable-task-claude-sonnet-karl-context-2026-06-07.json \
  --require-real
```

The same protocol was run for `gemini-2.5-flash`. Both reports have `synthetic_rows=0` and `measures_executed_task_completion=true`.

Held-out task set:

| Task id | Target behavior |
|---|---|
| `py_parse_duration` | Parse h/m/s duration strings into seconds and reject malformed input |
| `py_merge_intervals` | Merge overlapping or adjacent intervals |
| `py_topological_sort` | Deterministic topological sort with cycle rejection |
| `py_group_by_key` | Group dictionaries by key while preserving order and missing-key behavior |
| `py_chunked` | Chunk list or generator input into tuples |
| `py_redact_secrets` | Redact obvious API keys, bearer tokens, and password assignments |

Real executable result:

| Backend | Condition | Rows | Passed | Pass rate | Failed task ids |
|---|---|---:|---:|---:|---|
| Claude Sonnet | `random` | 6 | 6 | 100% | none |
| Claude Sonnet | `reward_selected` | 6 | 6 | 100% | none |
| Claude Sonnet | `full_ledger` | 6 | 6 | 100% | none |
| Gemini 2.5 Flash | `random` | 6 | 5 | 83.33% | `py_parse_duration` |
| Gemini 2.5 Flash | `reward_selected` | 6 | 5 | 83.33% | `py_chunked` |
| Gemini 2.5 Flash | `full_ledger` | 6 | 4 | 66.67% | `py_parse_duration`, `py_chunked` |

Interpretation:

- This is real executable task-completion evidence because generated candidate files were run against hidden verifier tests in isolated workspaces.
- Claude Sonnet saturated this six-task benchmark, so it provides no condition separation.
- Gemini 2.5 Flash produced a discriminative result: `reward_selected` tied `random` at 5/6 and exceeded `full_ledger` at 4/6.
- This does not prove that reward-selected trajectory training improves task completion over random selection. It proves a real prompt-conditioned executable evaluation path and shows that the current v0 task set is too small/easy to establish reward-selected lift over random.

## Training-Lift Adapter Experiment

The next empirical gate was a trained or adapter-conditioned executable held-out coding-agent evaluation with the same task set across three ledger-data conditions:

| Condition | Description |
|---|---|
| `random` | Training examples sampled randomly from eligible trajectories |
| `reward_selected` | Training examples selected by positive domain advantage |
| `full_ledger` | Full normalized export, filtered for train/eval leakage |

The repository includes a preflight script for preparing the controlled private splits:

```bash
python3 scripts/prepare_training_lift_experiment.py \
  --trajectory-store "$KARL_TRAJECTORY_STORE" \
  --heldout-public-tasks examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl \
  --heldout-task-specs examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --output-dir output/private-training-lift-2026-06-08 \
  --report benchmarks/training-lift-preflight-2026-06-08.json \
  --sample-size 96 \
  --probe-remote \
  --remote-host mac5
```

The script writes private train/validation JSONL files under ignored `output/private-*` paths and writes only aggregate hashes/statistics to the checked report. The initial `2026-06-08` remote preflight had status `blocked_remote_training_unreachable`; a second local preflight recorded a Mac5-free fallback with status `ready_for_local_adapter_training`.

| Condition | Selected records | Train | Validation | Mean reward | Mean advantage |
|---|---:|---:|---:|---:|---:|
| `random` | 96 | 86 | 10 | 0.6750 | 0.7333 |
| `reward_selected` | 96 | 86 | 10 | 0.7408 | 1.6182 |
| `full_ledger` | 96 | 86 | 10 | 0.6787 | 0.8774 |

Additional preflight facts:

| Field | Value |
|---|---:|
| Eligible private records after filters | 2,920 |
| Held-out leakage-risk exclusions | 2,138 |
| Missing prompt exclusions | 749 |
| Too-few-tool exclusions | 1,663 |
| Remote trainer probe | `mac5` SSH failed with timeout |

The local fallback preflight was run as:

```bash
python3 scripts/prepare_training_lift_experiment.py \
  --trajectory-store "$KARL_TRAJECTORY_STORE" \
  --heldout-public-tasks examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl \
  --heldout-task-specs examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --output-dir output/private-training-lift-2026-06-08 \
  --report benchmarks/training-lift-local-preflight-2026-06-08.json \
  --sample-size 96 \
  --probe-local
```

Local preflight result:

| Field | Value |
|---|---|
| Status | `ready_for_local_adapter_training` |
| Python | `/opt/homebrew/opt/python@3.14/bin/python3.14` |
| MLX plain import | Fails with duplicate OpenMP runtime |
| MLX workaround import | Passes with `KMP_DUPLICATE_LIB_OK=TRUE` |
| `mlx_lm` help check | Passes |
| Memory | 16.0 GB |
| Free disk | 6.97 GB |

This meant the adapter experiment could proceed without Mac5 if needed, but Mac5 later became reachable and was used for the checked adapter run.

Mac5 later became reachable, so the three adapters were trained there using `mlx-community/gemma-3-1b-it-4bit`. Adapter weights, raw training rows, and raw generation logs remain under ignored private output directories and are not checked in.

Training settings:

| Setting | Value |
|---|---:|
| Iterations | 500 |
| Batch size | 1 |
| LoRA layers | 4 |
| Max sequence length | 256 |
| Learning rate | 1e-5 |
| Validation rows per condition | 10 |

Checked adapter-training result:

| Condition | Final train loss | Final validation loss | Validation rank |
|---|---:|---:|---:|
| `reward_selected` | 1.129 | 1.484 | 1 |
| `full_ledger` | 0.973 | 1.843 | 2 |
| `random` | 0.918 | 2.031 | 3 |

The reward-selected adapter reduced validation loss by 26.93% relative to `random`; `full_ledger` reduced validation loss by 9.26% relative to `random`. This is training-objective evidence only. It does not establish downstream task-completion lift.

Candidate generation from the trained adapters used only the public prompts:

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
```

The generated candidate report has `synthetic_rows=0` and `hidden_tests_sent_to_model=false`.

Materialization and execution:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --candidates examples/evaluation/executable-candidates-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl \
  --output examples/evaluation/executable-task-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl

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

Interpretation:

- The training-lift gate was executed end-to-end: private splits, three adapters, public-prompt candidate generation, hidden-test materialization, and `--require-real` executable scoring.
- The reward-selected split produced the best validation loss, which supports the claim that the reward-selected data better matches the private validation objective.
- The downstream executable benchmark is negative. It does not prove that reward-selected trajectory training improves task completion over random selection.
- The next empirical gate should use a stronger base model or more capable training recipe and a larger/harder executable task set before making a downstream-lift claim.

### Gemma 4 Base-Model Sanity Gate

The first local adapter result was all-zero, but that did not isolate the cause. It combined a very small base model, a small private split, 256-token training context, and limited generation behavior. Stronger base-model sanity runs were added so the repository can distinguish "the benchmark is impossible" from "the previous training recipe was too weak."

Candidate generation used `mlx-community/gemma-4-E2B-it-qat-4bit` and `mlx-community/gemma-4-12B-it-qat-4bit` through `mlx-vlm` on Mac5. The script loads the MLX-VLM model once, applies the instruct chat template, sends only public task prompts and starter files, records raw generations outside the public candidate JSONL, and writes a report with `hidden_tests_sent_to_model=false`.

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
```

Generation report:

| Field | Value |
|---|---:|
| Model | `mlx-community/gemma-4-E2B-it-qat-4bit` |
| Backend | `mlx_vlm.generate` |
| Public tasks | 6 |
| Synthetic rows | 0 |
| Hidden tests sent to model | false |
| Max generation tokens | 2048 |
| Public compatibility failures before hidden tests | 0/6 |

The 12B run used the same protocol with `mlx-community/gemma-4-12B-it-qat-4bit`, `max_tokens=4096`, `synthetic_rows=0`, and `hidden_tests_sent_to_model=false`. It loaded successfully on Mac5. One public compatibility failure remained before hidden-test materialization: `py_redact_secrets` produced malformed Python even after two public-only repair attempts.

Materialization and execution:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl \
  --candidates examples/evaluation/executable-candidates-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.jsonl \
  --output examples/evaluation/executable-task-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.jsonl \
  --output benchmarks/executable-task-mlx-gemma4-e2b-qat-base-mac5-2026-06-10.json \
  --require-real
```

Checked base-model executable result:

| Condition | Rows | Passed | Pass rate | Failed task ids |
|---|---:|---:|---:|---|
| `gemma4_e2b_qat_base` | 6 | 3 | 50.0% | `py_topological_sort`, `py_chunked`, `py_redact_secrets` |
| `gemma4_12b_qat_base` | 6 | 5 | 83.33% | `py_redact_secrets` |

Interpretation:

- The old all-zero local result should not be read as proof that the ledger idea failed. It was a negative result for the specific Gemma 3 1B adapter setup.
- The Gemma 4 E2B QAT base model reaches 3/6 on the same hidden-test executable task set without ledger fine-tuning.
- The Gemma 4 12B QAT base model reaches 5/6 on the same task set, confirming that Mac5 can run a materially stronger local baseline.
- The remaining 12B failure is a malformed redaction implementation, not a benchmark/system crash. It points toward a public-only repair/checking layer, not hidden-test leakage.
- The next controlled lift experiment should start from Gemma 4 12B-class or stronger models, train with at least 4096-token context, use hundreds or thousands of rows per condition, and report both base-model and adapter-conditioned executable deltas.

### Gemma 4 E2B 512-Row Adapter Lift Gate

The stronger adapter lane reuses the same private trajectory pool but increases the training scale and context length: 512 selected records per condition, 460 train rows and 52 validation rows, 4096-token training context, 500 MLX LoRA iterations, and raw-Python public-only candidate generation. Raw private rows, adapters, and raw generation logs remain under ignored `output/private-*` paths. The public-safe aggregate training report is `benchmarks/training-lift-adapter-training-mlx-gemma4-e2b-512x4096-mac5-2026-06-10.json`.

Training settings:

| Setting | Value |
|---|---:|
| Base model | `mlx-community/gemma-4-E2B-it-qat-4bit` |
| Rows per condition | 512 |
| Train / validation rows | 460 / 52 |
| Iterations | 500 |
| Batch size | 1 |
| LoRA layers | 4 |
| Max sequence length | 4096 |
| Learning rate | 1e-5 |
| Gradient checkpointing | true |

Aggregate training result:

| Condition | Mean reward | Mean advantage | Final train loss | Final validation loss |
|---|---:|---:|---:|---:|
| `random` | 0.6782 | 0.8051 | 1.066 | 1.089 |
| `reward_selected` | 0.7259 | 1.6717 | 0.963 | 1.277 |
| `full_ledger` | 0.6790 | 0.8333 | 0.846 | 0.354 |

The validation objective does not rank the conditions the same way as the hidden executable task result, so downstream completion must be measured directly.

Candidate generation used `scripts/generate_executable_candidates_mlx_adapter.py` with `--prompt-format raw-python`, `--max-tokens 1024`, and one public-only repair attempt. Hidden tests were not sent to the model. The checked generation report is `benchmarks/executable-candidate-generation-mlx-gemma4-e2b-adapters-512x4096-rawpython-mac5-2026-06-10.json`.

Checked adapter-conditioned executable result:

| Condition | Rows | Passed | Pass rate | Failed task ids |
|---|---:|---:|---:|---|
| `random` | 6 | 3 | 50.00% | `py_parse_duration`, `py_chunked`, `py_redact_secrets` |
| `reward_selected` | 6 | 5 | 83.33% | `py_chunked` |
| `full_ledger` | 6 | 2 | 33.33% | `py_parse_duration`, `py_topological_sort`, `py_group_by_key`, `py_chunked` |

Interpretation:

- This is the first positive downstream adapter lift signal in the repository: `reward_selected` beats `random` by two tasks and 33.33 percentage points on the same hidden executable gate.
- The result has `synthetic_rows=0` and records `hidden_tests_sent_to_model=false`.
- The old all-zero adapter result is now correctly scoped to the Gemma 3 1B/256-token recipe.
- The task set has only six tasks, so this is not yet a broad SWE-style performance proof. The next gate should replicate the lift on E4B or a 12B-class cloud training run and a larger 50-100 task executable set.

### Larger 60-Task Replication Gate

The six-task lift signal was followed by a larger Python stdlib held-out suite, `python-stdlib-heldout-v1-60`. The suite has 60 public prompts, 60 hidden-test executable specs, and an oracle candidate file. The oracle report passed all tasks, so the suite itself is internally consistent.

Run shape:

```bash
cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-oracle-python-stdlib-heldout-v1.jsonl \
  --output benchmarks/executable-task-oracle-python-stdlib-heldout-v1-2026-06-10.json \
  --require-real
```

Gemma 4 E2B QAT base, E4B QAT base, and the E2B reward-selected adapter were then generated from public prompts only, materialized, and scored with `--require-real`.

Checked 60-task result:

| Condition | Rows | Passed | Pass rate | Synthetic rows |
|---|---:|---:|---:|---:|
| Oracle | 60 | 60 | 100.00% | 0 |
| Gemma 4 E2B QAT base | 60 | 50 | 83.33% | 0 |
| Gemma 4 E4B QAT base | 60 | 49 | 81.67% | 0 |
| Gemma 4 E2B reward-selected adapter | 60 | 46 | 76.67% | 0 |

Interpretation:

- The larger suite falsifies the broad version of the six-task lift claim for the current E2B adapter recipe.
- Current evidence does not prove that TML improves downstream coding-agent task completion.
- The executable evaluation path is stronger after this run: oracle validation, non-synthetic model rows, hidden-test execution, and base/adapted comparisons all work on a 60-task suite.
- Validation loss and small-suite lift are not enough. Future claims need larger-suite downstream pass-rate lift.

### Harness Skill Extraction From Failed Runs

The `skillgraph-evolve` binary converts executable benchmark deltas into regression-gated skill packages. It lets the system learn from a failed adapter run without promoting unsafe routing behavior.

Run:

```bash
cargo run --bin skillgraph-evolve -- \
  --public-tasks examples/evaluation/executable-public-tasks-python-stdlib-heldout-v1.jsonl \
  --task-specs examples/evaluation/executable-taskset-python-stdlib-heldout-v1.jsonl \
  --baseline-report benchmarks/executable-task-mlx-gemma4-e2b-qat-base-heldout-v1-mac5-2026-06-10.json \
  --comparison-report benchmarks/executable-task-mlx-gemma4-e2b-reward-selected-512x4096-rawpython-heldout-v1-mac5-2026-06-10.json \
  --output-dir examples/skills/python-stdlib-heldout-v1/e2b-reward-selected-vs-base
```

Checked result:

| Metric | Value |
|---|---:|
| Baseline passed | 50/60 |
| Comparison passed | 46/60 |
| Net pass delta | -4 |
| Fixed tasks | 5 |
| Regressed tasks | 9 |
| Shared failures | 5 |
| Promoted skills | 0 |
| Proposed skills | 1 |
| Quarantined skills | 7 |
| Diagnostic skills | 1 |
| Active router skills | 0 |

The generated artifacts live under `examples/skills/python-stdlib-heldout-v1/e2b-reward-selected-vs-base/`.

Artifacts:

| Artifact | Purpose |
|---|---|
| `trajectory-skills.jsonl` | Structured skill rows grouped by task family |
| `skill-graph.json` | SkillDAG-style nodes and typed edges |
| `router-index.json` | Activation index with promoted/proposed/quarantined/diagnostic status |
| `skillgraph-evolution-report.json` | Aggregate gate result |
| `packages/<skill_id>/SKILL.md` | Human-readable activation boundary |
| `packages/<skill_id>/MEMORY.md` | Evidence memory for the package |
| `packages/<skill_id>/tests.jsonl` | Task-level delta evidence |
| `packages/<skill_id>/failure_modes.json` | Regression and shared-failure boundary |

Interpretation:

- The router correctly has no active skills because the global adapter comparison regressed.
- `python_stdlib_math_trajectory_delta` is only `proposed`, not active, because it repaired `py_v1_moving_average` but the global gate failed.
- Families with regressions are quarantined and should be used as repair targets, not automatic prompts.
- This is harness improvement, not downstream performance proof.

### Narrow Math Repair Router

The proposed math package can be tested without adopting the failed adapter globally. `scripts/apply_skillgraph_repair_router.py` builds a new candidate set from:

- the E2B base candidate rows for all tasks by default
- the reward-selected adapter candidate row only for repaired task ids claimed by allowed skill statuses

Run:

```bash
python3 scripts/apply_skillgraph_repair_router.py \
  --base-candidates examples/evaluation/executable-candidates-mlx-gemma4-e2b-qat-base-heldout-v1-mac5-2026-06-10.jsonl \
  --comparison-candidates examples/evaluation/executable-candidates-mlx-gemma4-e2b-reward-selected-512x4096-rawpython-heldout-v1-mac5-2026-06-10.jsonl \
  --skills-jsonl examples/skills/python-stdlib-heldout-v1/e2b-reward-selected-vs-base/trajectory-skills.jsonl \
  --allow-status proposed \
  --condition skillgraph_math_repair_router \
  --output examples/evaluation/executable-candidates-skillgraph-math-repair-router-heldout-v1-2026-06-10.jsonl \
  --report benchmarks/executable-candidate-generation-skillgraph-math-repair-router-heldout-v1-2026-06-10.json
```

The generated router report has `hidden_tests_sent_to_model=false`, `synthetic_rows=0`, `preserved_base_row_count=59`, `routed_row_count=1`, and `routed_task_ids=["py_v1_moving_average"]`.

Materialization and execution:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-heldout-v1.jsonl \
  --candidates examples/evaluation/executable-candidates-skillgraph-math-repair-router-heldout-v1-2026-06-10.jsonl \
  --output examples/evaluation/executable-task-skillgraph-math-repair-router-heldout-v1-2026-06-10.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-skillgraph-math-repair-router-heldout-v1-2026-06-10.jsonl \
  --output benchmarks/executable-task-skillgraph-math-repair-router-heldout-v1-2026-06-10.json \
  --require-real
```

Checked executable result:

| Condition | Rows | Passed | Pass rate | Synthetic rows |
|---|---:|---:|---:|---:|
| Gemma 4 E2B QAT base | 60 | 50 | 83.33% | 0 |
| Skillgraph math repair router | 60 | 51 | 85.00% | 0 |

Base-vs-router `skillgraph-evolve` result:

| Metric | Value |
|---|---:|
| Net pass delta | +1 |
| Fixed tasks | 1 |
| Regressed tasks | 0 |
| Promoted skills | 1 |
| Active router skills | 1 |

The active skill is `python_stdlib_math_trajectory_delta`, and the promoted artifacts live under `examples/skills/python-stdlib-heldout-v1/math-repair-router-vs-base/`.

Interpretation:

- This is the first clean 60-task lift from the harness skills layer.
- The lift is narrow and router-level, not adapter-level: the base model remains responsible for 59/60 rows.
- The result supports the strategy "use the skillgraph as a repair map, not as proof."
- The next repair cycle should target another non-regressing family or train a stronger model/adapter recipe, then require the same base-vs-router gate before promotion.
