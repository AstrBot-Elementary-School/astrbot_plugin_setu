# 贡献说明

## 贡献目标

优先做这些事情：

- 修复 Setu/Fortune 命令、provider、sender 回归
- 完善插件配置与会话模板的易用性
- 提高多平台 sender 稳定性和 provider 可靠性
- 补全文档、测试与排障能力

不建议直接上来做大而散的重构，除非先把行为边界讲清楚。

## AI 贡献

本项目允许使用 AI 协作贡献。

适合 AI 参与的工作包括：

- 后端实现与回归修复
- 配置 schema 与迁移维护
- 测试补全
- 文档整理与架构说明
- 排障、日志梳理、兼容性分析

## 改动前先理解当前边界

改动前先确认自己触碰的是哪条边界，不在这里复制业务规则：

- 架构与启动分工见 [`../project/architecture.md`](../project/architecture.md)
- 命令、配置模型和消息配置见 README 与 `src/shared/config/models.py`
- 平台发送和 provider 适配见 `src/infrastructure/providers/` 和 `src/infrastructure/sending/`

如果准备做的事和这些边界冲突，需要先明确说明为什么。

## 推荐的贡献流程

1. 明确问题或目标
2. 先阅读相关代码与现有测试
3. 小步提交，单次改动尽量围绕一个目的
4. 先补或更新测试，再补文档
5. 通过 lint 与最小回归检查后再提交 PR

## 文档同步要求

文档同步细则统一维护在 [`maintenance.md`](./maintenance.md#文档同步)。贡献文档只强调一点：不要只改代码而让 README、docs、CHANGELOG 或 agent 入口说明失真。

## 代码风格

通用工程原则见 [`engineering-principles.md`](./engineering-principles.md)。贡献时优先沿用现有模式，不要为了局部问题顺手大改 unrelated 模块。

## PR 描述建议

建议至少写清楚：

- 背景问题
- 改动范围
- 风险点
- 验证方式

如果是回归修复，最好明确指出"避免了什么回退"。
