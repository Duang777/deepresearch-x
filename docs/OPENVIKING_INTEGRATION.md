# OpenViking Integration Guide

本文档定义 DeepResearch-X 与 OpenViking 的集成方式、运行约束、验收标准与故障处理策略。

## 1. 目标与范围

### 目标
- 将 OpenViking 作为可选记忆后端接入 DeepResearch-X。
- 在外部服务不可用时，保证主流程不被阻断。
- 保持核心编排逻辑与后端实现解耦。

### 范围
- 包含：运行配置、接口约定、降级策略、验证步骤。
- 不包含：OpenViking 端到端部署细节（由 OpenViking 项目负责）。

## 2. 架构与职责边界

### 关键组件
- `MemoryService`：统一记忆读写与队列调度。
- `SQLiteStore`：默认本地后端，始终可用。
- `OpenVikingMemoryAdapter`：远程后端适配层，失败自动回退。

### 设计原则
- Core pipeline 仅依赖 `MemoryStore` 协议，不依赖具体实现。
- 远程失败不向上冒泡为致命错误，统一走本地降级路径。
- 回退后启用失败冷却，避免重复超时拖慢请求。

## 3. 接口约定

适配器默认请求以下端点：
- `POST /api/v1/retrieval/find`
- `POST /api/v1/sessions/commit`
- `POST /api/v1/sessions/checkpoint`

如果 OpenViking 服务端接口与上述不一致，请调整：
- `deepresearch_x/memory/openviking.py`

建议保持以下契约不变：
- `get_memory(session_id, scope, limit) -> List[MemoryFact]`
- `upsert_facts(facts) -> MemoryUpsertResult`
- `save_checkpoint(checkpoint) -> None`

## 4. 运行配置

`.env` 最小配置：

```env
MEMORY_BACKEND=openviking
OPENVIKING_BASE_URL=http://127.0.0.1:8100
OPENVIKING_TIMEOUT_SECONDS=0.8
```

建议配置：
- 本地开发：`OPENVIKING_TIMEOUT_SECONDS=0.5~1.0`
- 内网稳定服务：`OPENVIKING_TIMEOUT_SECONDS=1.0~2.0`

## 5. 降级与容错策略

### 触发条件
- 连接失败
- 请求超时
- 非 2xx 状态码
- 响应体不满足解析要求

### 处理行为
- 读取：回退 `fallback_store.get_memory(...)`
- 写入：回退 `fallback_store.upsert_facts(...)`
- Checkpoint：优先写本地，远程写失败不影响主流程
- 冷却机制：短时间禁用远程探测，减少持续超时开销

## 6. 验收流程

### 步骤 A：远程可用
1. 启动 OpenViking 服务。
2. 执行一次研究请求，指定 `memory_backend=openviking`。
3. 校验：
- HTTP 200
- 返回包含 `memory_*` 指标
- 会话记忆可查询

### 步骤 B：远程不可用
1. 关闭 OpenViking 服务。
2. 重复同样请求。
3. 校验：
- HTTP 仍为 200
- 请求延迟可控（受超时与冷却策略影响）
- 功能继续可用（通过 SQLite 回退）

## 7. 观测指标建议

建议重点关注：
- `metrics.memory_recall_hits`
- `metrics.memory_queue_latency_ms`
- `memory_write_count`
- `memory_conflict_count`
- `metrics.total_elapsed_ms`

建议设定报警阈值（示例）：
- 连续 5 分钟远程失败率 > 30%
- 平均请求延迟较基线上升 > 40%

## 8. 安全与合规说明

- 本仓库通过网络适配边界对接 OpenViking，不引入其源码。
- 若在生产环境分发，请依据部署模式评估许可证义务与合规要求。
- 建议在企业环境中补充访问控制、审计日志与密钥管理策略。

## 9. 常见问题

### Q1: 为什么选择默认 SQLite 而非默认 OpenViking？
- 为保证本地与 CI 环境稳定可运行，避免远程依赖成为单点风险。

### Q2: 如何快速判断当前是否发生回退？
- 观察远程可用性日志（若启用）与请求延迟变化。
- 对比同一时段 `openviking` 与 `sqlite` 模式下的 `memory_write_count` 行为。

### Q3: OpenViking API 变更后如何最小代价升级？
- 仅修改 `openviking.py` 的路径与解析映射，保持 `MemoryStore` 协议不变。
