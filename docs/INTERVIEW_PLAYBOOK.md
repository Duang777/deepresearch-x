# Interview Demo Playbook (10-12 min)

## 1. One-Sentence Positioning
"This is an evidence-first deep research agent with session memory, checkpoint traceability, and measurable A/B evaluation."

## 2. Demo Setup (1 min)
```powershell
cd D:/DUAN/APP/deepresearch-x
.venv/Scripts/activate
$env:SEARCH_PROVIDER="mock"
uvicorn deepresearch_x.app:app --reload
```

## 3. Live Product Walkthrough (4 min)
1. Open UI and run a topic once with `session_id=demo-memory`.
2. Run the same topic again with the same `session_id`.
3. Show metrics increase in `memory_recall_hits`.
4. Mention memory budget control (`memory_budget_tokens`).

## 4. API Traceability (2 min)
```powershell
curl http://127.0.0.1:8000/api/sessions/demo-memory
curl "http://127.0.0.1:8000/api/memory/demo-memory?memory_scope=hybrid&memory_backend=sqlite"
```
What to say:
- "I can inspect run checkpoints and memory facts directly."
- "This makes behavior auditable, not black-box."

## 5. Quantitative Comparison (2-3 min)
```powershell
python scripts/compare_benchmark.py --topics-file examples/benchmark_topics.jsonl --loops 1 --top-k 3 --limit 3 --output-dir outputs/compare
```
Open:
- `outputs/compare/memory_ab_report.md`

What to highlight:
- baseline vs deerflow-style vs openviking
- memory recall, citation coverage, cost/latency trade-offs
- optional OpenViking path with fallback safety

## 6. Architecture Deep Dive (1-2 min)
Key points:
- adapter-first architecture (`search`, `reader`, `llm`, `memory`)
- async memory queue to avoid blocking main request path
- degradation strategy: remote memory unavailable -> local memory still works

## Likely Q&A
- "How do you prevent context explosion?"
- Answer: memory budget + ranked injection.
- "What if external memory service fails?"
- Answer: adapter fallback and cooldown.
- "How is quality measured?"
- Answer: benchmark script + report with confidence, coverage, cost, latency.
