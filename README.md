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
- `examples/evaluation/karl-v7-heldout-coding-agent-model-scores.jsonl`: privacy-preserving aggregate rows from a real held-out coding-agent model-quality benchmark
- `examples/evaluation/executable-taskset-python-stdlib-smoke.jsonl`: canonical executable smoke task specs
- `examples/evaluation/executable-candidates-smoke.jsonl`: synthetic candidate/model-output rows for the executable smoke suite
- `examples/evaluation/executable-task-smoke.jsonl`: materialized smoke rows for the executable task benchmark runner
- `examples/evaluation/executable-taskset-python-stdlib-heldout-v0.jsonl`: hidden-test executable held-out task specs
- `examples/evaluation/executable-public-tasks-python-stdlib-heldout-v0.jsonl`: public prompts used for real model-output generation
- `examples/evaluation/executable-candidates-claude-sonnet-karl-context-2026-06-07.jsonl`: non-synthetic Claude Sonnet candidate rows
- `examples/evaluation/executable-candidates-gemini-flash-karl-context-2026-06-07.jsonl`: non-synthetic Gemini 2.5 Flash candidate rows
- `examples/evaluation/executable-candidates-mlx-gemma3-1b-adapters-mac5-clean-2026-06-10.jsonl`: non-synthetic MLX adapter candidate rows from the controlled training-lift split
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

The checked-in `agent-eval` example is synthetic. It demonstrates the tool-plan aggregation protocol, not downstream model improvement.

Run the real held-out coding-agent model-quality benchmark:

```bash
cargo run --bin heldout-agent-bench -- \
  --input examples/evaluation/karl-v7-heldout-coding-agent-model-scores.jsonl \
  --output benchmarks/karl-v7-heldout-agent-benchmark-2026-04-02.json
```

This benchmark aggregates the real KARL V7 model run from `2026-04-02`: 10 models x 5 held-out coding-agent session contexts, scored by `karl.v7.style_validator.overall` with pass threshold `0.4`. Raw private generations are intentionally not included.

Current result:

- total evaluated contexts: 50
- score metric: `karl.v7.style_validator.overall`
- best by mean score with latency tie-break: `GPT-5.4-mini`
- 1.0 mean score / 100% quality pass: `GPT-5.4-mini`, `GPT-OSS 120B`, `MiniMax M2.5`, `DeepSeek R1`
- fastest 1.0-score model: `GPT-5.4-mini` at 1.5688s mean latency
- lowest result: `Qwen3.5 397B`, 0.0 mean score / 0% quality pass

Boundary: this measures model response quality on held-out coding-agent contexts. It does not execute repository tasks or prove that reward-selected trajectory training improves SWE-style task completion. The repository now includes that same-task adapter gate; its first result is negative for executable task completion, even though reward-selected training gives the best validation loss.

Run the executable task benchmark smoke suite:

```bash
cargo run --bin materialize-executable-bench -- \
  --tasks examples/evaluation/executable-taskset-python-stdlib-smoke.jsonl \
  --candidates examples/evaluation/executable-candidates-smoke.jsonl \
  --output examples/evaluation/executable-task-smoke.jsonl

cargo run --bin executable-task-bench -- \
  --input examples/evaluation/executable-task-smoke.jsonl \
  --output benchmarks/executable-task-smoke-2026-06-06.json
```

The materializer keeps the held-out task set separate from condition-specific candidate files, which is the format needed for real random/reward/full-ledger model outputs. The executor then materializes each candidate into an isolated temp workspace, runs its verifier command, captures pass/fail, timeout, duration, and output previews, then aggregates by condition. The checked smoke fixture is synthetic and exists to validate the execution path only. It is not model-lift evidence.

Smoke result:

- `reward_selected`: 3/3 pass
- `full_ledger`: 2/3 pass
- `random`: 0/3 pass
- synthetic rows: 9/9

Run the real executable model-output benchmark:

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

Real non-synthetic result on the six-task Python stdlib held-out set:

- Claude Sonnet: `random` 6/6, `reward_selected` 6/6, `full_ledger` 6/6
- Gemini 2.5 Flash: `random` 5/6, `reward_selected` 5/6, `full_ledger` 4/6
- synthetic rows: 0/36 across the two real reports

Boundary: this proves executable model-output measurement. It does not prove trained reward-selected trajectory lift over random, because Claude saturated the benchmark and Gemini tied `reward_selected` with `random` while beating `full_ledger`.

Prepare the controlled training-lift gate:

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

Checked preflight result:

- private random/reward-selected/full-ledger train/valid splits were generated locally
- each condition has 96 selected records, split 86 train / 10 validation
- mean reward: `random` 0.6750, `reward_selected` 0.7408, `full_ledger` 0.6787
- remote trainer status: blocked, `mac5` SSH timed out
- Mac5-free local trainer status: ready with `KMP_DUPLICATE_LIB_OK=TRUE`
- local trainer resources: 16 GB memory, 6.97 GB free disk at preflight time

Run the trained-adapter executable gate after one MLX LoRA adapter has been trained per condition:

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

Checked Mac5 adapter-training result with `mlx-community/gemma-3-1b-it-4bit`:

- final validation loss: `reward_selected` 1.484, `full_ledger` 1.843, `random` 2.031
- relative validation-loss reduction vs `random`: `reward_selected` 26.93%, `full_ledger` 9.26%
- executable held-out task pass rate: `random` 0/6, `reward_selected` 0/6, `full_ledger` 0/6
- synthetic rows: 0/18 in the adapter-conditioned executable report

Boundary: the controlled adapters were trained and evaluated. The reward-selected split produced the best private validation loss, but downstream executable task-completion lift is not proven because every adapter condition failed all six held-out executable tasks.

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

The Rust daemon makes the artifact reproducible. The held-out KARL V7 benchmark adds a real model-quality result over coding-agent contexts, and the non-synthetic executable reports add real model-output task-completion measurements. The training-lift gate has now been run through Mac5 adapter training: reward-selected data gives the best validation loss, but the checked adapter-conditioned executable benchmark is negative at 0/6 for all conditions. The next research step is a stronger training/generation setup and a larger executable task set before claiming downstream lift.

## License

MIT
