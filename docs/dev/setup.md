# 开发环境与本地调试

## 前置要求

- Python 3.10+
- AstrBot 主仓库本地开发环境
- 推荐使用 `uv`

## 本地代码位置

插件通常位于：

```text
AstrBot/data/plugins/astrbot_plugin_setu
```

## 常用目录

```text
assets/      # 静态资源与预览图
src/         # DDD 主代码
tests/       # 单元与集成测试
docs/        # 项目、开发、使用文档
skills/      # 给 AI agent 的 skill
templates/   # 运势卡片 HTML 模板与字体资源
```

## 运行与调试原则

### 启动入口

项目运行通常启动 AstrBot 主仓库顶层入口，而不是直接运行插件目录内的文件。

本地工作区常见入口：

```bash
python /path/to/AstrBot/main.py
```

### 数据目录

不要把运行时数据写回插件仓库下的 `data/`。

本插件统一通过 `StarTools.get_data_dir(self.name)` 访问运行时数据目录。

`tests/conftest.py` 会在导入 `astrbot.core` 之前固定 `ASTRBOT_ROOT`，避免 AstrBot 默认以 `os.getcwd()` 作为根目录，从而在插件目录下创建 `data/cmd_config.json` 和 `data/t2i_templates/`。

### 启动结构

启动分工见 [`../project/architecture.md`](../project/architecture.md)。本地调试时保持 `main.py` 专注注册和路由，不要把业务逻辑塞进入口文件。

### 配置调试

在 AstrBot 插件配置中编辑 `session_configs` 与 `safety`，保存后重载。首次迁移请使用合成运行数据验证，不要在插件目录创建 `data/`。独立 worktree 运行测试时，显式设置 `ASTRBOT_ROOT` 为现有 AstrBot 根目录。

## 测试与检查命令

命令清单统一维护在 [`testing.md`](./testing.md)，本文件不重复列出。

## 改动前先确认的几件事

- 改的是命令语义、配置模型，还是 UI 行为？
- 这次改动是否会影响 provider 发送或缓存兼容性？
- 这次改动是否需要同步更新 README 与 docs？
