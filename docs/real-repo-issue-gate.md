# Real-Repo Issue Gate

The honest downstream proof for Trajectory Memory Ledger is not another local
stdlib task suite. It is same-agent issue resolution on real repositories.

The gate compares:

- `base_agent`: the coding agent without TML planner memory.
- `base_agent_tml_planner`: the same agent, model, budget, timeout, and patch
  harness, with TML planner/retrieval allowed before patch generation.

Everything else stays fixed. The official evaluator applies each generated
patch inside repository containers and judges whether the issue is resolved.

## Evidence Ladder

| Stage | Size | Purpose | Claim allowed |
|---|---:|---|---|
| Fixture preflight | 2 synthetic rows | Validate schema, coverage, and claim guard | No performance claim |
| Verified Mini or frozen Verified pilot | 50 real issues | Decide whether the planner generalizes at all | Pilot only |
| SWE-bench Lite | 300 real issues | Cheaper paper-grade issue-resolution result | Broad real-repo claim if positive |
| SWE-bench Verified | 500 real issues | Stronger human-validated result | Strongest issue-resolution claim |

## Contract

- Same instance ids for both conditions.
- Same base model and agent loop.
- Same wall-clock, token, turn, and patch-generation budget.
- Same SWE-bench harness version, dataset, split, timeout, and workers.
- Hidden tests and harness reports are not available during generation.
- The TML planner may use ledger memory, skillgraph packages, and public issue
  context before patch generation.
- The TML planner may not use the base condition's harness failures to repair
  the planner condition inside the same comparison.

## Prepare Or Summarize

The script accepts official SWE-bench prediction JSONL files:

```json
{"instance_id":"sympy__sympy-20590","model_name_or_path":"same-agent-model","model_patch":"diff --git ..."}
```

Preflight without harness reports:

```bash
python3 scripts/prepare_real_repo_issue_gate.py \
  --dataset-name princeton-nlp/SWE-bench_Verified \
  --subset-label verified-mini-50 \
  --instances-jsonl output/private-swebench/verified-mini-50-instances.jsonl \
  --base-predictions output/private-swebench/base-agent.predictions.jsonl \
  --planner-predictions output/private-swebench/tml-planner.predictions.jsonl \
  --output benchmarks/real-repo-issue-gate-preflight.json
```

Freeze the public-safe Verified Mini manifest:

```bash
python3 scripts/fetch_swebench_verified_mini_manifest.py
```

This writes
`examples/evaluation/swebench-verified-mini-public-manifest-2026-06-11.jsonl`
and a report under `benchmarks/`. The manifest keeps only public generation
fields such as `repo`, `instance_id`, `base_commit`, `problem_statement`,
`hints_text`, `created_at`, `version`, and `environment_setup_commit`. It omits
`patch`, `test_patch`, `FAIL_TO_PASS`, and `PASS_TO_PASS`.

Check local harness readiness:

```bash
python3 scripts/preflight_real_repo_issue_gate_env.py
```

The checked local `2026-06-11` preflight is blocked:

- free disk is `6.10 GiB`, below the configured `10.00 GiB` floor,
- `docker` is not installed,
- the Python `swebench` module is not importable,
- the public manifest exists,
- base/planner prediction JSONL files do not exist yet.

This is not a failure of TML. It says the official harness run belongs on a
Docker-capable machine with enough disk and generated prediction files.

Run the official harness for both prediction files:

```bash
python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --split test \
  --predictions_path output/private-swebench/base-agent.predictions.jsonl \
  --max_workers 1 \
  --timeout 1800 \
  --run_id tml_base_verified_mini

python -m swebench.harness.run_evaluation \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --split test \
  --predictions_path output/private-swebench/tml-planner.predictions.jsonl \
  --max_workers 1 \
  --timeout 1800 \
  --run_id tml_planner_verified_mini
```

On macOS ARM, the official SWE-bench README notes that `--namespace ''` should
be added so Docker images build locally instead of pulling Linux images.

Summarize after both official reports exist:

```bash
python3 scripts/prepare_real_repo_issue_gate.py \
  --dataset-name princeton-nlp/SWE-bench_Verified \
  --subset-label verified-mini-50 \
  --instances-jsonl output/private-swebench/verified-mini-50-instances.jsonl \
  --base-predictions output/private-swebench/base-agent.predictions.jsonl \
  --planner-predictions output/private-swebench/tml-planner.predictions.jsonl \
  --base-report evaluation_results/tml_base_verified_mini \
  --planner-report evaluation_results/tml_planner_verified_mini \
  --output benchmarks/real-repo-issue-gate-verified-mini.json
```

## Checked Fixture

The repository includes a synthetic two-row fixture under
`examples/evaluation/real-repo-gate/`. It exists only to prove that the script
validates same-instance coverage, parses reports, computes planner delta, and
refuses a performance claim when rows are synthetic.

```bash
python3 scripts/prepare_real_repo_issue_gate.py \
  --dataset-name fixture/SWE-bench-style \
  --subset-label synthetic-fixture \
  --instances-jsonl examples/evaluation/real-repo-gate/fixture-instances.jsonl \
  --base-predictions examples/evaluation/real-repo-gate/base-predictions.fixture.jsonl \
  --planner-predictions examples/evaluation/real-repo-gate/planner-predictions.fixture.jsonl \
  --base-report examples/evaluation/real-repo-gate/base-results.fixture.json \
  --planner-report examples/evaluation/real-repo-gate/planner-results.fixture.json \
  --allow-synthetic-fixture \
  --output benchmarks/real-repo-issue-gate-fixture-2026-06-11.json
```

Expected claim status:

```text
synthetic_fixture_not_performance_evidence
```

## Current Status

As of this artifact, TML has not yet run the real-repo gate. The public-safe
Verified Mini manifest is frozen, and this local machine has a blocked harness
preflight. The proven result remains narrower: the anticipatory planner reaches
60/60 on the local Python stdlib executable suite. That is useful planner
evidence, but it does not prove SWE-bench issue-resolution lift.

The next honest decision is simple:

- If the planner beats base on the same 50 real issues, continue to Lite.
- If it ties or loses, stop broad claims and mine failures for better planner
  memory or adapter-training episodes.
- If Lite or Verified is positive under the same contract, then the paper can
  claim real-repo issue-resolution lift.
