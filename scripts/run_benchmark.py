from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import List

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from deepresearch_x.config import AppSettings
from deepresearch_x.pipeline import ResearchPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DeepResearch-X on a topic batch.")
    parser.add_argument(
        "--topics-file",
        type=Path,
        required=True,
        help="Path to JSONL file. Each line: {\"topic\": \"...\"}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/benchmark_results.jsonl"),
        help="Output JSONL path for run artifacts.",
    )
    parser.add_argument("--loops", type=int, default=3)
    parser.add_argument("--top-k", type=int, default=6)
    parser.add_argument("--limit", type=int, default=0, help="Optional max topic count.")
    parser.add_argument(
        "--use-memory",
        action="store_true",
        help="Force memory-enabled runs.",
    )
    parser.add_argument(
        "--disable-memory",
        action="store_true",
        help="Force memory-disabled runs.",
    )
    parser.add_argument(
        "--memory-backend",
        type=str,
        default="",
        help="sqlite|openviking. Empty uses app default.",
    )
    parser.add_argument("--memory-budget-tokens", type=int, default=0)
    parser.add_argument("--memory-scope", type=str, default="")
    parser.add_argument(
        "--session-prefix",
        type=str,
        default="bench",
        help="Stable session prefix for cross-run continuity demos.",
    )
    return parser.parse_args()


def load_topics(path: Path, limit: int = 0) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"topics file not found: {path}")
    topics: List[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            topic = str(obj.get("topic", "")).strip()
        except json.JSONDecodeError:
            topic = line
        if topic:
            topics.append(topic)
        if limit and len(topics) >= limit:
            break
    if not topics:
        raise ValueError("No valid topics found in topics file.")
    return topics


def main() -> None:
    args = parse_args()
    forced_use_memory = None
    if args.use_memory:
        forced_use_memory = True
    if args.disable_memory:
        forced_use_memory = False

    settings = AppSettings()
    pipeline = ResearchPipeline.from_settings(settings)

    topics = load_topics(args.topics_file, limit=args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    cost_list: List[float] = []
    latency_list: List[int] = []
    claim_counts: List[int] = []
    fulltext_rates: List[float] = []

    with args.output.open("w", encoding="utf-8") as f:
        for idx, topic in enumerate(topics, start=1):
            result = pipeline.run(
                topic=topic,
                loops=args.loops,
                top_k=args.top_k,
                session_id=f"{args.session_prefix}-{idx}",
                use_memory=forced_use_memory,
                memory_backend=args.memory_backend,
                memory_budget_tokens=args.memory_budget_tokens or None,
                memory_scope=args.memory_scope or None,
            )
            row = {
                "timestamp": datetime.utcnow().isoformat(),
                "topic": topic,
                "run_id": result.run_id,
                "session_id": result.session_id,
                "metrics": result.metrics.model_dump(),
                "memory_used_count": result.memory_used_count,
                "memory_write_count": result.memory_write_count,
                "memory_conflict_count": result.memory_conflict_count,
                "claims": [c.model_dump() for c in result.final_claims],
                "report_markdown": result.report_markdown,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

            metrics = result.metrics
            cost_list.append(metrics.estimated_cost_usd)
            latency_list.append(metrics.total_elapsed_ms)
            claim_counts.append(metrics.claim_count)
            denominator = max(1, metrics.source_count)
            fulltext_rates.append(metrics.fulltext_source_count / denominator)

            print(
                f"[{idx}/{len(topics)}] {topic[:64]} | claims={metrics.claim_count} "
                f"| cost=${metrics.estimated_cost_usd:.4f} | latency={metrics.total_elapsed_ms}ms"
            )

    print("\n=== Benchmark Summary ===")
    print(f"topics: {len(topics)}")
    print(f"avg_claim_count: {mean(claim_counts):.2f}")
    print(f"avg_cost_usd: {mean(cost_list):.4f}")
    print(f"avg_latency_ms: {mean(latency_list):.1f}")
    print(f"avg_fulltext_coverage: {mean(fulltext_rates) * 100:.1f}%")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
