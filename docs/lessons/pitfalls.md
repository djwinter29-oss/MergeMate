# 踩坑记录

## Tester 越界修改 src/ 代码

**现象**：tester 在写测试时发现 bug，直接改 `src/` 里的代码。

**根因**：tester 的 Soul 边界明确规定"不得编写实现代码"，但"顺手修一下"的冲动很难克制。

**教训**：Kanban 需要检测并自动拦截。如果 tester 修改了 `src/` 目录，应该在提交时触发警报，自动创建 coder task。

## 两个 Coder Worker 同时改同一个文件的同一个函数

**现象**：coder-1 和 coder-2 同时修改 `service.py` 的 `do_thing()`。

**根因**：任务分解不够细。两个 worker 被分配了重叠的职责。

**教训**：planner 在分解任务时，必须确保每个文件在同一时刻只被一个 worker 修改。可以用 kanban 的 `depends_on` 强制串行化。

## 并行模式 1 个 Worker 却设了 parallel

**现象**：配置了 `parallel_mode: parallel` 但只有一个 worker，结果走了 parallel 分支但没有并发收益。

**根因**：配置错误。

**教训**：配置校验应该增加规则——`parallel_mode: parallel` 需要至少 2 个 workers。当前代码已经加了这个检查。