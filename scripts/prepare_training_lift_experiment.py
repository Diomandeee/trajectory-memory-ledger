#!/usr/bin/env python3
"""
Prepare a controlled training-lift experiment from a private trajectory store.

The script writes private train/valid JSONL files under an ignored output
directory and writes a public-safe aggregate report. It does not train a model
and it does not claim lift. The report is the preflight gate: data splits must
exist, held-out leakage checks must pass, and the requested remote trainer must
be reachable before adapter evaluation can be cited.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import statistics
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONDITIONS = ("random", "reward_selected", "full_ledger")
SYSTEM_PROMPT = (
    "You are an expert software engineering assistant. Given a task, plan the "
    "optimal sequence of tool uses to accomplish it efficiently. Prefer reading "
    "before editing, keeping changes scoped, and verifying after changes."
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password)\s*=\s*['\"]?[^'\"\s]+"),
    re.compile(r"\bghp_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]+(?:_[A-Za-z0-9_]+)+\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)?\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b"),
)


@dataclass(frozen=True)
class Record:
    row_index: int
    record_id: str
    reward: float
    advantage: float
    domain: str
    prompt: str
    plan: str
    total_tools: int


def main() -> int:
    args = parse_args()
    heldout_terms = load_heldout_terms(args.heldout_public_tasks, args.heldout_task_specs)
    loaded = load_records(args.trajectory_store, heldout_terms, args.min_tools)
    if len(loaded["eligible"]) < args.sample_size:
        raise SystemExit(
            f"need at least {args.sample_size} eligible records, found {len(loaded['eligible'])}"
        )

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    condition_reports = {}
    for condition, selected in select_conditions(loaded["eligible"], args.sample_size, args.seed).items():
        condition_dir = output_dir / condition
        condition_dir.mkdir(parents=True, exist_ok=True)
        condition_reports[condition] = write_condition_split(
            condition=condition,
            records=selected,
            condition_dir=condition_dir,
            valid_ratio=args.valid_ratio,
            seed=args.seed,
        )

    remote_preflight = probe_remote(args.remote_host, args.remote_timeout_s) if args.probe_remote else {
        "status": "not_requested",
        "remote_host": args.remote_host,
    }
    status = derive_status(condition_reports, remote_preflight, args.probe_remote)

    report = {
        "schema": "trajectory-memory-ledger.training_lift_preflight.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "experiment_status": status,
        "private_trajectory_store": args.trajectory_store_label,
        "private_trajectory_store_path_recorded": False,
        "private_outputs_written": True,
        "private_output_dir": str(output_dir),
        "heldout_task_refs": {
            "public_tasks": str(args.heldout_public_tasks),
            "task_specs": str(args.heldout_task_specs),
        },
        "selection": {
            "sample_size_per_condition": args.sample_size,
            "seed": args.seed,
            "min_tools": args.min_tools,
            "valid_ratio": args.valid_ratio,
            "eligible_records": len(loaded["eligible"]),
            "excluded": loaded["excluded"],
            "conditions": condition_reports,
        },
        "remote_preflight": remote_preflight,
        "next_adapter_commands": build_next_commands(output_dir, args.base_model),
        "claim_boundary": (
            "This preflight prepares controlled random/reward_selected/full_ledger training splits "
            "and checks trainer reachability. It does not train adapters, generate post-training "
            "candidates, or prove reward-selected task-completion lift."
        ),
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trajectory-store", type=Path, required=True)
    parser.add_argument("--trajectory-store-label", default="private-local-trajectory-store")
    parser.add_argument("--heldout-public-tasks", type=Path, required=True)
    parser.add_argument("--heldout-task-specs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output/private-training-lift-2026-06-08"))
    parser.add_argument("--report", type=Path, default=Path("benchmarks/training-lift-preflight-2026-06-08.json"))
    parser.add_argument("--sample-size", type=int, default=96)
    parser.add_argument("--valid-ratio", type=float, default=0.1)
    parser.add_argument("--min-tools", type=int, default=2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--base-model", default="mlx-community/gemma-3-1b-it-4bit")
    parser.add_argument("--remote-host", default="mac5")
    parser.add_argument("--remote-timeout-s", type=int, default=3)
    parser.add_argument("--probe-remote", action="store_true")
    return parser.parse_args()


def load_heldout_terms(public_tasks: Path, task_specs: Path) -> set[str]:
    terms: set[str] = set()
    for path in (public_tasks, task_specs):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                task_id = str(row.get("task_id", "")).strip()
                if task_id:
                    terms.add(task_id.lower())
                    terms.update(part for part in re.split(r"[_\W]+", task_id.lower()) if len(part) >= 5)
                prompt = str(row.get("public_prompt", ""))
                for token in re.findall(r"[A-Za-z_][A-Za-z0-9_]{4,}", prompt):
                    if token not in {"Return", "Implement", "ValueError", "source"}:
                        terms.add(token.lower())
    return terms


def load_records(path: Path, heldout_terms: set[str], min_tools: int) -> dict[str, Any]:
    rewards_for_default_advantage = []
    raw_rows = []
    excluded = {
        "json_decode": 0,
        "missing_reward": 0,
        "too_few_tools": 0,
        "missing_prompt": 0,
        "empty_plan": 0,
        "heldout_leakage_risk": 0,
    }
    with path.open(encoding="utf-8") as handle:
        for row_index, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                excluded["json_decode"] += 1
                continue
            reward = (((raw.get("outcome") or {}).get("reward_score")))
            if reward is None:
                excluded["missing_reward"] += 1
                continue
            try:
                reward_float = float(reward)
            except (TypeError, ValueError):
                excluded["missing_reward"] += 1
                continue
            raw_rows.append((row_index, raw, reward_float))
            rewards_for_default_advantage.append(reward_float)

    global_mean = statistics.mean(rewards_for_default_advantage) if rewards_for_default_advantage else 0.0
    eligible: list[Record] = []
    for row_index, raw, reward in raw_rows:
        trajectory = raw.get("trajectory") or {}
        events = [event for event in (trajectory.get("events") or []) if not event.get("placeholder")]
        total_tools = int(trajectory.get("observed_event_count") or trajectory.get("total_tools") or len(events) or 0)
        if max(total_tools, len(events)) < min_tools:
            excluded["too_few_tools"] += 1
            continue
        prompt = clean_text(str((raw.get("context") or {}).get("prompt_text") or trajectory.get("prompt") or ""))
        if len(prompt) < 10:
            excluded["missing_prompt"] += 1
            continue
        plan = clean_text(trajectory_to_plan(raw))
        if len(plan) < 20:
            excluded["empty_plan"] += 1
            continue
        leakage_text = f"{prompt} {plan}".lower()
        if any(term and term in leakage_text for term in heldout_terms):
            excluded["heldout_leakage_risk"] += 1
            continue
        outcome = raw.get("outcome") or {}
        advantage = outcome.get("advantage")
        if advantage is None:
            advantage = reward - global_mean
        eligible.append(
            Record(
                row_index=row_index,
                record_id=str(raw.get("id") or f"row-{row_index}"),
                reward=reward,
                advantage=float(advantage),
                domain=str(raw.get("domain") or (raw.get("skill") or {}).get("domain") or "_global"),
                prompt=prompt[:4000],
                plan=plan[:4000],
                total_tools=total_tools,
            )
        )

    return {"eligible": eligible, "excluded": excluded}


def clean_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def trajectory_to_plan(record: dict[str, Any]) -> str:
    trajectory = record.get("trajectory") or {}
    events = [event for event in (trajectory.get("events") or []) if not event.get("placeholder")]
    parts = []
    for idx, event in enumerate(events[:24], 1):
        tool = str(event.get("tool_name") or "?")
        params = event.get("key_params") or {}
        success = event.get("success")
        status = "ok" if success is True else ("fail" if success is False else "?")
        desc = describe_event(tool, params)
        parts.append(f"{idx}. [{status}] {desc}")
    total = trajectory.get("total_tools") or len(events)
    successes = trajectory.get("successes")
    reward = (record.get("outcome") or {}).get("reward_score")
    parts.append(f"Result: {successes}/{total} tools succeeded, reward={reward}")
    return "\n".join(parts)


def describe_event(tool: str, params: dict[str, Any]) -> str:
    if tool in {"Read", "Edit", "Write"} and params.get("file_path"):
        return f"{tool} {short_path(str(params['file_path']))}"
    if tool == "Bash" and params.get("command"):
        return f"Bash: {str(params['command'])[:120]}"
    if tool in {"Grep", "Glob"} and params.get("pattern"):
        return f"{tool}: {str(params['pattern'])[:80]}"
    if tool == "Task" and params.get("description"):
        return f"Task: {str(params['description'])[:100]}"
    return tool


def short_path(path: str) -> str:
    parts = path.split("/")
    return "/".join([".."] + parts[-2:]) if len(parts) > 3 else path


def select_conditions(records: list[Record], sample_size: int, seed: int) -> dict[str, list[Record]]:
    rng = random.Random(seed)
    sorted_by_reward = sorted(records, key=lambda record: (record.reward, record.advantage), reverse=True)
    sorted_by_distribution = sorted(records, key=lambda record: record.reward)
    if len(sorted_by_distribution) == sample_size:
        full = sorted_by_distribution
    else:
        full = [
            sorted_by_distribution[round(idx * (len(sorted_by_distribution) - 1) / (sample_size - 1))]
            for idx in range(sample_size)
        ]
    return {
        "random": rng.sample(records, sample_size),
        "reward_selected": sorted_by_reward[:sample_size],
        "full_ledger": full,
    }


def write_condition_split(
    condition: str,
    records: list[Record],
    condition_dir: Path,
    valid_ratio: float,
    seed: int,
) -> dict[str, Any]:
    rows = [
        {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": record.prompt},
                {"role": "assistant", "content": record.plan},
            ]
        }
        for record in records
    ]
    rng = random.Random(f"{seed}:{condition}")
    rng.shuffle(rows)
    split_idx = max(1, min(len(rows) - 1, int(len(rows) * (1.0 - valid_ratio))))
    train_rows = rows[:split_idx]
    valid_rows = rows[split_idx:]
    train_path = condition_dir / "train.jsonl"
    valid_path = condition_dir / "valid.jsonl"
    write_jsonl(train_path, train_rows)
    write_jsonl(valid_path, valid_rows)
    record_ids = [record.record_id for record in records]
    manifest = {
        "condition": condition,
        "record_count": len(records),
        "record_id_hash": sha256_text("\n".join(record_ids)),
        "train_sha256": sha256_file(train_path),
        "valid_sha256": sha256_file(valid_path),
        "reward": summarize([record.reward for record in records]),
        "advantage": summarize([record.advantage for record in records]),
        "total_tools": summarize([float(record.total_tools) for record in records]),
        "domain_count": len({record.domain for record in records}),
        "domain_histogram_hash": sha256_text(json.dumps(top_counts(record.domain for record in records), sort_keys=True)),
    }
    (condition_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        **manifest,
        "train_rows": len(train_rows),
        "valid_rows": len(valid_rows),
        "private_files": {
            "train": str(train_path),
            "valid": str(valid_path),
            "manifest": str(condition_dir / "manifest.json"),
        },
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=False) + "\n")


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 4),
        "mean": round(statistics.mean(values), 4),
        "max": round(max(values), 4),
    }


def top_counts(values: Any, limit: int = 8) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[str(value)] = counts.get(str(value), 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def probe_remote(host: str, timeout_s: int) -> dict[str, Any]:
    command = ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout_s}", host, "echo ok"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s + 2)
    except subprocess.TimeoutExpired:
        return {
            "status": "ssh_timeout",
            "remote_host": host,
            "timeout_s": timeout_s,
            "training_reachable": False,
        }
    if result.returncode != 0:
        return {
            "status": "ssh_failed",
            "remote_host": host,
            "training_reachable": False,
            "exit_code": result.returncode,
            "stderr_preview": sanitize_remote_text(result.stderr.strip())[:500],
        }
    mlx_result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={timeout_s}", host, "python3 -c 'import mlx, mlx_lm; print(\"mlx_ready\")'"],
        capture_output=True,
        text=True,
        timeout=timeout_s + 5,
    )
    return {
        "status": "ready" if mlx_result.returncode == 0 else "missing_mlx_or_mlx_lm",
        "remote_host": host,
        "training_reachable": True,
        "mlx_ready": mlx_result.returncode == 0,
        "stdout_preview": mlx_result.stdout.strip()[:500],
        "stderr_preview": sanitize_remote_text(mlx_result.stderr.strip())[:500],
    }


def sanitize_remote_text(text: str) -> str:
    return re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[REDACTED_IP]", text)


def derive_status(condition_reports: dict[str, Any], remote_preflight: dict[str, Any], probe_remote_requested: bool) -> str:
    if set(condition_reports) != set(CONDITIONS):
        return "incomplete_condition_exports"
    if not probe_remote_requested:
        return "data_ready_remote_not_checked"
    if remote_preflight.get("status") == "ready":
        return "ready_for_adapter_training"
    return "blocked_remote_training_unreachable"


def build_next_commands(output_dir: Path, base_model: str) -> dict[str, str]:
    commands = {}
    for condition in CONDITIONS:
        condition_dir = output_dir / condition
        commands[condition] = (
            "python3 -m mlx_lm lora "
            f"--model {base_model} "
            f"--data {condition_dir} "
            "--train "
            f"--adapter-path output/private-adapters/{condition} "
            "--iters 500 --batch-size 1 --num-layers 4 --max-seq-length 256 --learning-rate 1e-5"
        )
    return commands


if __name__ == "__main__":
    raise SystemExit(main())
