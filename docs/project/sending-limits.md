# 发送链路传输上限与多图诊断

本文记录 setu 图片发送在 OneBot / NapCat 链路上的两层发送限制实测数据，以及「多图发不出」的排查结论。修改 `src/infrastructure/sending/`（`image_sender.py`、`send_strategies.py`、`napcat_stream.py`）时优先参考本文。

> [!IMPORTANT]
> 数据采集：2026-06-12，dev runtime 本地 NapCat（反向 WS client 连 AstrBot `6199`，bot QQ `1357811947`，目标群 `772654791`）。组件版本：`aiocqhttp 1.4.4`、`hypercorn 0.18.0`、`quart 0.20.0`、`websockets 15.0.1`。NapCat 版本、NTQQ 协议与 ASGI 默认值后续都可能变动，引用前按当前 runtime 复测。
> 本文区分**已端到端实测确证**与**代码/默认值推断**两类结论，不把推断写成事实。

## 发送数据流

聊天命令 / LLM tool → `GetSetuImagesUseCase` → `ImageSender.send_images` → `resolve_send_mode` → `DirectSendStrategy` / `ForwardSendStrategy` → `context.send_message` → aiocqhttp 适配器 → `Node.to_dict()` / `_from_segment_to_dict()` 把每张图转成 `base64://` → 整个 `send_group_msg` / `send_group_forward_msg` action 作为**单个 WS 文本帧**经 Hypercorn 发往 NapCat。

关键事实：标准发送链路（`event.chain_result` → `context.send_message`）下，aiocqhttp 适配器 `_from_segment_to_dict` 对**每个 Image 段无条件 `convert_to_base64`**。这是框架层行为，插件内不能通过普通 `Comp.Image(file="file://...")` 绕开。可行逃逸口只有 `DirectSendStrategy._send_onebot_image_chain` 的 OneBot 直通：手工构造 dict 直接 `bot.send_group_msg`，不调 `convert_to_base64`。

## 两层限制模型（核心结论）

「多图发不出」由**两个相互独立**的瓶颈共同造成，互不替代：

| 层 | 机制 | direct（`send_group_msg`） | forward（`send_group_forward_msg`） |
| --- | --- | --- | --- |
| **WS 传输层** | 整个 action JSON 作为单个 WS 文本帧，由 websockets 库按**字节数**判定，**不看 action 名** | 单帧 ≈ 50 MiB 上限 | 单帧 ≈ 50 MiB 上限（与 direct **同一条线**） |
| **应用层 / NTQQ** | Q 协议对单条消息的聚合规则 | **单条最多 8 张图**，第 9 张起整条 Timeout 失败，与体积无关 | **每个 node 独立处理**，容量远大于 direct（17 node / 63 MB 应用层可成） |

要点：
- **forward 不受 8 张限制**（每 node 独立），是多图的正确发送形态；但整个 base64 action 仍受 ≈50 MiB WS 单帧上限。
- **direct 受双重限制**：既有 8 张硬上限，累计 base64 也受 50 MiB WS 帧上限。
- 两层都过不去时才真正发不出；任一层超限即失败。

## 实测数据汇总

