"""Pydantic v2 configuration models for Setu plugin.

Replaces the ConfigBase + mixin chain with type-safe, validated models.
Each section mirrors the _conf_schema.json structure for WebUI compatibility.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ImageSize(str, Enum):
    """Valid image sizes for Lolicon/Atri APIs."""

    ORIGINAL = "original"
    REGULAR = "regular"
    SMALL = "small"
    THUMB = "thumb"
    MINI = "mini"


class AspectRatio(str, Enum):
    """Valid aspect ratios for filtering."""

    HORIZONTAL = "horizontal"
    VERTICAL = "vertical"
    SQUARE = "square"


class ContentModeStr(str, Enum):
    """Content rating modes."""

    SFW = "sfw"
    R18 = "r18"
    MIX = "mix"


class ApiTypeStr(str, Enum):
    """API provider types."""

    LOLICON = "lolicon"
    ATRI = "atri"
    SEXNYAN = "sexnyan"
    CUSTOM = "custom"
    ALL = "all"


class MultiApiStrategyStr(str, Enum):
    """Multi-API strategy types."""

    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    FAILOVER = "failover"


class SendModeStr(str, Enum):
    """Image send modes."""

    IMAGE = "image"
    FORWARD = "forward"
    AUTO = "auto"


class DoujinshiSendModeStr(str, Enum):
    """随机本子文件生成模式。"""

    PDF = "pdf"
    ARCHIVE = "archive"


class AutoRevokeScopeStr(str, Enum):
    """Content scopes that should be auto-revoked after Setu sends."""

    NONE = "none"
    SFW = "sfw"
    R18 = "r18"
    ALL = "all"


class AutoRevokeTargetStr(str, Enum):
    """Content types that can enter the shared auto-revoke scheduler."""

    SETU = "setu"
    FORTUNE = "fortune"
    DOUJINSHI = "doujinshi"


def should_auto_revoke(scope: str | AutoRevokeScopeStr, is_r18: bool) -> bool:
    """Return whether a Setu payload should be auto-revoked for this scope."""
    normalized = str(scope.value if isinstance(scope, AutoRevokeScopeStr) else scope)
    if normalized == AutoRevokeScopeStr.ALL.value:
        return True
    if normalized == AutoRevokeScopeStr.R18.value:
        return is_r18
    if normalized == AutoRevokeScopeStr.SFW.value:
        return not is_r18
    return False


class NapcatStreamModeStr(str, Enum):
    """NapCat stream upload modes."""

    DISABLED = "disabled"
    FALLBACK = "fallback"
    ALWAYS = "always"


class NapcatLocalFileModeStr(str, Enum):
    """NapCat local file passthrough modes."""

    DISABLED = "disabled"
    FALLBACK = "fallback"
    ALWAYS = "always"


class HtmlCardStrategyStr(str, Enum):
    """HTML card strategies."""

    NEVER = "never"
    FALLBACK = "fallback"
    ALWAYS = "always"


class AccessControlModeStr(str, Enum):
    """Access control modes."""

    NONE = "none"
    BLACKLIST = "blacklist"
    WHITELIST = "whitelist"


class ProviderConfig(BaseModel):
    """Configuration for a single API provider (Lolicon or Atri)."""

    image_size: ImageSize = ImageSize.REGULAR
    proxy: str = ""
    aspect_ratio: AspectRatio | None = None
    uid: list[int] = Field(default_factory=list)
    keyword: str = ""
    exclude_ai: bool = True

    @field_validator("aspect_ratio", mode="before")
    @classmethod
    def normalize_empty_aspect_ratio(cls, value: Any) -> Any:
        """Treat empty-string aspect ratio from schema/config files as None."""
        if value == "":
            return None
        return value


class CustomApiConfig(BaseModel):
    """Custom API configuration."""

    name: str = "My custom API"
    url: str = ""
    method: str = "GET"
    timeout: int = 30
    parser_type: str = "auto"
    json_path: str = ""


class ProviderOverrideConfig(ProviderConfig):
    """Provider config supplied via template_list (carries its template key)."""

    model_config = ConfigDict(populate_by_name=True)

    template_key: str = Field("", alias="__template_key")


class TagAliasTemplateConfig(BaseModel):
    """Optional tag alias mapping from template_list."""

    model_config = ConfigDict(populate_by_name=True)

    template_key: str = Field("", alias="__template_key")
    canonical: str = ""
    aliases: list[str] = Field(default_factory=list)


class PlatformTransportConfig(BaseModel):
    """Optional platform transport config supplied via template_list."""

    model_config = ConfigDict(populate_by_name=True)

    template_key: str = Field("", alias="__template_key")
    stream_mode: NapcatStreamModeStr = NapcatStreamModeStr.FALLBACK
    stream_chunk_kb: int = Field(default=64, ge=1)
    local_file_mode: NapcatLocalFileModeStr = NapcatLocalFileModeStr.DISABLED
    local_file_allowed_roots: list[str] = Field(default_factory=list)


class SetuGeneralConfig(BaseModel):
    """Setu general configuration."""

    api_type: ApiTypeStr = ApiTypeStr.LOLICON
    multi_api_strategy: MultiApiStrategyStr = MultiApiStrategyStr.ROUND_ROBIN
    content_mode: ContentModeStr = ContentModeStr.SFW
    max_count: int = Field(default=10, ge=1, le=10)
    max_replenish_rounds: int = Field(default=3, ge=1, le=3)
    tag_alias_templates: list[TagAliasTemplateConfig] = Field(default_factory=list)


class DeliveryConfig(BaseModel):
    """消息发送与自动清理配置。"""

    send_mode: SendModeStr = SendModeStr.AUTO
    doujinshi_send_mode: DoujinshiSendModeStr = DoujinshiSendModeStr.PDF
    doujinshi_max_page: int = Field(default=0, ge=0)
    r18_docx_mode: bool = True
    auto_revoke_scope: AutoRevokeScopeStr = AutoRevokeScopeStr.NONE
    auto_revoke_targets: list[AutoRevokeTargetStr] = Field(
        default_factory=lambda: [AutoRevokeTargetStr.DOUJINSHI]
    )
    auto_revoke_delay: int = Field(default=30, ge=0)
    platform_transports: list[PlatformTransportConfig] = Field(default_factory=list)
    # 兼容旧版平铺 NapCat 配置；新配置入口是 platform_transports 模板。
    napcat_stream_mode: NapcatStreamModeStr = NapcatStreamModeStr.FALLBACK
    napcat_stream_chunk_kb: int = Field(default=64, ge=1)
    napcat_local_file_mode: NapcatLocalFileModeStr = NapcatLocalFileModeStr.DISABLED
    napcat_local_file_allowed_roots: list[str] = Field(default_factory=list)
    compress_enabled: bool = False
    compress_max_mb: int = Field(default=4, ge=1, le=30)


class HtmlCardConfig(BaseModel):
    """HTML card wrapping configuration."""

    strategy: HtmlCardStrategyStr = HtmlCardStrategyStr.FALLBACK
    mode: str = "single"
    card_padding: int = Field(default=6, ge=0, le=30)
    card_gap: int = Field(default=6, ge=0, le=30)


class FeatureConfig(BaseModel):
    """Global feature switch, enabled by default for existing installations."""

    enabled: bool = True


class TriggerConfig(BaseModel):
    """Natural-language routing; explicit commands remain available."""

    natural_language_enabled: bool = True


class FortuneConfig(BaseModel):
    """Fortune (Today's Luck) configuration."""

    enabled: bool = True
    api_type: str = "inherit"
    tags: str = ""
    content_mode: ContentModeStr = ContentModeStr.SFW
    allow_user_refresh: bool = False
    auto_refresh: bool = True


class CacheConfig(BaseModel):
    """Disk cache used before adapter-level image sending."""

    enabled: bool = True
    ttl_hours: int = Field(default=2, ge=1, le=168)
    max_items: int = Field(default=200, ge=1, le=1000)
    cleanup_on_start: bool = True


class MessagesFetchingConfig(BaseModel):
    """Fetching message configuration."""

    enabled: bool = True
    text: str = "正在获取图片，请稍候..."


class MessagesFoundConfig(BaseModel):
    """Found message configuration."""

    enabled: bool = True
    text: str = "找到 {count} 张符合要求的图片~"


class MessagesSendFailedConfig(BaseModel):
    """Send failed message configuration."""

    enabled: bool = True
    text: str = "图片发送失败，请稍后再试。"


class MessageTextConfig(BaseModel):
    """Generic user-facing message configuration."""

    enabled: bool = True
    text: str = ""


class MessageOverrideConfig(BaseModel):
    """Optional user-facing message override from template_list."""

    model_config = ConfigDict(populate_by_name=True)

    template_key: str = Field("", alias="__template_key")
    message_key: str = "fetching"
    enabled: bool = True
    text: str = "正在获取图片，请稍候..."


class MessagesConfig(BaseModel):
    """User-facing message configuration."""

    _DEFAULT_TEXTS: ClassVar[dict[str, str]] = {
        "fetching": "正在获取图片，请稍候...",
        "found": "找到 {count} 张符合要求的图片~",
        "send_failed": "图片发送失败，请稍后再试。",
        "revoke_scheduled": "已设置自动撤回，将在 {revoke_delay} 秒后撤回。",
        "rate_limited": "你有一个请求正在处理中，请稍后再试~",
        "config_not_loaded": "配置未加载",
        "feature_disabled": "{feature}功能已关闭，请联系管理员。",
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
        "fortune_missing_user_id": "请指定用户ID",
        "fortune_get_failed": "获取运势失败: {error}",
        "fortune_refresh_failed": "刷新运势失败: {error}",
        "fortune_refresh_group_failed": "刷新群运势失败: {error}",
        "fortune_refresh_all_failed": "刷新全局运势失败: {error}",
        "fortune_refresh_group_done": "已刷新本群 {count} 位用户的今日运势",
        "fortune_refresh_all_done": "已刷新全局 {count} 位用户的今日运势",
        "fortune_enabled_group_done": "运势功能已开启",
        "fortune_disabled_group_done": "运势功能已关闭",
        "fortune_block_user_done": "用户 {user_id} 已添加到运势黑名单",
        "fortune_unblock_user_done": "用户 {user_id} 已从运势黑名单移除",
        "fortune_trust_user_done": "用户 {user_id} 已添加到运势白名单",
        "fortune_untrust_user_done": "用户 {user_id} 已从运势白名单移除",
    }

    @model_validator(mode="before")
    @classmethod
    def fill_missing_message_text(cls, data: Any) -> Any:
        """Fill default text when a message object omits the text field."""
        if not isinstance(data, dict):
            return data
        patched = dict(data)
        for key, default_text in cls._DEFAULT_TEXTS.items():
            value = patched.get(key)
            if isinstance(value, dict) and "text" not in value:
                patched[key] = {**value, "text": default_text}
        return patched

    message_overrides: list[MessageOverrideConfig] = Field(default_factory=list)
    feature_disabled: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="{feature}功能已关闭，请联系管理员。")
    )
    fetching: MessagesFetchingConfig = Field(default_factory=MessagesFetchingConfig)
    found: MessagesFoundConfig = Field(default_factory=MessagesFoundConfig)
    send_failed: MessagesSendFailedConfig = Field(
        default_factory=MessagesSendFailedConfig
    )
    revoke_scheduled: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="已设置自动撤回，将在 {revoke_delay} 秒后撤回。"
        )
    )
    rate_limited: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="你有一个请求正在处理中，请稍后再试~"
        )
    )
    config_not_loaded: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="配置未加载")
    )
    error_invalid_request: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="请求参数无效")
    )
    error_internal_server: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="服务器内部错误")
    )
    invalid_count: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="数量解析失败，图片数量必须在{min_count}-{max_count}之间"
        )
    )
    max_count_exceeded: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="一次最多只能获取{max_count}张哦~"
        )
    )
    count_out_of_range: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="图片数量必须在{min_count}-{max_count}之间哦~"
        )
    )
    fetch_timeout: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="获取图片超时，网络可能不稳定，请稍后再试。"
        )
    )
    fetch_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="获取图片失败，请稍后再试")
    )
    doujinshi_fetching: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="正在获取随机本子并生成文件，请稍候..."
        )
    )
    doujinshi_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="随机本子获取或文件生成失败，请稍后再试。"
        )
    )
    no_result: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="未找到{tags_info}符合要求的图片~"
        )
    )
    empty_payload: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="运气不好，一张图都没拿到...")
    )
    r18_docx_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="R18 Docx 封装失败，请稍后再试或联系管理员。"
        )
    )
    fortune_group_only: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="此命令仅支持群聊")
    )
    fortune_missing_user_id: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="请指定用户ID")
    )
    fortune_get_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="获取运势失败: {error}")
    )
    fortune_refresh_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="刷新运势失败: {error}")
    )
    fortune_refresh_group_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="刷新群运势失败: {error}")
    )
    fortune_refresh_all_failed: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="刷新全局运势失败: {error}")
    )
    fortune_refresh_group_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="已刷新本群 {count} 位用户的今日运势"
        )
    )
    fortune_refresh_all_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="已刷新全局 {count} 位用户的今日运势"
        )
    )
    fortune_enabled_group_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="运势功能已开启")
    )
    fortune_disabled_group_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(text="运势功能已关闭")
    )
    fortune_block_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已添加到运势黑名单"
        )
    )
    fortune_unblock_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已从运势黑名单移除"
        )
    )
    fortune_trust_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已添加到运势白名单"
        )
    )
    fortune_untrust_user_done: MessageTextConfig = Field(
        default_factory=lambda: MessageTextConfig(
            text="用户 {user_id} 已从运势白名单移除"
        )
    )


