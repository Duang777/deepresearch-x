from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from deepresearch_x.config import AppSettings
from deepresearch_x.pipeline import ResearchPipeline
from scripts.run_benchmark import load_topics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare Baseline, DeerFlow-style memory, and OpenViking memory variants."
    )
    parser.add_argument(
        "--topics-file",
        type=Path,
        required=True,
        help="Path to JSONL file. Each line: {\"topic\": \"...\"}",
    )
    parser.add_argument("--loops", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs/compare"),
        help="Directory for JSONL and markdown outputs.",
    )
    parser.add_argument("--memory-budget-tokens", type=int, default=280)
    parser.add_argument("--memory-scope", type=str, default="hybrid")
    parser.add_argument(
        "--skip-openviking",
        action="store_true",
        help="Skip OpenViking variant if you only need local comparison.",
    )
    return parser.parse_args()


def run_variant(
    topics: List[str],
    settings: AppSettings,
    loops: int,
    top_k: int,
    variant_name: str,
    use_memory: bool,
    memory_backend: str,
    memory_budget_tokens: int,
    memory_scope: str,
) -> List[Dict[str, Any]]:
    pipeline = ResearchPipeline.from_settings(settings)
    rows: List[Dict[str, Any]] = []
    session_id = f"{variant_name}-session"

    for idx, topic in enumerate(topics, start=1):
        result = pipeline.run(
            topic=topic,
            loops=loops,
            top_k=top_k,
            session_id=session_id,
            use_memory=use_memory,
            memory_backend=memory_backend,
            memory_budget_tokens=memory_budget_tokens,
            memory_scope=memory_scope,
        )
        confidence_list = [c.confidence for c in result.final_claims]
        citation_rate = (
            mean([1.0 if c.supporting_sources else 0.0 for c in result.final_claims])
            if result.final_claims
            else 0.0
        )
        duplicate_source_rate = max(0.0, 1.0 - (result.metrics.source_count / max(1, loops * top_k)))
        row = {
            "variant": variant_name,
            "topic": topic,
            "run_id": result.run_id,
            "session_id": result.session_id,
            "metrics": result.metrics.model_dump(),
            "avg_claim_confidence": round(mean(confidence_list), 4) if confidence_list else 0.0,
            "citation_coverage": round(citation_rate, 4),
            "duplicate_source_rate": round(duplicate_source_rate, 4),
            "memory_used_count": result.memory_used_count,
            "memory_write_count": result.memory_write_count,
            "memory_conflict_count": result.memory_conflict_count,
        }
        rows.append(row)
        print(
            f"[{variant_name}] [{idx}/{len(topics)}] {topic[:56]} "
            f"| claims={result.metrics.claim_count} "
            f"| mem_hits={result.metrics.memory_recall_hits} "
            f"| cost=${result.metrics.estimated_cost_usd:.4f} "
            f"| latency={result.metrics.total_elapsed_ms}ms"
        )
    return rows


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    if not rows:
        return {
            "avg_claim_count": 0.0,
            "avg_confidence": 0.0,
            "avg_cost_usd": 0.0,
            "avg_latency_ms": 0.0,
            "avg_fulltext_coverage": 0.0,
            "avg_memory_hits": 0.0,
            "avg_memory_writes": 0.0,
            "avg_memory_conflicts": 0.0,
            "avg_duplicate_source_rate": 0.0,
            "avg_citation_coverage": 0.0,
        }

    return {
        "avg_claim_count": mean(r["metrics"]["claim_count"] for r in rows),
        "avg_confidence": mean(r["avg_claim_confidence"] for r in rows),
        "avg_cost_usd": mean(r["metrics"]["estimated_cost_usd"] for r in rows),
        "avg_latency_ms": mean(r["metrics"]["total_elapsed_ms"] for r in rows),
        "avg_fulltext_coverage": mean(
            r["metrics"]["fulltext_source_count"] / max(1, r["metrics"]["source_count"])
            for r in rows
        ),
        "avg_memory_hits": mean(r["metrics"]["memory_recall_hits"] for r in rows),
        "avg_memory_writes": mean(r["memory_write_count"] for r in rows),
        "avg_memory_conflicts": mean(r["memory_conflict_count"] for r in rows),
        "avg_duplicate_source_rate": mean(r["duplicate_source_rate"] for r in rows),
        "avg_citation_coverage": mean(r["citation_coverage"] for r in rows),
    }


def _pct_delta(base: float, current: float) -> float:
    if abs(base) < 1e-9:
        return 0.0
    return ((current - base) / base) * 100.0


def _pct_or_na(base: float, current: float) -> str:
    if abs(base) < 1e-9:
        return "n/a"
    return f"{_pct_delta(base, current):+.1f}%"