| 链路环节 | 测试方式 | 实测结果 | 性质 |
| --- | --- | --- | --- |
| atri 原图体积 | 真实下载 `api.atri.rodeo/setu?size=original` | 单图 ~10 MB（base64 ~13.5 MB） | 实测 |
| **direct 张数梯度** | HTTP 旁路（绕 WS 帧限制），20s 间隔排除限流 | 2/4/6/**8 图 OK**；**9 图起 Timeout 失败**（9 图仅 9.88 MB，与体积无关，重复复现） | 实测 |
| **direct 体积**（少图大体积） | HTTP 旁路 | base64 单图 13.5 MB ✓、3 张 30 MB ✓ | 实测 |
| 多图 **http URL** 直发 | HTTP 旁路 | ✗ `EventChecker Failed`（retcode 200） | 实测 |
| **forward 应用层容量** | HTTP 旁路 | 8 node / 29 MB ✓；**17 node / 63 MB ✓**（远超 direct） | 实测 |
| direct 应用层（同体积对照） | HTTP 旁路 | 8 图 / 29 MB ✗ Timeout；17 图 / 63 MB ✗ Timeout | 实测 |
| Hypercorn WS server **发送方向**（AstrBot→NapCat） | 最小复现 server | 30 MB ✓（发送方向不设上限） | 实测 |
| Hypercorn WS server **接收方向**（NapCat→AstrBot） | 最小复现 server | 15 MB ✓ / 17 MB ✗ `1009`（默认 16 MiB） | 实测 |
| **NapCat WS client 入站上限（普通 action）** | 临时 WS 连接二分 | 48 MB ✓ / 52 MB ✗ `1009`（约 50 MiB） | 实测 |
| **NapCat WS client 入站上限（forward action）** | 临时 WS 连接，真实 `send_group_forward_msg` 帧 | 10/30/45/**48 MB 到达应用层**；**52/60 MB `1009` 断连**（≈50 MiB，与普通 action 一致） | 实测 |

## 结论

### 已确证

1. **direct 单条最多 8 张图**：第 9 张起整条 `send_group_msg` 在 NTQQ 侧 Timeout 失败，与 payload 体积无关（9 图 9.88 MB 仍失败，重复复现）。这是 setu「多图（>1）发不出」在 direct 模式下最常见的真凶。
2. **forward 每 node 独立，应用层容量大**：17 node / 63 MB 经 HTTP 旁路成功，远超 direct。多图应优先走合并转发。
3. **WS 单帧上限 ≈50 MiB，对 direct 和 forward 一致**：传输层按字节判帧，不看 action 名。forward 大帧实测 48 MB 到达 / 52 MB `1009` 断连，与普通 action 的 50 MiB 线完全吻合。
4. **Hypercorn 16 MiB 限制方向相反，不挡发图**：`websocket_max_message_size=16 MiB` 只作用在 server 接收方向（NapCat→AstrBot 事件上报）。早先「16 MiB 挡多图发送」的判断被双向 WS 实测推翻。
5. **瓶颈不在 NapCat/QQ 协议体积**：base64 30 MB 多图与转发经 HTTP 旁路均成功；体积墙在 WS 帧（≈50 MiB），张数墙在 NTQQ（8 张）。
6. **标准链路强制 base64**：`file:///` 本地图片经适配器序列化后变 `base64://`（实测）。卷隔离下传 `file:///` 路径会 `FileNotFoundError`（实测）。如果 AstrBot 与 NapCat 共享同一路径（例如都能读取 `/AstrBot/data`），则可通过 raw OneBot 直通发送受信任 `file://` 路径，绕过标准链路 base64。
7. **stream 引用 + 合并转发组合必崩**：`Node.to_dict()` 对 `stream://` 或服务端绝对路径强制 `convert_to_base64`，抛 `Exception: not a valid file`（用真实 `Comp.Node` 实测）。stream 上传回退在 forward 模式 100% 失败，只在 direct 模式（走 OneBot 直通）有效。

### 与生产现象的关系

本地实测给出两条明确的墙，足以解释「1 张能发、多图发不出」：

- **direct 模式**：>8 张直接触发 NTQQ Timeout；即使少于 8 张，多张原图累计 base64 也可能撞 50 MiB WS 帧墙。
- **forward 模式**：突破 8 张限制，但多张原图 base64 累计超 ≈50 MiB 时撞 WS 帧墙被 `1009` 丢弃，整条转发发不出。

> 本地"同一台 mac、不同 user-data-dir"不等于文件系统隔离：本地 NapCat 能读 AstrBot 写的任何路径。涉及卷隔离的结论不能从本地实测外推到生产。生产若用 Docker 卷隔离，`file:///` 路径失效是额外的独立失败点。

## 对发送策略的影响

**当前发送策略：**

- **多图优先 forward**：`send_mode` 默认 `auto`，多图（>1）且平台支持时自动走合并转发；`resolve_send_mode` 增加 `supports_forward` 检查，不支持的平台自动回退 `image`。
- **控制单帧体积**：
  - 新增 `compress_enabled`（默认 `false`）和 `compress_max_mb`（默认 4）配置项，开启后发送前对超限图片压缩（JPEG 质量阶梯 + 必要时缩放）。
  - 分批逻辑：根据 base64 估算值和 40 MiB 安全线自动分批；`direct` 模式每批 ≤8 张且 ≤40 MiB，`forward` 模式每批仅受 40 MiB 约束。
- **forward 死路规避**：`_send_one_batch` 的 stream 回退仅在 `effective_mode != "forward"` 时启用；forward 失败保留实际发送错误。
- **`uin` 校验**：`ForwardSendStrategy._build_forward_nodes` 中 `event.get_self_id()` 为空时记 warning，保留空字符串避免序列化崩溃。
- **direct + 本地 file:// 直通（可选）**：新增 `delivery.platform_transports`，其中 NapCat 模板包含 `local_file_mode`（默认 `disabled`）和 `local_file_allowed_roots`。仅 OneBot/NapCat 类平台、直发模式、真实文件且路径位于发送缓存目录或显式共享目录时，才走 raw OneBot `file://` 直通。
- **stream 分块固定**：NapCat stream 单块原始字节大小为 64 KiB，`chunk_data` 仍为 base64 字符串。传输模式和本地路径白名单继续通过平台模板设置。
- **自动撤回需要 message_id**：`auto_revoke_targets` 包含 `setu` 且 `auto_revoke_scope` 命中时，OneBot/NapCat 类平台的 direct、stream、file:// 直通、forward 和 R18 Docx 会优先走 raw OneBot action 以提取 `message_id`。目标列表包含 `fortune` 时，今日运势也会走同一消息撤回队列；包含 `doujinshi` 时，本子 PDF/ZIP 普通文件也会直接取得其消息 ID，而非反查群文件。拿不到 id、平台不支持 `delete_msg` 或删除失败时只记录 warning，不触发重复发送或阻断发图；成功登记的撤回任务写入 `db.sqlite` 的 `setu_schedule_task` 表，重启后仍会恢复。
- **raw 文件 URI**：本子普通文件直发绕过 aiocqhttp 常规消息段适配时，会将绝对本地路径转换为 `file://` URI；否则 NapCat 可能返回消息 ID，但 QQ 客户端打开附件时显示下载失败。

**未实现（计划或待验证）：**

- **非 base64 stream**：NapCat 当前 stream API 接收 `chunk_data` base64 字符串，插件内不能改成二进制流。若要真正非 base64 stream，需要改 NapCat API 或新增 AstrBot/NapCat 共同支持的传输接口。
- **regular 默认图尺寸**：`ProviderConfig.image_size` 默认已改为 `REGULAR`（v2.0.3），降低原图体积风险；但未强制所有 provider 使用 regular。

## 复现方法

实测脚本不入库（含临时改 NapCat OB11 网络配置、向真实群发图，均测后还原）。复现要点：

- NapCat WebUI（`16099`）登录换 Credential：`hash = sha256(token + ".napcat")`，POST `/api/auth/login` 字段名 `hash`，返回 base64 `Credential`；凭证有效期 1 小时（`MAX_CREDENTIAL_VALID_SECONDS`），过期自助重登。
- 通过 `/api/OB11Config/SetConfig`（`config` 字段须为 JSON **字符串**）临时加 httpServer 或 wsClient，测完移除并校验 `websocketClients` 还原为仅 `astrbot` 一条、`httpServers` 为空。
- 应用层容量测试走 HTTP 旁路（绕 WS 帧限制）；WS 帧上限用临时 NapCat client 指向本地 WS server 二分逼近。
- direct 张数梯度测试须留 ≥20s 间隔排除 QQ 限流干扰。
- forward 帧 padding 用真实 `send_group_forward_msg` 结构承载，区分 `1009`（传输层丢帧）与应用层 retcode（帧已到达）。

更多 sender 结构见 `architecture.md` 的「核心运行链路」。

## Base64 图片

运势渲染或 `Image.fromBytes()` 生成的 `base64://` 图片直接解码用于体积估算和压缩。普通路径与本地 `file://` URI 继续支持，URI 中的转义字符按路径解码。普通图片发送已移除 HTML 卡片包装，t2i 只用于运势渲染。