class SafetyConfig(BaseModel):
    """Safety and access control configuration."""

    setu_user_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    setu_group_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    setu_blocked_users: list[str] = Field(default_factory=list)
    setu_whitelist_users: list[str] = Field(default_factory=list)
    setu_blocked_groups: list[str] = Field(default_factory=list)
    setu_whitelist_groups: list[str] = Field(default_factory=list)
    fortune_user_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    fortune_group_access_control_mode: AccessControlModeStr = AccessControlModeStr.NONE
    fortune_blocked_users: list[str] = Field(default_factory=list)
    fortune_whitelist_users: list[str] = Field(default_factory=list)
    fortune_blocked_groups: list[str] = Field(default_factory=list)
    fortune_whitelist_groups: list[str] = Field(default_factory=list)


class SessionTemplateItem(BaseModel):
    """Session configuration template item."""

    session_id: str = ""
    session_type: str = "group"
    content_mode: str = ""
    r18_docx_mode: str = ""
    auto_revoke_scope: str = ""
    send_mode: str = ""


class FortuneSessionTemplateItem(BaseModel):
    """Fortune session configuration template item."""

    session_id: str = ""
    session_type: str = "group"
    tags: str = ""
    content_mode: str = ""


class ApiSectionConfig(BaseModel):
    """API section configuration."""

    provider_overrides: list[ProviderOverrideConfig] = Field(default_factory=list)
    custom_api_configs: list[CustomApiConfig] = Field(default_factory=list)


