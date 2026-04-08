# Developer Runbook and Demo Procedure

本文档定义 DeepResearch-X 在开发环境下的标准运行流程、演示流程、验收清单与排障手册。

## 1. 使用场景

适用对象：
- 开发者本地联调
- 功能验收演示
- 版本发布前回归验证

主要目标：
- 快速启动服务
- 验证核心 API 可用
- 生成可复现 benchmark 产物

## 2. 前置条件

- Python 3.10+
- 已安装依赖：`pip install -r requirements.txt`
- `.env` 已存在（可由 `.env.example` 复制）

推荐：
- 使用独立虚拟环境 `.venv`
- 演示时设置 `SEARCH_PROVIDER=mock` 获得可复现输出

## 3. 本地启动流程

```powershell
cd D:/DUAN/APP/deepresearch-x
.venv/Scripts/activate
uvicorn deepresearch_x.app:app --reload
```

服务地址：
- `http://127.0.0.1:8000`

健康检查：
- `GET /health` 返回 `{"status":"ok"}`

## 4. API 验收流程

### 4.1 执行研究请求

请求：
```json
{
  "topic": "memory enhanced deep research systems",
  "loops": 1,
  "top_k": 3,
  "session_id": "runbook-session",
  "use_memory": true,
  "memory_backend": "sqlite",
  "memory_budget_tokens": 256,
  "memory_scope": "hybrid"
}
```

验收点：
- 返回状态码 `200`
- 返回包含 `session_id`
- 返回 `metrics.memory_recall_hits`
- 返回 `memory_write_count`

### 4.2 会话与记忆查询

```powershell
curl http://127.0.0.1:8000/api/sessions/runbook-session
curl "http://127.0.0.1:8000/api/memory/runbook-session?memory_scope=hybrid&memory_backend=sqlite"
```

验收点：
- 会话 checkpoint 数量 > 0
- 记忆条目数量 > 0

## 5. 基准评测流程

### 5.1 单次批量运行
```powershell
$env:SEARCH_PROVIDER="mock"
python scripts/run_benchmark.py --topics-file examples/benchmark_topics.jsonl --loops 1 --top-k 3 --limit 3 --output outputs/runbook_benchmark.jsonl
```

### 5.2 三路对比
```powershell
$env:SEARCH_PROVIDER="mock"
python scripts/compare_benchmark.py --topics-file examples/benchmark_topics.jsonl --loops 1 --top-k 3 --limit 3 --output-dir outputs/runbook_compare
```

产物：
- `outputs/runbook_compare/memory_compare_results.jsonl`
- `outputs/runbook_compare/memory_ab_report.md`

## 6. OpenViking 模式验证

### 6.1 远程可用场景
- 设置：`MEMORY_BACKEND=openviking`
- 执行研究请求
- 检查返回成功及指标完整

### 6.2 远程不可用场景
- 停止 OpenViking 服务
- 重复请求
- 验证服务仍返回 `200` 且核心结果可用（SQLite 回退）

## 7. 发布前检查清单

提交前建议执行：

```powershell
.venv/Scripts/activate
python -m pytest -q
python scripts/compare_benchmark.py --topics-file examples/benchmark_topics.jsonl --loops 1 --top-k 3 --limit 2 --output-dir outputs/pre_release_compare
```

检查项：
- 单测通过
- API 冒烟通过
- benchmark 产物完整
- README 与 docs 链接可达

## 8. 故障排查

### 8.1 `memory_recall_hits` 长期为 0
- 检查是否复用同一 `session_id`
- 检查 `use_memory` 是否为 `true`
- 检查 `memory_scope` 是否合理（建议 `hybrid`）

### 8.2 OpenViking 模式延迟过高
- 降低 `OPENVIKING_TIMEOUT_SECONDS`
- 使用默认回退策略（SQLite）
- 排查 OpenViking 服务端网络与队列负载

### 8.3 benchmark 脚本异常
- 确认 `examples/benchmark_topics.jsonl` 存在且格式正确
- 确认 `.venv` 依赖完整
- 使用 `SEARCH_PROVIDER=mock` 排除外部依赖波动

## 9. 文档约定

相关文档：
- `README.md`：系统总览与主入口
- `docs/OPENVIKING_INTEGRATION.md`：集成与运维手册
- `docs/INTERVIEW_PLAYBOOK.md`：运行与演示流程手册（本文件）

维护原则：
- 命令可复制执行
- 每个流程有明确验收点
- 优先说明失败路径与回退策略
