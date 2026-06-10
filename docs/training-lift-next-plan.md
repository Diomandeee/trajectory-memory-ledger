# Next Training-Lift Plan

The first adapter-conditioned executable result was negative: three Gemma 3 1B MLX LoRA adapters all scored 0/6. The Gemma 4 base-model sanity runs clarify the cause. Gemma 4 E2B QAT scored 3/6, and Gemma 4 12B QAT scored 5/6 on the same hidden-test executable task set before any ledger fine-tuning. The next lift experiment should start at that capability tier instead of repeating the weak setup.

## Diagnosis

The failed adapter run should be interpreted as a weak training/generation setup:

- base model: `mlx-community/gemma-3-1b-it-4bit`
- selected rows per condition: 96 total, 86 train / 10 validation
- max sequence length: 256
- generation cap: 1024 tokens
- executable result: `random` 0/6, `reward_selected` 0/6, `full_ledger` 0/6

The stronger local baselines show the held-out executable set is not impossible:

| Model | Condition | Max generation tokens | Passed | Pass rate |
|---|---|---:|---:|---:|
| Gemma 4 E2B QAT | `gemma4_e2b_qat_base` | 2048 | 3/6 | 50.00% |
| Gemma 4 12B QAT | `gemma4_12b_qat_base` | 4096 | 5/6 | 83.33% |

## Next Gate

The next valid downstream-lift claim requires comparing trained models against their own base-model lines on a larger executable task set.

Minimum protocol:

1. Use a Gemma 4 12B-class or stronger base model.
2. Keep base-model candidate generation as a reported control.
3. Train matched `random`, `reward_selected`, and `full_ledger` conditions from the same eligible private pool.
4. Use at least 4096-token training context; prefer 8192 if stable.
5. Use hundreds or thousands of rows per condition, not 86 train rows.
6. Match per-condition token budgets so `full_ledger` is not advantaged only by volume.
7. Keep held-out executable prompts and hidden verifier tests separate.
8. Allow public-only repair checks: syntax, importability, public starter definitions, and public prompt/example consistency. Do not feed hidden verifier failures back into generation.
9. Report candidate-generation failures separately from hidden-test failures.
10. Report executable pass rate, confidence intervals, and per-task failures for every condition.

## Training Scale

Recommended staged runs:

| Stage | Rows per condition | Context | Purpose |
|---|---:|---:|---|
| Smoke | 512 | 4096 | Catch trainer/model incompatibility quickly |
| Main local | 2048 | 4096 or 8192 | First meaningful local lift attempt |
| Cloud proof | 4096+ | 8192+ | Stronger QLoRA/LoRA run if local MLX training cannot handle Gemma 4 12B |

If local MLX adapter training does not support the selected Gemma 4 model cleanly, do not fall back to Gemma 3 1B. Move the training run to a cloud GPU stack and keep Mac5 for generation/evaluation.

## Evaluation Scale

The six-task Python stdlib set is useful as a fast sanity gate, but it is too small for a final lift claim. The next executable set should have at least 50 tasks, and preferably 100+, with:

- deterministic stdlib tasks,
- multiple files where appropriate,
- public prompt/starter split,
- hidden verifier tests,
- no leakage from private training prompts,
- a mix of parsing, collections, graph, state-machine, filesystem-safe, and text-processing tasks.

Success criteria for a real downstream-lift claim:

- `reward_selected` beats `random` on executable pass rate for the same model family.
- The lift remains after public-only repair is held constant across conditions.
- The result is not only validation-loss improvement.
- The report has `synthetic_rows=0`.
- The report records `hidden_tests_sent_to_model=false`.

Until that gate passes, the honest claim remains: Trajectory Memory Ledger can record, score, export, train from, and evaluate coding-agent trajectories, and reward-selected data currently improves validation loss, but downstream task-completion lift is not yet proven.
