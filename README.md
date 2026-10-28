# Setu 插件（astrbot_plugin_setu）

<div align="center">

<img src="https://count.getloli.com/@astrbot_plugin_setu?name=astrbot_plugin_setu&theme=rule34&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Moe Counter">

**支持多图片源、随机本子 PDF/ZIP、今日运势、会话配置和 LLM 工具调用的 AstrBot 插件。**

[![License: AGPL](https://img.shields.io/badge/License-AGPL-blue.svg)](https://opensource.org/licenses/agpl-3.0)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![AstrBot](https://img.shields.io/badge/AstrBot-%E2%89%A54.24.0-green)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey)

</div>

本插件完全开源免费，欢迎 Issue 和 PR。

---

## 预览

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

## 功能特性

- **多 API 支持** - Lolicon、SexNyan、自定义 API 等
- **分层架构** - `application` / `domain` / `infrastructure` / `shared` 清晰分离
- **HTML 卡片包装** - 普通发送失败后尝试卡片发送
- **LLM 工具调用** - 可通过大模型自动获取色图
- **标签搜索** - 支持多标签、中文标签、模糊匹配
- **多种色图发送模式** - 直接发送、合并转发、文件封装
- **随机本子文件** - 获取 API 返回的全部页图，可配置封装为 PDF 或 ZIP；OneBot/NapCat 普通文件消息可按统一可恢复队列延迟撤回
- **防审核机制** - HTML 卡片 fallback、NapCat 流式上传、延迟撤回、Docx 封装
- **性能优化** - 磁盘缓存、自动补图、httpx、可观测下载重试
- **多平台适配** - 支持 AstrBot 多平台发送；合并转发、流式上传和撤回能力因平台而异

---

## 安装

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

## 使用方法

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
```

- 数量范围支持中文数字
- 标签支持空格、逗号、顿号分隔
- 会话覆盖在插件配置的 `session_configs` 模板列表中设置。
- `/随机本子`（别名 `/本子`、`/doujinshi`）按 `delivery.doujinshi_send_mode` 生成并发送随机本子 PDF 或 ZIP；所有平台均直接发送文件，不再使用合并转发；OneBot 群聊可按配置延迟撤回对应的普通文件消息

完整的命令说明见 [`docs/usage/commands.md`](./docs/usage/commands.md)。

### 管理配置

在 AstrBot 插件配置中修改全局参数、`safety` 黑白名单和 `session_configs` 会话覆盖，保存后重载插件生效。插件不再提供 Pages 页面、配置命令或配置修改工具。

业务操作使用 `/今日运势` 和 `/刷新运势 [我|本群|全局]`。刷新自己的运势时只返回确认，运势内容通过 `/今日运势` 查看。开启 `fortune.allow_user_refresh` 后普通用户可刷新自己的运势；本群刷新仍需管理员，全局刷新仍需超级管理员。运势关闭后，相关入口和后台预生成都停用。

“图片获取”的更多配置可关闭 LLM 工具或短语触发，也可用图片、本子、运势三种短语模板替换默认说法。命令不受这两个开关影响。“发送与撤回”的更多配置可关闭随机本子，阻止下载。独立的 `r18` 标签只影响本次图片请求，不能绕过当前会话的 SFW 分级。

### LLM 工具调用

- 支持通过大模型自动调用色图工具
- 需在 AstrBot 配置好 LLM 提供商

完整工具清单见 [`docs/usage/ai-tools.md`](./docs/usage/ai-tools.md)。

---

## 配置

配置依次为图片获取、发送与撤回、今日运势、会话设置、访问控制和图片来源高级设置。低频参数需打开“显示更多配置”后设置；关闭功能会隐藏相关输入，但不清空已有值。完整配置参考见 [`docs/usage/configuration.md`](./docs/usage/configuration.md)。

### 基础配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `api_type` | API 类型（lolicon / sexnyan / custom / all） | `lolicon` |
| `send_mode` | 色图发送模式（auto / image / forward） | `auto` |
| `doujinshi_send_mode` | 本子文件格式（pdf / archive） | `pdf` |
| `doujinshi_max_page` | 随机本子最大页数（`0` 表示不限） | `0` |
| `content_mode` | 内容模式（sfw / r18 / mix） | `sfw` |
| `max_count` | 单次最大图片数（1-10） | `10` |
| `exclude_ai` | 是否排除 AI 生成图片 | `true` |

### 发送与撤回

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `delivery.html_card_strategy` | 图片卡片发送方式（never / fallback / always） | `fallback` |
| `platform_transports` | 平台传输模板列表，可添加 NapCat 模板 | `[]` |
| `auto_revoke_targets` | 自动撤回内容列表（`setu` / `fortune` / `doujinshi`） | `["doujinshi"]` |
| `auto_revoke_scope` | 自动撤回范围（none / sfw / r18 / all） | `none` |
| `auto_revoke_delay` | 已启用内容共用的自动清理延迟（秒，`0` 全部关闭） | `30` |
| `r18_docx_mode` | R18 是否使用 Docx 封装 | `true` |

图片下载遇到短暂网络错误时会先按内部默认的 3 轮对同一 URL 做确认重试；发送接口超时或 OneBot/NapCat 类适配器未返回 message id 时会标记为可能仍在送达，不会立刻触发降级重复发图。旧版 `auto_revoke_r18` 会在启动时迁移为 `auto_revoke_scope`，迁移后不再作为公开配置项展示。

NapCat stream 上传的分块内容按 NapCat 协议仍为 base64 字符串；若 AstrBot 与 NapCat 共享同一图片目录，可在 `platform_transports` 添加 NapCat 模板，将共享目录加入 `local_file_allowed_roots` 并把 `local_file_mode` 设为 `always` 或 `fallback`，让直发模式通过 raw OneBot `file://` 路径绕过 AstrBot 标准链路的 base64 转换。

`auto_revoke_targets` 是单一内容列表，默认只含 `doujinshi`，因此色图和今日运势默认不撤回；按需加入 `setu` 或 `fortune`。色图加入后还须命中 `auto_revoke_scope`。三类内容共享 `auto_revoke_delay` 和 OneBot 可恢复队列；设置 `1800` 即为 30 分钟，设为 `0` 会关闭全部自动清理。随机本子无论选择 PDF 还是 ZIP 都以普通文件消息发送；OneBot/NapCat 群聊发送成功后会直接登记消息 ID，到期调用 `delete_msg`，不再反查群文件。所有任务保存于插件运行数据目录的 `revoke_tasks.json`，插件重启后仍按原到期时间继续执行。

### 模板覆盖

| 配置项 | 说明 |
|--------|------|
| `provider_overrides` | 覆盖 provider 默认参数 |
| `custom_api_configs` | 自定义图片 API 列表 |
| `tag_alias_templates` | 标签别名映射 |
| `session_configs` | 按完整会话标识覆盖色图、发送与运势背景参数 |

旧卡片配置会迁入 `delivery.html_card_strategy`，默认仍为 `fallback`。多图片源固定轮流使用，运势使用全局图片源，不再单独配置。

### 访问控制

在插件配置的 `safety` 模板列表中，按需添加“色图与随机本子”或“今日运势”。每条只有访问模式和 SID 黑白名单，按完整 SID 精确匹配；群聊规则对整个群生效，不再单独限制群内成员。

会话模板支持继承全局；运势模板的“单独设置背景标签”开启后，留空标签表示清除全局标签限制。详见[配置参考](./docs/usage/configuration.md#会话级覆盖)。

升级时会将旧会话数据一次性迁入插件配置。旧用户／群组裸 ID 权限无法推导完整 SID，存在非空名单或限制模式时会报错，需在插件配置中明确填写新的 SID 权限规则；原运行文件保留。迁移失败会阻止初始化；迁移完成后删除模板或清空名单不会恢复旧记录。旧自定义消息和调优参数停止生效，启动时会移除 `messages`、`message_overrides` 等旧键；失败与拒绝文案固定在代码中，发送成功不追加提示；`/刷新运势` 刷新自己时返回固定确认。

---

## 文档

- [`docs/usage/`](./docs/usage/README.md): 命令、配置、AI 工具说明
- [`docs/project/`](./docs/project/README.md): 项目定位、架构与设计取舍
- [`docs/dev/`](./docs/dev/README.md): 开发环境、测试、贡献与维护规则
- [`CHANGELOG.md`](./CHANGELOG.md): 版本变更记录

---

## 开源协议

 本项目基于 [AGPL](LICENSE) 协议开源。
