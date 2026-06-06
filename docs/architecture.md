# Architecture

Trajectory Memory Ledger separates durable ingestion from research and training.

## Rust Runtime

`trajectory-ledgerd` owns the live path:

1. Read `events-YYYY-MM-DD.jsonl`
2. Skip envelopes already covered by the date-scoped cursor
3. Group gateway envelopes by `flow_id`
4. Build one trajectory card per completed flow
5. Normalize the card to schema v2
6. Score it with the six-signal reward model
7. Append to the JSONL ledger under an exclusive file lock
8. Write cursor and Prometheus metrics atomically

The cursor is intentionally scoped by date:

```json
{"date": "2026-06-03", "seq": 42}
```

Daily event files may restart `seq` at 1. A global monotonic cursor would silently drop events after a date rollover.

## Research Layer

Python and notebooks should consume the normalized ledger for:

- batch extraction
- SFT export
- train/validation splits
- reward ablations
- selection experiments
- model training and evaluation
- paper metrics

This split keeps the operational collector reliable while leaving research tooling flexible.

## Evaluation Tools

The repository includes two Rust evaluation binaries:

- `daemon-bench`: generates synthetic gateway events and measures ingestion throughput, append latency, duplicate skipping, cursor rollover, and concurrent append safety.
- `agent-eval`: aggregates held-out tool-plan generations by condition. It is intended for downstream experiments comparing random trajectory selection, reward-selected trajectory selection, and the full normalized ledger export.

The synthetic `agent-eval` example in `examples/evaluation/` verifies the protocol shape. It is not downstream model-performance evidence.
