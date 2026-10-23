# Setu 文档索引

`astrbot_plugin_setu` 的补充文档按用途拆分为三个目录：

- [`project/`](./project/README.md): 项目定位、架构、现状与路线图
- [`dev/`](./dev/README.md): 开发环境、测试流程、贡献约定
- [`usage/`](./usage/README.md): 面向使用者的命令、配置、会话模板说明

## 文档职责边界

文档按"入口索引、开发流程、项目事实、用户说明"拆分，避免同一规则多处维护：

- `docs/README.md` 只做总索引和阅读路径。
- `docs/dev/` 只写开发、测试、贡献、维护纪律，不复制业务语义。
- `docs/project/overview.md` 只写项目定位和取舍，不维护细节清单。
- `docs/project/architecture.md` 写模块关系和主运行链路。
- `docs/project/domain-model.md` 是领域值、枚举、配置模型、常量归属的唯一细节来源。
- 其他 `docs/project/*.md` 按模块深挖流程和实现边界。
- `docs/usage/` 面向用户说明，维护命令、配置、会话模板和兼容性说明。

如果多个文档都提到同一概念，应由最具体的专题文档维护细节，其他文档只链接过去。

## 章节索引

### project

- [`project/overview.md`](./project/overview.md): 项目定位、边界、设计目标与核心取舍
- [`project/architecture.md`](./project/architecture.md): 架构全景、模块关系、运行主链路与配置职责

### dev

- [`dev/setup.md`](./dev/setup.md): 环境准备、运行入口、目录约束
- [`dev/testing.md`](./dev/testing.md): lint、pytest、回归清单
- [`dev/contributing.md`](./dev/contributing.md): 贡献流程、改动边界、提交约定
- [`dev/engineering-principles.md`](./dev/engineering-principles.md): 工具使用、错误处理、保护逻辑与前端验证原则
- [`dev/maintenance.md`](./dev/maintenance.md): 维护规则、配置边界、已移除能力与文档同步要求

### usage

- [`usage/README.md`](./usage/README.md): 使用文档索引
- [`usage/commands.md`](./usage/commands.md): 聊天业务命令与刷新操作
- [`usage/configuration.md`](./usage/configuration.md): 基础配置、HTML 卡片与防审核、性能优化
- [`usage/ai-tools.md`](./usage/ai-tools.md): LLM tools 能力和使用边界

## 推荐阅读路径

### 我想快速理解这个插件

1. [`project/overview.md`](./project/overview.md)
2. [`project/architecture.md`](./project/architecture.md)
3. [`README.md`](../README.md)

### 我要参与开发或维护

1. [`dev/setup.md`](./dev/setup.md)
2. [`dev/testing.md`](./dev/testing.md)
3. [`dev/contributing.md`](./dev/contributing.md)
4. [`dev/engineering-principles.md`](./dev/engineering-principles.md)
5. [`dev/maintenance.md`](./dev/maintenance.md)

### 我只想查命令和配置

1. [`usage/commands.md`](./usage/commands.md)
2. [`usage/configuration.md`](./usage/configuration.md)
3. 按需继续阅读 [`usage/`](./usage/README.md)
