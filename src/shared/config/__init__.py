"""Shared configuration models."""

from __future__ import annotations

from .messages import MessagesConfig
from .models import (
    AccessControlModeStr,
    ApiSectionConfig,
    ApiTypeStr,
    AutoRevokeScopeStr,
    ContentModeStr,
    CustomApiConfig,
    DeliveryConfig,
    DoujinshiSendModeStr,
    FortuneConfig,
    HtmlCardStrategyStr,
    NapcatLocalFileModeStr,
    NapcatStreamModeStr,
    PlatformTransportConfig,
    ProviderConfig,
    ProviderOverrideConfig,
    SendModeStr,
    SetuGeneralConfig,
    SetuPluginConfig,
    TagAliasTemplateConfig,
    should_auto_revoke,
)

__all__ = [
    "AccessControlModeStr",
    "ApiSectionConfig",
    "ApiTypeStr",
    "AutoRevokeScopeStr",
    "ContentModeStr",
    "CustomApiConfig",
    "DeliveryConfig",
    "DoujinshiSendModeStr",
    "FortuneConfig",
    "HtmlCardStrategyStr",
    "MessagesConfig",
    "NapcatLocalFileModeStr",
    "NapcatStreamModeStr",
    "PlatformTransportConfig",
    "ProviderConfig",
    "ProviderOverrideConfig",
    "SendModeStr",
    "SetuGeneralConfig",
    "SetuPluginConfig",
    "TagAliasTemplateConfig",
    "should_auto_revoke",
]
