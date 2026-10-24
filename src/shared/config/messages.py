"""内置提示及占位符解析；不接受用户覆盖。"""

from __future__ import annotations

from typing import Any, ClassVar


class MessagesConfig:
    """集中管理插件内置提示。"""

    TEXTS: ClassVar[dict[str, str]] = {
        "feature_disabled": "{feature}已停用",
        "r18_not_allowed": "当前会话仅允许 SFW 图片，不能使用 r18 标记",
        "access_denied": "当前会话无权使用此功能",
        "fetching": "正在获取图片，请稍候...",
        "found": "找到 {count} 张符合要求的图片~",
        "send_failed": "图片发送失败，请稍后再试。",
        "revoke_scheduled": "已设置自动撤回，将在 {revoke_delay} 秒后撤回。",
        "rate_limited": "你有一个请求正在处理中，请稍后再试~",
        "config_not_loaded": "配置未加载",
        "error_invalid_request": "请求参数无效",
        "error_internal_server": "服务器内部错误",
        "invalid_count": "数量解析失败，图片数量必须在{min_count}-{max_count}之间",
        "max_count_exceeded": "一次最多只能获取{max_count}张哦~",
        "count_out_of_range": "图片数量必须在{min_count}-{max_count}之间哦~",
        "fetch_timeout": "获取图片超时，网络可能不稳定，请稍后再试。",
        "fetch_failed": "获取图片失败，请稍后再试",
        "doujinshi_fetching": "正在获取随机本子并生成文件，请稍候...",
        "doujinshi_failed": "随机本子获取或文件生成失败，请稍后再试。",
        "no_result": "未找到{tags_info}符合要求的图片~",
        "empty_payload": "运气不好，一张图都没拿到...",
        "r18_docx_failed": "R18 Docx 封装失败，请稍后再试或联系管理员。",
        "fortune_group_only": "此命令仅支持群聊",
        "fortune_image_submitted": "已提交今日运势图。\n{fortune}",
        "fortune_image_failed": "运势图未能发送，以下为文字运势：\n{fortune}",
        "fortune_get_failed": "获取运势失败: {error}",
        "fortune_refresh_failed": "刷新运势失败: {error}",
        "fortune_refresh_group_failed": "刷新群运势失败: {error}",
        "fortune_refresh_all_failed": "刷新全局运势失败: {error}",
        "fortune_refresh_group_done": "已刷新本群 {count} 位用户的今日运势",
        "fortune_refresh_all_done": "已刷新全局 {count} 位用户的今日运势",
    }

    @classmethod
    def resolve_message(cls, key: str, **kwargs: Any) -> str | None:
        text = cls.TEXTS.get(key.replace(".", "_"))
        if text is None:
            return None
        for name, value in kwargs.items():
            text = text.replace(f"{{{name}}}", str(value))
        return text or None