def build_summary_markdown(variant_stats: Dict[str, Dict[str, float]], topic_count: int) -> str:
    baseline = variant_stats["baseline"]
    deerflow = variant_stats["deerflow_style"]
    openviking = variant_stats.get("openviking")

    def table_row(name: str, stats: Dict[str, float]) -> str:
        return (
            f"| {name} | {stats['avg_claim_count']:.2f} | {stats['avg_confidence']:.3f} | "
            f"{stats['avg_citation_coverage'] * 100:.1f}% | {stats['avg_fulltext_coverage'] * 100:.1f}% | "
            f"{stats['avg_duplicate_source_rate'] * 100:.1f}% | {stats['avg_memory_hits']:.2f} | "
            f"{stats['avg_memory_writes']:.2f} | ${stats['avg_cost_usd']:.4f} | {stats['avg_latency_ms']:.1f} |"
        )

    rows = [table_row("Baseline (No Memory)", baseline), table_row("DeerFlow-Style (SQLite)", deerflow)]
    if openviking:
        rows.append(table_row("OpenViking Adapter", openviking))

    deerflow_hit_abs = deerflow["avg_memory_hits"] - baseline["avg_memory_hits"]
    deerflow_dup_delta = _pct_delta(
        baseline["avg_duplicate_source_rate"],
        deerflow["avg_duplicate_source_rate"],
    )
    deerflow_citation_delta = _pct_delta(
        baseline["avg_citation_coverage"],
        deerflow["avg_citation_coverage"],
    )

    ov_text = ""
    if openviking:
        ov_hit_abs = openviking["avg_memory_hits"] - baseline["avg_memory_hits"]
        ov_text = (
            f"- OpenViking adapter: memory recall delta `{ov_hit_abs:+.2f} hits` ({_pct_or_na(baseline['avg_memory_hits'], openviking['avg_memory_hits'])}), "
            f"latency delta `{openviking['avg_latency_ms'] - baseline['avg_latency_ms']:+.1f} ms` ({_pct_or_na(baseline['avg_latency_ms'], openviking['avg_latency_ms'])}) vs baseline.\n"
            "- If OpenViking service is unavailable, adapter auto-falls back to local SQLite.\n"
        )

    return f"""# DeepResearch-X Memory A/B Report

Generated at: {datetime.utcnow().isoformat()} UTC  
Topics evaluated: {topic_count}

## Variant Matrix

| Variant | Avg Claim Count | Avg Confidence | Citation Coverage | Full-Text Coverage | Duplicate Retrieval Rate | Memory Recall Hits | Memory Writes | Avg Cost (USD) | Avg Latency (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## Key Deltas vs Baseline
- DeerFlow-style memory: memory recall delta `{deerflow_hit_abs:+.2f} hits` ({_pct_or_na(baseline['avg_memory_hits'], deerflow['avg_memory_hits'])}).
- DeerFlow-style memory: duplicate retrieval rate delta `{deerflow_dup_delta:+.1f}%`.
- DeerFlow-style memory: citation coverage delta `{deerflow_citation_delta:+.1f}%`.
{ov_text}
## Interview Talking Points
1. Memory is not only enabled, but budgeted (`memory_budget_tokens`) to control prompt cost growth.
2. Session checkpoints make multi-turn research reproducible and auditable.
3. OpenViking is integrated via adapter boundary, so AGPL surface stays optional while preserving extensibility.
"""


def main() -> None:
    args = parse_args()
    topics = load_topics(args.topics_file, limit=args.limit)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    base_settings = AppSettings()
    baseline_settings = replace(base_settings, enable_page_reader=False)
    deerflow_settings = replace(base_settings, enable_page_reader=True)
    openviking_settings = replace(base_settings, enable_page_reader=True)

    baseline_rows = run_variant(
        topics=topics,
        settings=baseline_settings,
        loops=args.loops,
        top_k=args.top_k,
        variant_name="baseline",
        use_memory=False,
        memory_backend="sqlite",
        memory_budget_tokens=args.memory_budget_tokens,
        memory_scope=args.memory_scope,
    )

    deerflow_rows = run_variant(
        topics=topics,
        settings=deerflow_settings,
        loops=args.loops,
        top_k=args.top_k,
        variant_name="deerflow_style",
        use_memory=True,
        memory_backend="sqlite",
        memory_budget_tokens=args.memory_budget_tokens,
        memory_scope=args.memory_scope,
    )

    variant_rows: Dict[str, List[Dict[str, Any]]] = {
        "baseline": baseline_rows,
        "deerflow_style": deerflow_rows,
    }
    if not args.skip_openviking:
        openviking_rows = run_variant(
            topics=topics,
            settings=openviking_settings,
            loops=args.loops,
            top_k=args.top_k,
            variant_name="openviking",
            use_memory=True,
            memory_backend="openviking",
            memory_budget_tokens=args.memory_budget_tokens,
            memory_scope=args.memory_scope,
        )
        variant_rows["openviking"] = openviking_rows

    compare_jsonl = args.output_dir / "memory_compare_results.jsonl"
    with compare_jsonl.open("w", encoding="utf-8") as f:
        for variant_name, rows in variant_rows.items():
            for row in rows:
                payload = {"variant": variant_name, **row}
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    stats = {name: aggregate(rows) for name, rows in variant_rows.items()}
    summary_text = build_summary_markdown(variant_stats=stats, topic_count=len(topics))
    summary_md = args.output_dir / "memory_ab_report.md"
    summary_md.write_text(summary_text, encoding="utf-8")

    print("\n=== Memory A/B Comparison Completed ===")
    print(f"results: {compare_jsonl}")
    print(f"summary: {summary_md}")


if __name__ == "__main__":
    main()