class SetuPluginConfig(BaseModel):
    """Root Pydantic model for Setu plugin configuration.

    This replaces the ConfigBase + mixin chain with a single validated model.
    The structure mirrors _conf_schema.json for WebUI compatibility.

    The model can be instantiated directly from AstrBotConfig dict:
        config = SetuPluginConfig(**astrbot_config)
    """

    setu_general: SetuGeneralConfig = Field(default_factory=SetuGeneralConfig)
    doujinshi: FeatureConfig = Field(default_factory=FeatureConfig)
    llm_tools: FeatureConfig = Field(default_factory=FeatureConfig)
    triggers: TriggerConfig = Field(default_factory=TriggerConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    html_card: HtmlCardConfig = Field(default_factory=HtmlCardConfig)
    fortune: FortuneConfig = Field(default_factory=FortuneConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    api: ApiSectionConfig = Field(default_factory=ApiSectionConfig)
    messages: MessagesConfig = Field(default_factory=MessagesConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    session_configs: list[SessionTemplateItem] = Field(default_factory=list)
    fortune_session_configs: list[FortuneSessionTemplateItem] = Field(
        default_factory=list
    )

    @field_validator("session_configs")
    @classmethod
    def validate_session_configs(
        cls, v: list[SessionTemplateItem]
    ) -> list[SessionTemplateItem]:
        """Validate session configurations."""
        for item in v:
            if item.session_type not in ("group", "private"):
                raise ValueError(f"Invalid session_type: {item.session_type}")
        return v

    @field_validator("fortune_session_configs")
    @classmethod
    def validate_fortune_session_configs(
        cls, v: list[FortuneSessionTemplateItem]
    ) -> list[FortuneSessionTemplateItem]:
        """Validate fortune session configurations."""
        for item in v:
            if item.session_type not in ("group", "private"):
                raise ValueError(f"Invalid session_type: {item.session_type}")
        return v

    # Convenience properties for backward compatibility
    @property
    def api_type(self) -> str:
        """Get API type."""
        return self.setu_general.api_type.value

    @property
    def multi_api_strategy(self) -> str:
        """Get multi-API strategy."""
        return self.setu_general.multi_api_strategy.value

    @property
    def content_mode(self) -> str:
        """Get content mode."""
        return self.setu_general.content_mode.value

    @property
    def max_count(self) -> int:
        """Get max count."""
        return self.setu_general.max_count

    @property
    def max_replenish_rounds(self) -> int:
        """Get max replenish rounds."""
        return self.setu_general.max_replenish_rounds

    @property
    def tag_alias(self) -> str:
        """Get tag alias string derived from tag_alias_templates."""
        lines = []
        for item in self.setu_general.tag_alias_templates:
            canonical = item.canonical.strip()
            aliases = [
                str(alias).strip() for alias in item.aliases if str(alias).strip()
            ]
            if canonical and aliases:
                lines.append(f"{canonical}={','.join(aliases)}")
        return "\n".join(lines)

    @property
    def send_mode(self) -> str:
        """Get send mode."""
        return self.delivery.send_mode.value

    @property
    def doujinshi_send_mode(self) -> str:
        """Get random doujinshi file generation mode."""
        return self.delivery.doujinshi_send_mode.value

    @property
    def doujinshi_max_page(self) -> int:
        """Get random doujinshi max page filter; 0 表示不限页数。"""
        return self.delivery.doujinshi_max_page

    @property
    def r18_docx_mode(self) -> bool:
        """Get R18 DOCX mode."""
        return self.delivery.r18_docx_mode

    @property
    def auto_revoke_scope(self) -> str:
        """Get auto-revoke content scope."""
        return self.delivery.auto_revoke_scope.value

    @property
    def auto_revoke_r18(self) -> bool:
        """Compatibility view: true when the current scope revokes R18."""
        return should_auto_revoke(self.delivery.auto_revoke_scope, is_r18=True)

    @property
    def auto_revoke_delay(self) -> int:
        """Get auto-revoke delay."""
        return self.delivery.auto_revoke_delay

    @property
    def auto_revoke_setu_enabled(self) -> bool:
        """Return whether Setu image sends may enter auto-revoke scheduling."""
        return AutoRevokeTargetStr.SETU in self.delivery.auto_revoke_targets

    @property
    def auto_revoke_fortune_enabled(self) -> bool:
        """Return whether today's-fortune responses may enter auto-revoke scheduling."""
        return AutoRevokeTargetStr.FORTUNE in self.delivery.auto_revoke_targets

    @property
    def auto_revoke_doujinshi_enabled(self) -> bool:
        """Return whether random doujinshi group files may enter cleanup scheduling."""
        return AutoRevokeTargetStr.DOUJINSHI in self.delivery.auto_revoke_targets

    @property
    def doujinshi_file_cleanup_delay(self) -> int:
        """兼容旧调用方：本子清理由统一撤回延迟控制。"""
        return self.delivery.auto_revoke_delay

    @property
    def napcat_stream_mode(self) -> str:
        """Get NapCat stream upload mode."""
        transport = self._platform_transport("napcat")
        if transport is not None:
            return transport.stream_mode.value
        return self.delivery.napcat_stream_mode.value

    @property
    def napcat_stream_chunk_kb(self) -> int:
        """Get NapCat stream upload chunk size in KiB."""
        transport = self._platform_transport("napcat")
        if transport is not None:
            return transport.stream_chunk_kb
        return self.delivery.napcat_stream_chunk_kb

    @property
    def napcat_local_file_mode(self) -> str:
        """Get NapCat local file passthrough mode."""
        transport = self._platform_transport("napcat")
        if transport is not None:
            return transport.local_file_mode.value
        return self.delivery.napcat_local_file_mode.value

    @property
    def napcat_local_file_allowed_roots(self) -> list[str]:
        """Get extra local roots allowed for NapCat file passthrough."""
        transport = self._platform_transport("napcat")
        if transport is not None:
            return list(transport.local_file_allowed_roots)
        return list(self.delivery.napcat_local_file_allowed_roots)

    @property
    def compress_enabled(self) -> bool:
        """Get whether pre-send image compression is enabled."""
        return self.delivery.compress_enabled

    @property
    def compress_max_mb(self) -> int:
        """Get per-image compression target size in MiB."""
        return self.delivery.compress_max_mb

    @property
    def html_card_strategy(self) -> str:
        """Get HTML card strategy."""
        return self.html_card.strategy.value

    @property
    def html_card_padding(self) -> int:
        """Get HTML card padding."""
        return self.html_card.card_padding

    @property
    def html_card_gap(self) -> int:
        """Get HTML card gap."""
        return self.html_card.card_gap

    @property
    def cache_enabled(self) -> bool:
        """Get cache enabled."""
        return self.cache.enabled

    @property
    def cache_ttl_hours(self) -> int:
        """Get cache TTL hours."""
        return self.cache.ttl_hours

    @property
    def cache_max_items(self) -> int:
        """Get cache max items."""
        return self.cache.max_items

    @property
    def cache_cleanup_on_start(self) -> bool:
        """Get cache cleanup on start."""
        return self.cache.cleanup_on_start

    @property
    def exclude_ai(self) -> bool:
        """Get exclude AI."""
        provider = "atri" if self.api_type == "atri" else "lolicon"
        return self._provider_config(provider).exclude_ai

    @property
    def image_size(self) -> str:
        """Get image size."""
        return self._provider_config("lolicon").image_size.value

    @property
    def proxy(self) -> str:
        """Get proxy."""
        return self._provider_config("lolicon").proxy

    @property
    def aspect_ratio(self) -> str:
        """Get aspect ratio."""
        config = self._provider_config("lolicon")
        return config.aspect_ratio.value if config.aspect_ratio else ""

    @property
    def uid(self) -> list[int]:
        """Get UID list."""
        return self._provider_config("lolicon").uid

    @property
    def keyword(self) -> str:
        """Get keyword."""
        return self._provider_config("lolicon").keyword

    @property
    def atri_image_size(self) -> str:
        """Get Atri image size."""
        return self._provider_config("atri").image_size.value

    @property
    def atri_proxy(self) -> str:
        """Get Atri proxy."""
        return self._provider_config("atri").proxy

    @property
    def atri_aspect_ratio(self) -> str:
        """Get Atri aspect ratio."""
        config = self._provider_config("atri")
        return config.aspect_ratio.value if config.aspect_ratio else ""

    @property
    def atri_uid(self) -> list[int]:
        """Get Atri UID list."""
        return self._provider_config("atri").uid

    @property
    def atri_keyword(self) -> str:
        """Get Atri keyword."""
        return self._provider_config("atri").keyword

    @property
    def atri_exclude_ai(self) -> bool:
        """Get Atri exclude AI."""
        return self._provider_config("atri").exclude_ai

    @property
    def sexnyan_proxy(self) -> str:
        """Get SexNyan proxy."""
        return self._provider_config("sexnyan").proxy

    @property
    def sexnyan_uid(self) -> list[int]:
        """Get SexNyan author UID list."""
        return self._provider_config("sexnyan").uid

    @property
    def sexnyan_keyword(self) -> str:
        """Get SexNyan keyword."""
        return self._provider_config("sexnyan").keyword

    @property
    def fortune_api_type(self) -> str:
        """Get fortune API type."""
        return self.fortune.api_type

    @property
    def custom_api(self) -> dict[str, Any]:
        """Get custom API config."""
        if self.api.custom_api_configs:
            cfg = self.api.custom_api_configs[0]
            return {
                "url": cfg.url,
                "method": cfg.method,
                "timeout": cfg.timeout,
            }
        return {"url": "", "method": "GET", "timeout": 30}

    @property
    def api_response_parser(self) -> dict[str, Any]:
        """Get API response parser config."""
        if self.api.custom_api_configs:
            cfg = self.api.custom_api_configs[0]
            return {
                "type": cfg.parser_type,
                "json_path": cfg.json_path,
            }
        return {"type": "auto", "json_path": ""}

    @property
    def custom_api_configs(self) -> list[dict[str, Any]]:
        """Get custom API configs."""
        return [cfg.model_dump() for cfg in self.api.custom_api_configs]

    def get_custom_api_config(self, name: str | None = None) -> dict[str, Any] | None:
        """Get custom API config by name."""
        configs = self.api.custom_api_configs
        if not configs:
            return None
        if name:
            for cfg in configs:
                if cfg.name == name:
                    return cfg.model_dump()
            return None
        return configs[0].model_dump()

    def _provider_config(self, provider: str) -> ProviderConfig:
        """Return provider config from matching template, else built-in defaults."""
        for item in self.api.provider_overrides:
            if item.template_key == provider:
                return item
        return ProviderConfig()

    def _platform_transport(self, platform: str) -> PlatformTransportConfig | None:
        """Return platform transport config from matching template."""
        for item in self.delivery.platform_transports:
            if item.template_key == platform:
                return item
        return None

    @property
    def msg_fetching_enabled(self) -> bool:
        """Get fetching message enabled."""
        return self.messages.fetching.enabled

    @property
    def msg_fetching_text(self) -> str:
        """Get fetching message text."""
        return self.messages.fetching.text

    @property
    def msg_found_enabled(self) -> bool:
        """Get found message enabled."""
        return self.messages.found.enabled

    @property
    def msg_found_text(self) -> str:
        """Get found message text."""
        return self.messages.found.text

    @property
    def msg_send_failed_text(self) -> str:
        """Get send failed message text."""
        return self.messages.send_failed.text

    @property
    def msg_send_failed_enabled(self) -> bool:
        """Get send failed message enabled."""
        return self.messages.send_failed.enabled

    def resolve_message(self, key: str, **kwargs: Any) -> str | None:
        """Resolve configured message text by key with placeholder substitution."""
        override = self._message_override(key)
        if override is not None:
            if not override.enabled:
                return None
            text = override.text
        elif key == "fetching":
            if not self.msg_fetching_enabled:
                return None
            text = self.msg_fetching_text
        elif key == "found":
            if not self.msg_found_enabled:
                return None
            text = self.msg_found_text
        elif key == "send_failed":
            if not self.msg_send_failed_enabled:
                return None
            text = self.msg_send_failed_text
        else:
            # Web API error keys are exposed as dotted names while Pydantic
            # fields keep Python identifiers.
            item = getattr(self.messages, key, None) or getattr(
                self.messages, key.replace(".", "_"), None
            )
            if not item or not getattr(item, "enabled", True):
                return None
            text = str(getattr(item, "text", "") or "")

        result = str(text)
        for k, v in kwargs.items():
            result = result.replace(f"{{{k}}}", str(v))
        if not result:
            return None
        return result

    def _message_override(self, key: str) -> MessageOverrideConfig | None:
        """Return a matching message override, if configured."""
        for item in self.messages.message_overrides:
            override_key = item.message_key or item.template_key
            if override_key == key:
                return item
        return None

    @property
    def setu_user_access_control_mode(self) -> str:
        """Get Setu user access control mode."""
        return self.safety.setu_user_access_control_mode.value

    @property
    def setu_group_access_control_mode(self) -> str:
        """Get Setu group access control mode."""
        return self.safety.setu_group_access_control_mode.value

    @property
    def fortune_user_access_control_mode(self) -> str:
        """Get Fortune user access control mode."""
        return self.safety.fortune_user_access_control_mode.value

    @property
    def fortune_group_access_control_mode(self) -> str:
        """Get Fortune group access control mode."""
        return self.safety.fortune_group_access_control_mode.value

    def format_found_message(
        self,
        count: int,
        revoke_delay: int | None = None,
        scope: str = "",
        r18: bool | str = "",
    ) -> str:
        """Format found message with placeholders."""
        r18_text = "是" if r18 is True else "否" if r18 is False else r18
        return (
            self.resolve_message(
                "found",
                count=count,
                revoke_delay=revoke_delay or "",
                scope=scope,
                r18=r18_text,
            )
            or ""
        )

    def get_effective_fortune_api_type(self) -> str:
        """Get effective fortune API type."""
        fortune_api = self.fortune.api_type
        if fortune_api == "inherit":
            return self.api_type
        return fortune_api
