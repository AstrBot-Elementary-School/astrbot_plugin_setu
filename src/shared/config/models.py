"""Pydantic v2 configuration models for Setu plugin.

Replaces the ConfigBase + mixin chain with type-safe, validated models.
Each section mirrors the _conf_schema.json structure for WebUI compatibility.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
    model_validator,
)

from ...domain.setu.triggers import compile_trigger


class ImageSize(str, Enum):
    """Valid image sizes for Lolicon APIs."""

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
    SEXNYAN = "sexnyan"
    CUSTOM = "custom"
    ALL = "all"


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
    """Configuration for a single API provider (Lolicon or SexNyan)."""

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
    local_file_mode: NapcatLocalFileModeStr = NapcatLocalFileModeStr.DISABLED
    local_file_allowed_roots: list[str] = Field(default_factory=list)


class TriggerTemplateConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    template_key: Literal["setu", "doujinshi", "fortune"] = Field(
        alias="__template_key"
    )
    phrase: str = ""

    @model_validator(mode="after")
    def validate_phrase(self) -> TriggerTemplateConfig:
        compile_trigger(self.template_key, self.phrase)
        return self


class SetuGeneralConfig(BaseModel):
    """Setu general configuration."""

    show_advanced: bool = False
    api_type: ApiTypeStr = ApiTypeStr.LOLICON
    content_mode: ContentModeStr = ContentModeStr.SFW
    max_count: int = Field(default=10, ge=1, le=10)
    llm_tools_enabled: bool = True
    natural_language_enabled: bool = True
    trigger_templates: list[TriggerTemplateConfig] = Field(
        default_factory=lambda: [
            TriggerTemplateConfig(__template_key=kind)
            for kind in ("setu", "doujinshi", "fortune")
        ]
    )
    tag_alias_templates: list[TagAliasTemplateConfig] = Field(default_factory=list)


class DeliveryConfig(BaseModel):
    """消息发送与自动清理配置。"""

    show_advanced: bool = False
    send_mode: SendModeStr = SendModeStr.AUTO
    html_card_strategy: HtmlCardStrategyStr = HtmlCardStrategyStr.FALLBACK
    doujinshi_enabled: bool = True
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
    napcat_local_file_mode: NapcatLocalFileModeStr = NapcatLocalFileModeStr.DISABLED
    napcat_local_file_allowed_roots: list[str] = Field(default_factory=list)
    compress_enabled: bool = False
    compress_max_mb: int = Field(default=4, ge=1, le=30)


class FortuneConfig(BaseModel):
    """Fortune (Today's Luck) configuration."""

    show_advanced: bool = False
    enabled: bool = True
    tags: str = ""
    content_mode: ContentModeStr = ContentModeStr.SFW
    allow_user_refresh: bool = False
    auto_refresh: bool = True


class AccessControlTemplate(BaseModel):
    """按功能配置完整 SID 访问规则。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    template_key: Literal["setu", "fortune"] = Field(alias="__template_key")
    mode: AccessControlModeStr = AccessControlModeStr.NONE
    blocked_sids: list[str] = Field(default_factory=list)
    whitelist_sids: list[str] = Field(default_factory=list)

    @field_validator("blocked_sids", "whitelist_sids")
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(value.strip() for value in values))
        for value in normalized:
            parts = value.split(":", 2)
            if len(parts) != 3 or not all(parts):
                raise ValueError(f"需要完整 SID（平台:消息类型:会话ID）：{value!r}")
        return normalized

    @model_validator(mode="after")
    def reject_conflicting_lists(self) -> AccessControlTemplate:
        if set(self.blocked_sids) & set(self.whitelist_sids):
            raise ValueError(f"{self.template_key} 黑白名单不能包含相同 SID")
        return self


class SafetyConfig(RootModel[list[AccessControlTemplate]]):
    """未添加模板的功能不限制；每种功能只接受一条规则。"""

    root: list[AccessControlTemplate] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_duplicate_rules(self) -> SafetyConfig:
        keys = [item.template_key for item in self.root]
        if len(keys) != len(set(keys)):
            raise ValueError("同一访问控制模板不能重复添加")
        return self


class SessionTemplateBase(BaseModel):
    """会话标识必须与 AstrBot unified_msg_origin 精确匹配。"""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    session_id: str

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("session_id 不能为空")
        return value


class SetuSessionTemplate(SessionTemplateBase):
    template_key: Literal["setu"] = Field("setu", alias="__template_key")
    content_mode: Literal["inherit", "sfw", "r18", "mix"] = "inherit"
    send_mode: Literal["inherit", "image", "forward", "auto"] = "inherit"
    r18_docx_mode: Literal["inherit", "true", "false"] = "inherit"
    auto_revoke_scope: Literal["inherit", "none", "sfw", "r18", "all"] = "inherit"


class FortuneSessionTemplate(SessionTemplateBase):
    template_key: Literal["fortune"] = Field("fortune", alias="__template_key")
    content_mode: Literal["inherit", "sfw", "r18", "mix"] = "inherit"
    override_tags: bool = False
    tags: str = ""


SessionTemplate = Annotated[
    SetuSessionTemplate | FortuneSessionTemplate, Field(discriminator="template_key")
]


class SessionOverridesConfig(BaseModel):
    session_configs: list[SessionTemplate] = Field(default_factory=list)

    @field_validator("session_configs")
    @classmethod
    def reject_duplicate_sessions(
        cls, values: list[SessionTemplate]
    ) -> list[SessionTemplate]:
        seen = set()
        for item in values:
            key = (item.session_id, item.template_key)
            if key in seen:
                raise ValueError(
                    f"会话模板重复：{item.session_id} ({item.template_key})"
                )
            seen.add(key)
        return values


class ApiSectionConfig(BaseModel):
    """API section configuration."""

    provider_overrides: list[ProviderOverrideConfig] = Field(default_factory=list)
    custom_api_configs: list[CustomApiConfig] = Field(default_factory=list)


class SetuPluginConfig(SessionOverridesConfig):
    """Root Pydantic model for Setu plugin configuration.

    This replaces the ConfigBase + mixin chain with a single validated model.
    The structure mirrors _conf_schema.json for WebUI compatibility.

    The model can be instantiated directly from AstrBotConfig dict:
        config = SetuPluginConfig(**astrbot_config)
    """

    setu_general: SetuGeneralConfig = Field(default_factory=SetuGeneralConfig)
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    fortune: FortuneConfig = Field(default_factory=FortuneConfig)
    api: ApiSectionConfig = Field(default_factory=ApiSectionConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)

    # Convenience properties for backward compatibility
    @property
    def api_type(self) -> str:
        """Get API type."""
        return self.setu_general.api_type.value

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
        return 3

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
        return 64

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
        return self.delivery.html_card_strategy.value

    @property
    def html_card_padding(self) -> int:
        """Get HTML card padding."""
        return 6

    @property
    def html_card_gap(self) -> int:
        """Get HTML card gap."""
        return 6

    @property
    def cache_enabled(self) -> bool:
        """Get cache enabled."""
        return True

    @property
    def cache_ttl_hours(self) -> int:
        """Get cache TTL hours."""
        return 2

    @property
    def cache_max_items(self) -> int:
        """Get cache max items."""
        return 200

    @property
    def cache_cleanup_on_start(self) -> bool:
        """Get cache cleanup on start."""
        return True

    @property
    def exclude_ai(self) -> bool:
        """Get exclude AI."""
        return self._provider_config("lolicon").exclude_ai

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
