# 🌸 Setu 插件（astrbot_plugin_setu）

<div align="center">

<img src="https://count.getloli.com/@astrbot_plugin_setu?name=astrbot_plugin_setu&theme=rule34&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Moe Counter">

**一个支持多平台、可自定义、带防审核机制的随机色图插件，支持多 API、随机本子 PDF/ZIP、会话级配置、LLM 工具调用。**

[![License: AGPL](https://img.shields.io/badge/License-AGPL-blue.svg)](https://opensource.org/licenses/agpl-3.0)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A54.24.0-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)

</div>

本插件完全开源免费，欢迎 Issue 和 PR。

---

## 📸 预览

<div align="center">
  <table>
    <tr>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/img_ob_preview.webp" width="400" alt="色图卡片预览1"/>
        <br/>
        <sub>HTML 卡片包装提高成功率</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/merge_send_preview.webp" width="400" alt="色图卡片预览2"/>
        <br/>
        <sub>多图合并转发</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/tag_search_preview.webp" width="400" alt="色图卡片预览3"/>
        <br/>
        <sub>自定义标签搜索</sub>
      </td>
      <td align="center">
        <img src="https://raw.githubusercontent.com/FlanChanXwO/astrbot_plugin_setu/master/assets/jrys_preview.webp" width="400" alt="今日运势卡片预览"/>
        <br/>
        <sub>基于色图驱动的今日运势</sub>
      </td>
    </tr>
  </table>
</div>

---

## ✨ 功能特性

- 🎨 **多 API 支持** - Lolicon、Atri、SexNyan、自定义 API 等
- 🧩 **分层架构** - `application` / `domain` / `infrastructure` / `shared` 清晰分离
- 🖼️ **HTML 卡片包装** - 防止平台审核，支持自定义样式
- 🤖 **LLM 工具调用** - 可通过大模型自动获取色图
- 🏷️ **标签搜索** - 支持多标签、中文标签、模糊匹配
- 🔄 **多种色图发送模式** - 直接发送、合并转发、文件封装
- 📚 **随机本子文件** - 获取 API 返回的全部页图，可配置封装为 PDF 或 ZIP；OneBot/NapCat 普通文件消息可按统一可恢复队列延迟撤回
- 🛡️ **防审核机制** - HTML 卡片 fallback、NapCat 流式上传、延迟撤回、Docx 封装
- ⚡ **性能优化** - 磁盘缓存、自动补图、httpx、可观测下载重试
- 🌐 **多平台适配** - 兼容 AstrBot 支持的所有平台

---

## 📦 安装

### 方式一：通过 AstrBot 插件市场安装（推荐）

在 AstrBot 管理面板中搜索 `astrbot_plugin_setu` 并安装。

### 方式二：手动安装

1. 克隆本仓库到 AstrBot 的插件目录：
   ```bash
   cd AstrBot/data/plugins
   git clone https://github.com/FlanChanXwO/astrbot_plugin_setu.git
   ```
2. 重启 AstrBot 或重载插件

---

## 📝 使用方法

### 基础命令

发送以下任一指令即可获取色图：

```text
来一份色图
来三份白丝瑟图
来9份白丝 萝莉色图
/setu 白丝 萝莉
/setu 3 白丝
来份本子
/随机本子
/session_config set setu.content_mode r18
```

- 数量范围支持中文数字
- 标签支持空格、逗号、顿号分隔
- `/session_config` 统一管理当前会话的覆盖配置
- `/随机本子`（别名 `/本子`、`/doujinshi`）按 `delivery.doujinshi_send_mode` 生成并发送随机本子 PDF 或 ZIP；所有平台均直接发送文件，不再使用合并转发；OneBot 群聊可按配置延迟撤回对应的普通文件消息

完整的命令说明见 [`docs/usage/commands.md`](./docs/usage/commands.md)。

### 会话配置命令（管理员设置）

```bash
/session_config get
/session_config get setu.content_mode
/session_config set setu.content_mode r18
/session_config clear setu.send_mode
/session_config clear
```

### 黑白名单管理命令（管理员）

通过插件 WebUI 的 Dashboard 访问控制标签页可集中管理黑白名单，也可使用命令动态管理：

```bash
/拉黑色图用户 @用户
/信任色图用户 @用户
/开启色图
/关闭色图
/运势用户 拉黑 @用户
/运势开关 开
/运势刷新
/运势刷新 全局
```

完整命令列表见 [`docs/usage/commands.md`](./docs/usage/commands.md)。

### LLM 工具调用

- 支持通过大模型自动调用色图工具
- 需在 AstrBot 配置好 LLM 提供商

完整工具清单见 [`docs/usage/ai-tools.md`](./docs/usage/ai-tools.md)。

---

## 🛠️ 配置

在 AstrBot 管理面板中配置。完整配置参考见 [`docs/usage/configuration.md`](./docs/usage/configuration.md)。

### 基础配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `api_type` | API 类型（lolicon / atri / sexnyan / custom / all） | `lolicon` |
| `send_mode` | 色图发送模式（auto / image / forward） | `auto` |
| `doujinshi_send_mode` | 本子文件格式（pdf / archive） | `pdf` |
| `doujinshi_max_page` | 随机本子最大页数（`0` 表示不限） | `0` |
| `content_mode` | 内容模式（sfw / r18 / mix） | `sfw` |
| `max_count` | 单次最大图片数（1-10） | `10` |
| `max_replenish_rounds` | 下载暂时失败时的同 URL 确认尝试次数/补图轮次 | `3` |
| `cache_enabled` | 是否复用本地发送缓存 | `true` |
| `exclude_ai` | 是否排除 AI 生成图片 | `true` |

### 功能开关

随机本子、LLM 工具、自然语言触发均可在 WebUI 单独关闭，默认开启；现有 `fortune.enabled` 是运势总开关。
关闭后会拦截对应入口并跳过相关初始化，已有撤回任务继续执行。修改后重载插件生效，详见 [功能开关配置](docs/usage/configuration.md#功能开关)。

### 防审核配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `html_card_strategy` | HTML 卡片策略（never / fallback / always） | `fallback` |
| `platform_transports` | 平台传输模板列表，可添加 NapCat 模板 | `[]` |
| `auto_revoke_targets` | 自动撤回内容列表（`setu` / `fortune` / `doujinshi`） | `["doujinshi"]` |
| `auto_revoke_scope` | 自动撤回范围（none / sfw / r18 / all） | `none` |
| `auto_revoke_delay` | 已启用内容共用的自动清理延迟（秒，`0` 全部关闭） | `30` |
| `r18_docx_mode` | R18 是否使用 Docx 封装 | `true` |

图片下载遇到短暂网络错误时会先按 `max_replenish_rounds` 对同一 URL 做确认重试；发送接口超时或 OneBot/NapCat 类适配器未返回 message id 时会标记为可能仍在送达，不会立刻触发降级重复发图。旧版 `auto_revoke_r18` 会在启动时迁移为 `auto_revoke_scope`，迁移后不再作为公开配置项展示。

NapCat stream 上传的分块内容按 NapCat 协议仍为 base64 字符串；若 AstrBot 与 NapCat 共享同一图片目录，可在 `platform_transports` 添加 NapCat 模板，将共享目录加入 `local_file_allowed_roots` 并把 `local_file_mode` 设为 `always` 或 `fallback`，让直发模式通过 raw OneBot `file://` 路径绕过 AstrBot 标准链路的 base64 转换。

`auto_revoke_targets` 是单一内容列表，默认只含 `doujinshi`，因此色图和今日运势默认不撤回；按需加入 `setu` 或 `fortune`。色图加入后还须命中 `auto_revoke_scope`。三类内容共享 `auto_revoke_delay` 和 OneBot 可恢复队列；设置 `1800` 即为 30 分钟，设为 `0` 会关闭全部自动清理。随机本子无论选择 PDF 还是 ZIP 都以普通文件消息发送；OneBot/NapCat 群聊发送成功后会直接登记消息 ID，到期调用 `delete_msg`，不再反查群文件。所有任务保存于插件运行数据目录的 `revoke_tasks.json`，插件重启后仍按原到期时间继续执行。

### 模板覆盖

| 配置项 | 说明 |
|--------|------|
| `provider_overrides` | 覆盖 provider 默认参数 |
| `custom_api_configs` | 自定义图片 API 列表 |
| `tag_alias_templates` | 标签别名映射 |
| `message_overrides` | 自定义提示文案（支持占位符；内置提示默认启用，可用覆盖模板关闭或修改） |

### 访问控制

访问控制通过插件 WebUI 的 Dashboard 访问控制标签页管理，支持：

- Setu / 运势独立的用户和群组访问模式
- 黑白名单表格管理
- 旧版 `safety.*` 配置自动迁移

详见 [`docs/usage/plugin-pages.md`](./docs/usage/plugin-pages.md)。

---

## 📚 文档

- [`docs/usage/`](./docs/usage/README.md): 命令、配置、AI 工具、管理页说明
- [`docs/project/`](./docs/project/README.md): 项目定位、架构与设计取舍
- [`docs/dev/`](./docs/dev/README.md): 开发环境、测试、贡献与维护规则
- [`CHANGELOG.md`](./CHANGELOG.md): 版本变更记录

---

## 未来更新
- [ ] 更好的自定义 API
- [ ] 更细粒度的 provider 健康检查与降级策略
- [ ] 继续补全 WebUI 配置与诊断能力

---

## 📄 开源协议

 本项目基于 [AGPL](LICENSE) 协议开源。
