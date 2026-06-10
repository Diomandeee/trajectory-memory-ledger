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
