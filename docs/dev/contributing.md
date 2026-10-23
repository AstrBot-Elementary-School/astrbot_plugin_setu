# 贡献说明

## 贡献目标

优先做这些事情：

- 修复 Setu/Fortune 命令、provider、sender 回归
- 完善插件配置与会话模板的易用性
- 提高多平台 sender 稳定性和 provider 可靠性
- 补全文档、测试与排障能力

大范围重构前，先说明涉及哪些行为和模块。

## AI 贡献

本项目允许使用 AI 协作贡献。

适合 AI 参与的工作包括：

- 后端实现与回归修复
- 配置 schema 与迁移维护
- 测试补全
- 文档整理与架构说明
- 排障、日志梳理、兼容性分析

## 改动前先理解当前边界

改动前按任务查阅：

- 架构与启动分工见 [`../project/architecture.md`](../project/architecture.md)
- 命令见[命令参考](../usage/commands.md)；配置模型见 `src/shared/config/models.py`，内置提示见 `src/shared/config/messages.py`
- 平台发送和 provider 适配见 `src/infrastructure/providers/` 和 `src/infrastructure/sending/`

若要改变现有行为，在 PR 中说明原因和兼容影响。

## 推荐的贡献流程

1. 明确问题或目标
2. 先阅读相关代码与现有测试
3. 小步提交，单次改动尽量围绕一个目的
4. 先补或更新测试，再补文档
5. 通过 lint 与最小回归检查后再提交 PR

## 文档同步要求

哪些文档需要更新，见[文档同步](./maintenance.md#文档同步)。

## 代码风格

通用工程原则见 [`engineering-principles.md`](./engineering-principles.md)。贡献时优先沿用现有模式，不要为局部问题顺手重构无关模块。

## PR 描述建议

使用仓库 PR 模板，保留三个章节并完成检查清单。`PR Template Validation` 会在创建 PR、推送或修改描述后检查格式；测试触发范围见[PR 合并检查](./testing.md#pr-合并检查)。

描述中至少写清楚：

- 背景问题
- 改动范围
- 风险点
- 验证方式

回归修复应说明原来哪里出错，以及如何验证。
