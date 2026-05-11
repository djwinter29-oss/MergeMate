# MergeMate 深度审查报告 — 2026-05-10

## 基准线

| 检查项 | 结果 |
|--------|------|
| 测试 | 810 passed, 4 skipped (19.5s) |
| 覆盖率 | 99% (3,028 stmts, 45 miss) |
| mypy | 0 errors (73 源文件, strict=false) |
| ruff | All checks passed |
| 源码 | 7,404 LOC (73 文件) / 测试 17,842 LOC (67 文件) |
| FIXME/TODO | 0 in src/ |
| Domain→Infra 依赖 | 0 (clean architecture 严格遵守) |
| 上次审查 P0 tickets | 全部已完成 (4/4) |

## 上次审查追溯

### P0 全部已解决 ✅
- 可观测性 ✅ — telemetry/logger.py + health.py readiness 端点
- 领域依赖泄漏 ✅ — 策略函数移到 domain/policies/
- async wrapper for sync I/O ✅ — tool_service.py 用 asyncio.to_thread
- remember_success 缺少 await ✅ — 已修复

### P1 进度
- DI 爆炸 → 类型化 context ✅ done (OrchestratorDependencies dataclass)
- 硬编码 pipeline → 插件系统 ✅ done (WorkflowStage + register_handler/register_workflow)
- 集成测试 ✅ done (3 个集成测试文件)

### P2 进度
- strict mypy ❌ 仍为 false
- LLM retry/backoff ❌ 缺失
- Infrastructure stubs ✅ done
- config validate CLI ✅ done

## 本次新发现

### 🔴 P0 — 阻塞级

#### P0.1: LLM 网关缺少重试/回退机制
ParallelLLMGateway._generate_from_provider() 无 retry/backoff。429/5xx 直接上抛。
**影响：** 生产环境中 LLM API 瞬时故障不可忽略，无自动重试导致偶发失败。
**建议：** 用 tenacity 或指数退避加 3 次重试。

### 🟡 P1 — 重要级

#### P1.1: config/models.py 反向依赖域层
第 11-19 行 import domain.shared.exceptions 和 domain.policies。Config 层不应依赖 domain 业务逻辑。

#### P1.2: AgentOrchestrator.process_run repository 调用阻塞事件循环
run_repository.get() 等所有 repository 操作为同步 SQLite I/O，直接阻塞事件循环。tool_service.py 已异步化但 repository 层没有。

#### P1.3: bootstrap.py 覆盖率 84% — 插件加载路径未测试
20 行未覆盖（59-64, 82-100），集中在入口点发现和文件式配置插件加载。

#### P1.4: handlers.py register_document_kind 冲突检测未覆盖
第 252-264 行 kind 已注册时的 warning 逻辑未被测试。

### 🟢 P2 — 优化级

#### P2.1: 高价值功能提案待实现
- CLI 交互模式 (mergemate chat) — 未实现
- Retry/Resume Failed Session — 协议层已定义但缺 UseCase
- Conversation History Search — 未实现

#### P2.2: mypy strict = false 未启用
7,404 LOC 代码库仍未严格模式。

#### P2.3: infrastructure/persistence/repositories/__init__.py 空占位符
33 bytes 空文件，可删除。

#### P2.4: StageDescriptor 标记 legacy 但仍在使用
DirectExecutionPlan 和 BaseExecutionPlan 仍返回 StageDescriptor。

#### P2.5: sqlite.py load_grouped_learnings other_workflows 分支未覆盖
第 716-743 行的 other_workflows 分支未被测试。

## 建议汇总

| 优先级 | 改进项 | 工作估计 |
|--------|--------|---------|
| P0.1 | LLM 网关添加 retry/backoff | ~1 天 |
| P1.1 | 消除 config→domain 反向依赖 | ~1-2 天 |
| P1.2 | repository 层异步化 | ~2 天 |
| P1.3 | 补齐 bootstrap 插件加载路径测试 | ~0.5 天 |
| P1.4 | 补齐 handlers.py 未覆盖行 | ~0.5 天 |
| P2.1 | 实现 Retry/RunResume UseCase | ~2 天 |
| P2.2 | 开启 mypy strict | ~3 天 |
| P2.3 | 删除空 stub 包 | 极小 |
| P2.4 | 淘汰 StageDescriptor | ~0.5 天 |
| P2.5 | 补齐 sqlite.py grouped_learnings 分支测试 | ~0.5 天 |