# 项目导航

`astrbot_plugin_setu` 是 AstrBot 随机图片、随机本子 PDF/ZIP 和今日运势插件，按 domain、application、infrastructure、shared 分层。

## 按任务找文档

- 了解功能和使用方式：[README.md](README.md)、[命令](docs/usage/commands.md)、[LLM 工具](docs/usage/ai-tools.md)。
- 调整全局配置、会话模板或 SID 权限：[配置参考](docs/usage/configuration.md)。
- 理解模块关系、启动流程和数据归属：[架构](docs/project/architecture.md)、[项目概览](docs/project/overview.md)。
- 准备本地环境或运行检查：[环境搭建](docs/dev/setup.md)、[测试](docs/dev/testing.md)。
- 修改配置兼容或迁移流程：[维护说明](docs/dev/maintenance.md#配置与迁移)、[升级与恢复](docs/usage/configuration.md#升级与恢复)。
- 排查 OneBot/NapCat 多图发送、Base64 图片和 t2i 卡片回退：[传输上限与诊断](docs/project/sending-limits.md)。
- 提交贡献或同步文档：[贡献说明](docs/dev/contributing.md)、[工程协作](docs/dev/engineering-principles.md)。

## 按模块找代码

- 入口注册、生命周期和命令路由：`main.py`。
- 图片请求与标签解析：`src/application/setu/`；标签规则：`src/domain/setu/`。
- 会话模板解析：`src/application/session_config/`；访问控制：`src/domain/access_control/`。
- 运势生成：`src/domain/fortune/`；命令适配与渲染：`src/infrastructure/astrbot/`。
- 图片源适配：`src/infrastructure/providers/`；本子文件生成：`src/infrastructure/doujinshi/`。
- 图片与文件发送、传输和撤回：`src/infrastructure/sending/`。
- 配置界面：`_conf_schema.json`；配置模型与内置提示：`src/shared/config/`；迁移：`src/infrastructure/config/`。
- 运行数据存储：`src/infrastructure/persistence/`；发送缓存：`src/shared/send_cache.py`。
- 运势卡片模板：`templates/`；测试与夹具：`tests/`。

完整文档索引见 [docs/README.md](docs/README.md)。
