"""内置提示及占位符解析；不接受用户覆盖。"""

from __future__ import annotations

from typing import Any, ClassVar


class MessagesConfig:
    """集中管理插件内置提示。"""

    TEXTS: ClassVar[dict[str, str]] = {
        "feature_disabled": "{feature}已停用",
        "r18_not_allowed": "当前会话仅允许 SFW 图片，请去掉 r18 标签",
        "access_denied": "当前会话无权使用此功能",
        "send_failed": "图片发送失败，请稍后再试。",
        "rate_limited": "上一个请求还在处理中，请稍候。",
        "config_not_loaded": "配置未加载",
        "invalid_count": "数量解析失败，图片数量必须在{min_count}-{max_count}之间",
        "fetch_timeout": "获取图片超时，网络可能不稳定，请稍后再试。",
        "fetch_failed": "获取图片失败，请稍后再试",
        "doujinshi_failed": "随机本子获取或文件生成失败，请稍后再试。",
        "no_result": "没有找到符合条件的图片。{tags_info}",
        "empty_payload": "这次没有获取到图片，请稍后再试。",
        "r18_docx_failed": "R18 Docx 封装失败，请稍后再试或联系管理员。",
    }

    @classmethod
    def resolve_message(cls, key: str, **kwargs: Any) -> str | None:
        text = cls.TEXTS.get(key)
        if text is None:
            return None
        for name, value in kwargs.items():
            text = text.replace(f"{{{name}}}", str(value))
        return text or None
