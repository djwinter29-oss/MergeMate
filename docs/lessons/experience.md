# 项目经验记录

本文档记录本项目开发过程中遇到的经验、坑位和最佳实践。

## 多角色 Git 冲突解决

**问题**：多个角色（coder, tester 等）并行工作时，Git 冲突不可避免。

**解决方案**：见 [git-conflict-resolution.md](./git-conflict-resolution.md)

**核心原则**：
1. 按角色隔离目录（coder 写 src/，tester 写 tests/）
2. 同一文件同函数 → 串行化，不要并行
3. 冲突时 coder 优先解决（最了解代码逻辑）
4. 角色越界修代码 → kanban block + 重新分配
5. Epic 级功能用共用分支 + worktree 隔离