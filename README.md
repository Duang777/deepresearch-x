# DeepResearch-X

一个工程化的深度研究 Agent 系统，专注于证据链追踪、分层记忆、可降级架构与可量化评测。  
_A production-oriented deep research agent focused on traceability, layered memory, graceful fallback, and measurable benchmarking._

## Badges

**Core Stack**
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.116-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)

**Quality**
[![CI](https://github.com/Duang777/deepresearch-x/actions/workflows/ci.yml/badge.svg)](https://github.com/Duang777/deepresearch-x/actions/workflows/ci.yml)
[![Memory](https://img.shields.io/badge/Memory-SQLite%20%7C%20OpenViking-0A7EA4)](docs/OPENVIKING_INTEGRATION.md)

**Ecosystem**
[![Docs](https://img.shields.io/badge/Docs-Index-1f6feb?logo=readthedocs&logoColor=white)](#docs-index)
[![Stars](https://img.shields.io/github/stars/Duang777/deepresearch-x?style=social)](https://github.com/Duang777/deepresearch-x/stargazers)

## Quick Links

[![Docs Index](https://img.shields.io/badge/Docs-Index-1f6feb?logo=readthedocs&logoColor=white)](#docs-index)
[![Architecture](https://img.shields.io/badge/Architecture-Overview-0b7285?logo=diagramsdotnet&logoColor=white)](#系统架构--architecture)
[![Quick Start](https://img.shields.io/badge/Start-Quick%20Start-2f9e44?logo=rocket&logoColor=white)](#快速开始--quick-start)
[![API](https://img.shields.io/badge/API-Overview-f08c00?logo=fastapi&logoColor=white)](#api-概览--api-overview)
[![Benchmark](https://img.shields.io/badge/Benchmark-Run%20Scripts-7b2cbf?logo=speedtest&logoColor=white)](#运行与评测--operations--benchmarking)
[![CI Workflow](https://img.shields.io/badge/CI-Workflow-2ea44f?logo=githubactions&logoColor=white)](https://github.com/Duang777/deepresearch-x/actions/workflows/ci.yml)

## Visual Preview

![Architecture Cover](docs/assets/architecture-cover.svg)

**Runtime Preview**

![Runtime Preview](docs/assets/runtime-preview.png)

## Docs Index

| 文档 | 说明 | English |
|---|---|---|
| [README.md](README.md) | 项目总览、架构、API、运行与评测 | Project overview, architecture, API, operations |
| [docs/OPENVIKING_INTEGRATION.md](docs/OPENVIKING_INTEGRATION.md) | OpenViking 集成与运维手册 | OpenViking integration and operations guide |
| [docs/INTERVIEW_PLAYBOOK.md](docs/INTERVIEW_PLAYBOOK.md) | 开发运行与演示流程手册 | Developer runbook and demo procedure |

## 核心特性 | Core Capabilities

| 能力 | 说明 | English |
|---|---|---|
| 多轮研究流水线 | `retrieve -> claim extraction -> evidence alignment -> report` | Multi-loop orchestration pipeline |
| 证据链追踪 | 结论绑定来源 URL、相关度分数、证据片段 | Claim-to-source traceability |
| 富文本抓取增强 | `direct fetch` 失败时回退 `r.jina.ai` | Full-text enrichment with fallback |
| 分层记忆作用域 | `session` / `global` / `hybrid` | Layered memory scopes |
| 异步记忆提取 | 去重、冲突标注、置信度更新 | Async memory extraction and reconciliation |
| 记忆注入预算 | `memory_budget_tokens` 限制上下文体积 | Budgeted memory injection |
| 后端可插拔 | 默认 SQLite，支持 OpenViking 并自动降级 | Pluggable memory backends with graceful fallback |
| 量化评测 | Baseline / DeerFlow-style / OpenViking 对比 | Quantitative benchmarking and comparison |

## 系统架构 | Architecture

```mermaid
flowchart LR
    API["FastAPI API Layer"] --> PIPE["ResearchPipeline"]
    PIPE --> SEARCH["Search Adapter<br/>duckduckgo/mock"]
    PIPE --> READER["Reader Adapter<br/>direct + r.jina.ai fallback"]
    PIPE --> LLM["LLM Adapter<br/>heuristic/openai"]
    PIPE --> MEM["MemoryService"]
    MEM --> SQL["SQLiteStore (default)"]
    MEM --> OV["OpenViking Adapter (optional)"]
    PIPE --> CKPT["Session Checkpoint Store"]
    PIPE --> OUT["Structured Result + Metrics"]
```

设计原则：
- 单一编排入口：`ResearchPipeline`
- 协议化边界：`adapter + protocol`
- 可降级优先：外部依赖异常时保持主链路可用

_Design principles: single orchestration entrypoint, protocol-driven boundaries, and graceful degradation by default._

## 快速开始 | Quick Start

```powershell
cd D:/DUAN/APP/deepresearch-x
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn deepresearch_x.app:app --reload
```

访问地址：
- [http://127.0.0.1:8000](http://127.0.0.1:8000)

## 配置说明 | Configuration

`.env` 关键配置：

| 分类 | 配置项 | 默认值 |
|---|---|---|
| Provider | `SEARCH_PROVIDER` | `duckduckgo` |
| Provider | `LLM_PROVIDER` | `heuristic` |
| Provider | `OPENAI_MODEL` | `gpt-4.1-mini` |
| Reader | `ENABLE_PAGE_READER` | `true` |
| Reader | `MAX_PAGE_FETCH_PER_LOOP` | `3` |
| Reader | `MAX_PAGE_CHARS` | `12000` |
| Reader | `READER_TIMEOUT_SECONDS` | `8` |
| Cost | `CHEAP_MODEL_COST_PER_1K` | `0.0006` |
| Cost | `EXPENSIVE_MODEL_COST_PER_1K` | `0.005` |
| Memory | `ENABLE_MEMORY` | `true` |
| Memory | `MEMORY_BACKEND` | `sqlite` |
| Memory | `MEMORY_SQLITE_PATH` | `outputs/memory_store.db` |
| Memory | `MEMORY_BUDGET_TOKENS` | `280` |
| Memory | `MEMORY_SCOPE` | `hybrid` |
| Memory | `MEMORY_QUEUE_WAIT_MS` | `220` |
| Fallback | `ALLOW_SEARCH_MOCK_FALLBACK` | `false` |
| Fallback | `ALLOW_LLM_HEURISTIC_FALLBACK` | `false` |
| OpenViking | `OPENVIKING_BASE_URL` | `http://127.0.0.1:8100` |
| OpenViking | `OPENVIKING_TIMEOUT_SECONDS` | `0.8` |

## API 概览 | API Overview

### POST `/api/research`

请求示例：
```json
{
  "topic": "multi-agent deep research systems",
  "loops": 3,
  "top_k": 6,
  "session_id": "prod-session-001",
  "use_memory": true,
  "memory_backend": "sqlite",
  "memory_budget_tokens": 280,
  "memory_scope": "hybrid"
}
```

响应关键字段：
- `report_markdown`
- `final_claims`
- `sources`
- `metrics`
- `session_id`
- `memory_used_count`
- `memory_write_count`
- `memory_conflict_count`
- `degraded_mode`
- `degraded_reasons`

### GET `/api/sessions/{session_id}`
- 返回会话 checkpoint 历史和指标快照。

### GET `/api/memory/{session_id}`
- 返回会话记忆条目，支持 `memory_scope` 与 `memory_backend` 参数。

## 运行与评测 | Operations & Benchmarking

### 启动服务
```powershell
.venv/Scripts/activate
uvicorn deepresearch_x.app:app --reload
```

### 批量运行
```powershell
.venv/Scripts/activate
python scripts/run_benchmark.py --topics-file examples/benchmark_topics.jsonl --loops 3 --top-k 6 --output outputs/benchmark_results.jsonl
```

### 可复现离线模式
```powershell
$env:SEARCH_PROVIDER="mock"
python scripts/run_benchmark.py --topics-file examples/benchmark_topics.jsonl --loops 1 --top-k 3 --limit 3 --disable-memory --output outputs/mock_benchmark.jsonl
```

### 三路对比（Baseline / DeerFlow-style / OpenViking）
```powershell
$env:SEARCH_PROVIDER="mock"
python scripts/compare_benchmark.py --topics-file examples/benchmark_topics.jsonl --loops 2 --top-k 4 --limit 4 --output-dir outputs/compare
```

输出文件：
- `outputs/compare/memory_compare_results.jsonl`
- `outputs/compare/memory_ab_report.md`

## 质量保障 | Quality Gates

运行测试：
```powershell
.venv/Scripts/activate
python -m pytest -q
```

当前覆盖范围：
- pipeline 主流程回归
- 记忆去重与冲突标注
- 记忆注入预算限制
- OpenViking fallback 契约
- 同一会话多次运行一致性

## 项目结构 | Project Layout

```text
deepresearch-x/
  deepresearch_x/
    app.py
    config.py
    models.py
    pipeline.py
    memory/
      store.py
      service.py
      openviking.py
    adapters/
      search.py
      reader.py
      llm.py
    templates/
      index.html
    static/
      app.js
      styles.css
  scripts/
    run_benchmark.py
    compare_benchmark.py
  docs/
    OPENVIKING_INTEGRATION.md
    INTERVIEW_PLAYBOOK.md
    assets/
      architecture-cover.svg
      runtime-preview.png
  tests/
    test_pipeline.py
    test_memory.py
```

## 可靠性策略 | Reliability

- 搜索不可用：自动回退 `MockSearchProvider`
- 页面抓取失败：自动回退 `r.jina.ai` Reader
- OpenViking 不可达：自动回退 SQLite（含失败冷却）
- 保持结构化输出，避免单点失败导致流程中断

_Failure handling is built-in to keep the pipeline operational under partial outages._

## Roadmap

- 引入任务级异步编排队列
- 增加研究质量评估模块（coverage/novelty/citation precision）
- 接入 CI 持续基准对比与质量门禁
- 增加可观测性导出（Prometheus/OpenTelemetry）
