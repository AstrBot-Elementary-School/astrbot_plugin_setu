# AGENTS.md — astrbot_plugin_setu

本文件只保留协作 agent 的入口规则。业务细节按需阅读 `docs/project/`，开发维护规则优先阅读 `docs/dev/maintenance.md`。

## 沟通语言

- 与用户沟通必须使用中文。

## 项目形态

- 这是一个 AstrBot 随机图片与随机本子 PDF 插件，采用 DDD 分层。
- 管理功能属于 Plugin Pages（统一 dashboard 页面，含会话配置和访问控制标签页）。
- 新入口必须遵守全局功能开关；入口守卫与启动边界见 `docs/project/architecture.md`，开关语义见 `docs/usage/configuration.md`。

主要目录：

- `src/domain/`: 领域实体、值对象、标签解析、访问控制。
- `src/application/`: 用例、DTO、端口接口、会话配置服务。
- `src/infrastructure/`: 配置、持久化、provider、随机本子 PDF、sender、AstrBot 适配。
- `src/shared/`: 配置模型、日志、发送缓存。
- `pages/`: Plugin Pages 前端（统一 dashboard）。
- `templates/`: 运势卡片 HTML 模板与字体。
- `tests/`: 单元测试、集成测试与测试夹具。

## 阅读入口

- 任何改动前先看：`docs/dev/maintenance.md`
- 需要业务背景时看：`docs/project/overview.md`
- 修改模块关系和启动分工时看：`docs/project/architecture.md`
- 修改消息配置、提示文案或占位符时看：`src/shared/config/models.py`
- 修改 provider 适配或 sender 策略时看：`src/infrastructure/providers/` 和 `src/infrastructure/sending/`

## 硬约束

- 不要把业务逻辑编排塞进 `main.py`；保持注册和路由专注。
- 插件运行数据必须通过 `StarTools.get_data_dir(self.name)` 获取，不要硬编码路径。
- 从插件目录本地调试时，不要创建或使用 `<plugin>/data` 作为运行态目录。
- 所有用户可见提示必须走 `MessagesConfig` / `resolve_message()`，不要在 handler 内硬编码提示文案。
- 随机本子 PDF 由 `infrastructure/doujinshi/` 生成；OneBot/NapCat 使用 `Nodes` 合并转发并按消息 ID 进入统一可恢复撤回，其他平台直接发送 `File`。
- 色图与随机本子都必须使用 `application/setu/tag_resolution.py` 解析标签，保持分隔符和别名映射语义一致。
- `delivery.auto_revoke_targets` 以单一列表选择色图、今日运势和本子是否进入自动清理；三者共用 `auto_revoke_delay`，本子合并转发必须在发送时取得并立即持久化 `message_id`，避免异步上传可见性导致清理状态丢失。
- 其他领域值、平台行为和配置边界不要写进本文件，放到 `docs/project/` 或 `docs/dev/`。

## 文档纪律

- 文档不是可选收尾。行为、边界、入口、配置、流程或维护约定变化时，必须同步更新对应 `docs/`。
- 下列变化默认必须同步文档：
  - 命令行为或参数变化
  - Plugin Pages 交互变化
  - 配置项、默认值或兼容规则变化
  - provider、sender、消息配置算法变化
  - 访问控制判定逻辑变化
- 如果修改 repo-wide 维护规则或 agent 入口约定，同步更新 `AGENTS.md` 和 `CLAUDE.md`。

## 测试与检查命令

从插件目录运行：

```bash
PYTHONPATH=/path/to/data/plugins python -m pytest tests/ -v
PYTHONPATH=/path/to/data/plugins python -m pytest tests/infrastructure/test_fortune_pregeneration.py -q
RUFF_CACHE_DIR=.ruff_cache python -m ruff check .
python -m ruff format .
python -m py_compile main.py src/**/*.py tests/**/*.py
```

从 AstrBot 项目根目录运行：

```bash
uv run ruff format data/plugins/astrbot_plugin_setu
uv run ruff check data/plugins/astrbot_plugin_setu
```

## 更新策略

当架构、命令面、发送策略、配置路径或测试 / lint 流程变化时，同步更新 `CLAUDE.md` 和 `AGENTS.md`。

## 篇幅约束

`AGENTS.md` 和 `CLAUDE.md` 均不得超过 100 行；内容过长时拆入 `docs/dev/` 或 `docs/project/`。
