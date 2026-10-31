# 项目概览

`astrbot_plugin_setu` 提供多源随机图片、随机本子 PDF/ZIP、平台适配发送和每日运势。

## 核心能力

- Lolicon、SexNyan、自定义 API 与多源策略。
- 标签搜索、别名、数量和内容分级；可配置短语入口与单次 `r18` 标记。
- 图片直发、合并转发、DOCX 及 NapCat 传输策略。
- 全局配置加会话模板覆盖，Setu／运势分别按完整 SID 控制会话访问。
- 五套运势主题、个人偏好和按会话保存的每日星级。
- 图片获取、运势获取与刷新 LLM 工具。

## 配置只有一个入口

所有设置都在 AstrBot 插件配置中管理：`safety` 管权限，`session_configs` 用模板管理会话差异。保存后重载，不提供独立 Pages、管理命令或配置修改工具。

提示集中管理但不开放自定义，内部调优采用固定默认。未知配置删除，非法值恢复默认；升级后应检查 SID 权限。

## 分层取舍

- `domain`：标签、访问控制、运势等级等稳定规则。
- `application`：图片用例与只读会话配置解析。
- `infrastructure`：AstrBot、provider、sender、配置清理及统一 SQLite 持久化。
- `shared`：配置模型、内置提示、日志及发送缓存。

运势唯一键为会话 SID、用户、日期；个人偏好按 `user_id` 跨会话共享。

启动与模块关系见[架构说明](./architecture.md)，使用方法见[配置参考](../usage/configuration.md)。
