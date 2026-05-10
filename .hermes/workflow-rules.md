# Kanban Workflow Rules

> 生效日期：2026-05-10
> 目标：防止 dead PR、kanban 产出流失、task 堵塞无人清理

---

## A. 产出落地规则（所有 task 必须遵守）

**硬性要求：** 每一个 kanban task 的产出（新文件、修改、测试、文档）最终必须出现在 `main` 分支上。不存在「看板完成但代码没进仓库」的情况。

### A1. 修改现有文件 → 使用 `--workspace worktree`

```bash
hermes kanban create "标题" --assignee coder --workspace worktree
```

### A2. 创建新文件 → 明确指定目标路径

- task body 中写明输出文件的目标路径
- 完成后用 `mv / patch / cp` 将文件移到 repo 中
- 最终 commit + push

### A3. 多子 task 的收集

architect 拆子 task 时，最后一个子 task 应为 **collect-and-commit**，负责将所有子 task 的产出合并到 repo：

```
T0  architect   decompose → 3 subtasks
T1  coder       feat X          workspace: worktree
T2  tester      test X          workspace: worktree
T3  coder       collect-and-commit  workspace: worktree
                 body: merge T1, T2 branches, rebase to main, create PR
```

---

## B. Review 流程

### B1. Review 必须走 GitHub PR

| 阶段 | 平台 | 责任方 |
|------|------|-------|
| Pre-review checklist | Kanban | reviewer profile（可选） |
| 正式 code review | **GitHub PR** | reviewer profile（approve/reject） |
| 最终 gate | GitHub | PR merge button |

### B2. 禁止

- ❌ 在 kanban 列里完成 review（review 必须走 GitHub）
- ❌ reviewer 在 kanban 上 block task 代替 PR 上的 comment
- ❌ 没有 GitHub PR 就 merge 到 main 的代码

### B3. PR 规范

- PR 标题：`[task_id] 简短描述`
- PR body：引用 kanban task ID
- PR 至少需要 1 个 approve
- CI 必须全绿才能 merge

---

## C. Blocked Task 清理机制

### C1. 自动标记 stale

- blocked >7 天的 task → 自动标记 stale（由 cron job 或手动扫描）
- stale 标记后 3 天无人回应 → 可 archive

### C2. 人工检查

每周末（或按需）执行：

```bash
hermes kanban list --status blocked
```

对每个 blocked task：

1. 阻塞原因是否已解决？→ unblock
2. 是否已过时？→ archive
3. 还有价值但暂时无解？→ 保持 blocked + 加 comment 说明原因
4. 没价值的垃圾 task？→ archive

### C3. 预防

- **不要把 toy/测试 task 放到 produciton board 上**
- 创建 task 时就要想清楚「谁来做、做什么、产出放哪」

---

## D. Architect 拆子 Task 约束

### D1. 验证 assignee 存在

在 `kanban_create` 之前必须执行：

```bash
hermes profile list | grep <profile_name>
```

只有存在于 `profile list` 中的 profile 才能作为 assignee。

### D2. 指定产出路径

每个子 task 的 body 中必须包含：

```
产出：<目标路径>
```

### D3. 依赖关系控制

使用 `--parent` 参数：

```bash
hermes kanban create "子任务B" --parent t_xxx
```

- parents 参数让子 task 保持在 `todo` 状态，直到所有 parent 都 `done` 后自动升为 `ready`
- 不需要手动协调——dispatcher + dependency engine 自动处理

### D4. 最终步骤必须是 collect-and-commit

如果有多个子 task 的产出，**最终必须有一个 collect-and-commit 子 task**，其职责是：

1. 从各个子 task 的 workspace 中读取产出文件
2. 将文件复制到 repo 中的正确路径
3. 创建 PR，合并到 main

---

## E. Workspace 卫生

### E1. 选择合适的 workspace

| 场景 | Workspace | 说明 |
|------|-----------|------|
| 修改已有文件 | `worktree` | 在 repo 内直接修改 |
| 创建新分析报告 | `scratch` | 纯文本产出 |
| 批量子 task 协作 | `scratch` + collect-and-commit | 最后统一收集 |

### E2. 避免产出流失

- `scratch` 默认路径是 `~/.hermes/kanban/boards/<board>/workspaces/<task_id>/`
- 如果用 scratch，必须确保有**collect-and-commit 步骤**
- 不要留下「task done 但文件在哪没人知道」的情况

---

## F. 执行与监督

### F1. 执行角色

- **planner**：负责在创建 task 时就指定 workspace 和产出路径
- **architect**：负责在拆子 task 时遵守 D 节规则
- **reviewer**：负责在 GitHub PR 上做 review，不在 kanban 上 block
- **chronicler**：记录 workflow 改进经验

### F2. 违反规则的处置

如果有人发现 task 违反了以上规则（例如产出没落地、review 走错了地方）：

1. 在 task 上加 comment 说明违规
2. 如果 task 还活着 → 修正 workspace 或补充 commit 步骤
3. 如果 task 已经 done → 开一个新的修复 task