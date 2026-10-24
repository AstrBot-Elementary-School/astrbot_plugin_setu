"""Setu 插件的领域枚举。"""

from __future__ import annotations

from enum import Enum


class ContentMode(str, Enum):
    """内容分级模式。"""

    SFW = "sfw"
    R18 = "r18"
    MIX = "mix"


class SendMode(str, Enum):
    """图片发送模式。"""

    IMAGE = "image"
    FORWARD = "forward"
    AUTO = "auto"


class HtmlCardStrategy(str, Enum):
    """HTML 卡片策略。"""

    NEVER = "never"
    FALLBACK = "fallback"
    ALWAYS = "always"


class ApiType(str, Enum):
    """API 提供商类型。"""

    LOLICON = "lolicon"
    SEXNYAN = "sexnyan"
    CUSTOM = "custom"
    ALL = "all"


class MultiApiStrategy(str, Enum):
    """多 API 策略。"""

    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    FAILOVER = "failover"


class AccessControlMode(str, Enum):
    """访问控制模式。"""

    NONE = "none"
    BLACKLIST = "blacklist"
    WHITELIST = "whitelist"
