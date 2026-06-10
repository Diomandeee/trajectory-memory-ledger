# Harness Skills Layer

The harness skills layer turns executable benchmark deltas into evidence-bound skill packages. It is the local implementation of the useful parts of SkillDAG, SkillOpt, and MUSE-style memory packaging without making an unsafe claim that a failed adapter should be routed automatically.

The key binary is `skillgraph-evolve`.

```bash
cargo run --bin skillgraph-evolve -- \
  --public-tasks examples/evaluation/executable-public-tasks-python-stdlib-heldout-v1.jsonl \
  --task-specs examples/evaluation/executable-taskset-python-stdlib-heldout-v1.jsonl \
  --baseline-report benchmarks/executable-task-mlx-gemma4-e2b-qat-base-heldout-v1-mac5-2026-06-10.json \
  --comparison-report benchmarks/executable-task-mlx-gemma4-e2b-reward-selected-512x4096-rawpython-heldout-v1-mac5-2026-06-10.json \
  --output-dir examples/skills/python-stdlib-heldout-v1/e2b-reward-selected-vs-base
```

## What It Builds

`skillgraph-evolve` reads:

- public task prompts
- canonical task specs
- one baseline `executable-task-bench` report
- one comparison `executable-task-bench` report

It emits:

- `trajectory-skills.jsonl`: one structured row per extracted skill family
- `skill-graph.json`: typed graph nodes and edges
- `router-index.json`: regression-gated routing index
- `skillgraph-evolution-report.json`: aggregate comparison report
- `packages/<skill_id>/SKILL.md`: human-readable activation boundary
- `packages/<skill_id>/MEMORY.md`: compact task evidence memory
- `packages/<skill_id>/tests.jsonl`: task-level evidence rows
- `packages/<skill_id>/failure_modes.json`: quarantine and diagnostic metadata
- `packages/<skill_id>/skill.json`: full structured package

## SkillDAG Mapping

The graph encodes four edge types:

| Edge | Meaning |
|---|---|
| `depends_on` | Skill evidence belongs to a specific task set |
| `specializes` | Skill applies to a task family such as `path`, `date`, or `parse` |
| `repairs` | Comparison passed a task that the baseline failed |
| `conflicts_with` | Comparison failed a task that the baseline passed |

This is deliberately a harness-side graph, not a model-side promise. The graph records where a trajectory delta helped, where it hurt, and which families need repair before routing.

## SkillOpt Mapping

The optimizer signal is the pass/fail delta:

- `fixed`: baseline failed, comparison passed
- `regressed`: baseline passed, comparison failed
- `preserved_pass`: both passed
- `shared_fail`: both failed

The global promotion gate defaults to:

- `net_pass_delta >= 1`
- `regressions <= 0`

Families with repairs but no local regressions are `proposed` if the global run failed. Families with any regression are `quarantined`. Families with only shared failures are `diagnostic`.

## MUSE-Style Packages

Each package is a portable skill-memory unit:

- `SKILL.md` says when it can apply and when it must not activate.
- `MEMORY.md` summarizes the evidence in task language.
- `tests.jsonl` preserves exact task-level deltas for replay.
- `failure_modes.json` keeps regression and shared-failure boundaries explicit.

The package is useful even when the adapter fails overall. It tells the next run which subskills deserve targeted repair and which ones must be blocked.

## Current 60-Task Result

The first generated package set compares Gemma 4 E2B QAT base against the reward-selected E2B adapter on `python-stdlib-heldout-v1-60`.

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

The positive proposed skill is `python_stdlib_math_trajectory_delta`, because it repaired `py_v1_moving_average` without a math-family regression. It is still not active because the global adapter comparison failed. The router correctly leaves `active_skill_ids` empty.

This means the current large-suite result does not prove downstream TML performance lift. It does prove that the harness can mine a failed run for bounded repair evidence without promoting unsafe behavior.

## Repair Router Test

The next step is to test a proposed skill without adopting the failed adapter globally. `apply_skillgraph_repair_router.py` starts from the base candidate rows and swaps in comparison rows only for repaired task ids from allowed skill statuses.

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

Then materialize and execute the normal hidden-test gate:

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

Checked result:

| Metric | Value |
|---|---:|
| Preserved base rows | 59 |
| Routed repair rows | 1 |
| Routed task | `py_v1_moving_average` |
| E2B base | 50/60 |
| Math repair router | 51/60 |
| Net pass delta | +1 |
| Regressions vs base | 0 |
| Synthetic rows | 0 |

Running `skillgraph-evolve` on base vs the repair-router report promotes `python_stdlib_math_trajectory_delta` and writes active router artifacts under `examples/skills/python-stdlib-heldout-v1/math-repair-router-vs-base/`.

Boundary: this is a real narrow router lift on the 60-task executable gate. It is not a broad claim that the reward-selected adapter should replace the base model.

## Task-Level Repair Router

The stronger repair-map test routes all fixed task ids from the failed adapter while preserving base outputs for every known adapter regression. This uses quarantined family evidence only as task-level repair candidates; it does not activate the quarantined family wholesale.

```bash
python3 scripts/apply_skillgraph_repair_router.py \
  --base-candidates examples/evaluation/executable-candidates-mlx-gemma4-e2b-qat-base-heldout-v1-mac5-2026-06-10.jsonl \
  --comparison-candidates examples/evaluation/executable-candidates-mlx-gemma4-e2b-reward-selected-512x4096-rawpython-heldout-v1-mac5-2026-06-10.jsonl \
  --skills-jsonl examples/skills/python-stdlib-heldout-v1/e2b-reward-selected-vs-base/trajectory-skills.jsonl \
  --allow-status proposed quarantined \
  --no-require-no-skill-regressions \
  --condition skillgraph_task_repair_router \
  --output examples/evaluation/executable-candidates-skillgraph-task-repair-router-heldout-v1-2026-06-10.jsonl \
  --report benchmarks/executable-candidate-generation-skillgraph-task-repair-router-heldout-v1-2026-06-10.json
```

Checked result:

| Metric | Value |
|---|---:|
| Preserved base rows | 55 |
| Routed repair rows | 5 |
| Known adapter regressions preserved from base | 9 |
| E2B base | 50/60 |
| Task repair router | 55/60 |
| Net pass delta | +5 |
| Regressions vs base | 0 |
| Synthetic rows | 0 |
| Promoted repair families | 4 |

The base-vs-router skillgraph promotes `python_stdlib_date_trajectory_delta`, `python_stdlib_math_trajectory_delta`, `python_stdlib_parse_trajectory_delta`, and `python_stdlib_security_trajectory_delta` under `examples/skills/python-stdlib-heldout-v1/task-repair-router-vs-base/`.

Boundary: this is the current strongest 60-task evidence for the harness skills layer. It proves the repair map can improve pass rate when used as a gated router. It still does not prove that the reward-selected adapter should replace the base model globally.
