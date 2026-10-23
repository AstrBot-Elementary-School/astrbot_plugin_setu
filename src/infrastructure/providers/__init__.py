"""图片提供商实现，使用策略模式。"""

from __future__ import annotations

from typing import Any

from ...application.ports import SetuImageProvider
from ...shared import get_logger
from .atri import AtriProvider
from .custom import CustomApiProvider
from .lolicon import LoliconProvider
from .multi import MultiApiProvider
from .sexnyan import SexNyanRunProvider

logger = get_logger()

# 提供商注册表
PROVIDERS: dict[str, type[SetuImageProvider]] = {
    "lolicon": LoliconProvider,
    "atri": AtriProvider,
    "sexnyan": SexNyanRunProvider,
}

# 多API策略下的内置提供商列表
BUILTIN_PROVIDERS = ["lolicon", "atri", "sexnyan"]

# ==================== Singleton Pattern ====================

_provider: SetuImageProvider | None = None


def get_provider() -> SetuImageProvider:
    """Get the provider singleton.

    Returns:
        The current SetuImageProvider instance.

    Raises:
        RuntimeError: If provider not initialized.
    """
    if _provider is None:
        raise RuntimeError("Provider not initialized. Call init_provider() first.")
    return _provider


def init_provider(
    api_type: str,
    custom_config: dict[str, Any] | None = None,
    parser_config: dict[str, Any] | None = None,
    custom_api_configs: list[dict[str, Any]] | None = None,
    multi_api_strategy: str = "round_robin",
    lolicon_config: dict[str, Any] | None = None,
    atri_config: dict[str, Any] | None = None,
    sexnyan_config: dict[str, Any] | None = None,
) -> SetuImageProvider:
    """Initialize provider singleton.

    Args:
        api_type: Provider type ('lolicon', 'atri', 'sexnyan', 'custom', 'all').
        custom_config: Custom API config for 'custom' type.
        parser_config: Parser config for 'custom' type.
        custom_api_configs: Custom API configs list (template_list format).
        multi_api_strategy: Multi-API strategy ('round_robin', 'random', 'failover').
        lolicon_config: Lolicon provider config.
        atri_config: Atri provider config.
        sexnyan_config: SexNyan provider config.

    Returns:
        The initialized provider instance.
    """
    global _provider
    _provider = _create_provider(
        api_type=api_type,
        custom_config=custom_config,
        parser_config=parser_config,
        custom_api_configs=custom_api_configs,
        multi_api_strategy=multi_api_strategy,
        lolicon_config=lolicon_config,
        atri_config=atri_config,
        sexnyan_config=sexnyan_config,
    )
    return _provider


def init_provider_from_config(config: Any) -> SetuImageProvider:
    """Initialize provider singleton from the current plugin config snapshot."""
    provider = init_provider(
        api_type=(getattr(config, "api_type", None) or "lolicon"),
        custom_api_configs=getattr(config, "custom_api_configs", None) or None,
        multi_api_strategy="round_robin",
        lolicon_config={
            "image_size": getattr(config, "image_size", None) or "original",
            "proxy": getattr(config, "proxy", None) or "",
            "aspect_ratio": getattr(config, "aspect_ratio", None) or "",
            "uid": getattr(config, "uid", None) or [],
            "keyword": getattr(config, "keyword", None) or "",
        },
        atri_config={
            "image_size": getattr(config, "atri_image_size", None) or "original",
            "proxy": getattr(config, "atri_proxy", None) or "",
            "aspect_ratio": getattr(config, "atri_aspect_ratio", None) or "",
            "uid": getattr(config, "atri_uid", None) or [],
            "keyword": getattr(config, "atri_keyword", None) or "",
        },
        sexnyan_config={
            "proxy": getattr(config, "sexnyan_proxy", None) or "",
            "uid": getattr(config, "sexnyan_uid", None) or [],
            "keyword": getattr(config, "sexnyan_keyword", None) or "",
        },
    )
    logger.info(
        "[provider] initialized from config: api_type=%s, lolicon_proxy=%s, atri_proxy=%s",
        getattr(config, "api_type", None) or "lolicon",
        getattr(config, "proxy", None) or "-",
        getattr(config, "atri_proxy", None) or "-",
    )
    return provider


def clear_provider() -> None:
    """Clear provider singleton (for testing)."""
    global _provider
    _provider = None


def _create_provider(
    api_type: str,
    custom_config: dict[str, Any] | None = None,
    parser_config: dict[str, Any] | None = None,
    custom_api_configs: list[dict[str, Any]] | None = None,
    multi_api_strategy: str = "round_robin",
    lolicon_config: dict[str, Any] | None = None,
    atri_config: dict[str, Any] | None = None,
    sexnyan_config: dict[str, Any] | None = None,
) -> SetuImageProvider | MultiApiProvider:
    """根据类型名称获取提供商实例。

    参数:
        api_type: 提供商类型（'lolicon'、'atri'、'sexnyan'、'custom' 或 'all'）。
        custom_config: 自定义 API 配置（当 api_type 为 custom 时使用）。
        parser_config: API 响应解析配置（当 api_type 为 custom 时使用）。
        custom_api_configs: 自定义 API 配置列表（template_list 格式）。
        multi_api_strategy: 多 API 策略（'round_robin'、'random'、'failover'）。
        lolicon_config: Lolicon 专属配置参数。
        atri_config: Atri 专属配置参数。
        sexnyan_config: SexNyan 专属配置参数。

    返回:
        提供商实例（如果类型未知则默认返回 lolicon）。
    """
    if api_type == "all":
        # 创建多API提供商（内置API）
        providers = []
        for name in BUILTIN_PROVIDERS:
            if name == "lolicon" and lolicon_config:
                provider = LoliconProvider(**lolicon_config)
            elif name == "atri" and atri_config:
                provider = AtriProvider(**atri_config)
            elif name == "sexnyan" and sexnyan_config:
                provider = SexNyanRunProvider(**sexnyan_config)
            else:
                provider = PROVIDERS[name]()
            providers.append(provider)
        return MultiApiProvider(providers, strategy=multi_api_strategy)

    if api_type == "custom":
        # 优先使用新的 template_list 配置格式
        if (
            custom_api_configs
            and isinstance(custom_api_configs, list)
            and len(custom_api_configs) > 0
        ):
            if len(custom_api_configs) == 1:
                # 只有一个配置，直接使用
                cfg = custom_api_configs[0]
                api_config = {
                    "url": cfg.get("url", ""),
                    "method": cfg.get("method", "GET"),
                    "timeout": cfg.get("timeout", 30),
                }
                parser_cfg = {
                    "type": cfg.get("parser_type", "auto"),
                    "json_path": cfg.get("json_path", ""),
                }
                return CustomApiProvider(api_config, parser_cfg)
            else:
                # 多个配置，创建多API提供商
                providers = []
                for cfg in custom_api_configs:
                    api_config = {
                        "url": cfg.get("url", ""),
                        "method": cfg.get("method", "GET"),
                        "timeout": cfg.get("timeout", 30),
                    }
                    parser_cfg = {
                        "type": cfg.get("parser_type", "auto"),
                        "json_path": cfg.get("json_path", ""),
                    }
                    providers.append(CustomApiProvider(api_config, parser_cfg))
                return MultiApiProvider(providers, strategy=multi_api_strategy)

        # 兼容旧的配置格式
        if custom_config:
            return CustomApiProvider(custom_config, parser_config or {})

        logger.warning("api_type 为 custom 但未提供配置，回退到 lolicon")
        if lolicon_config:
            return LoliconProvider(**lolicon_config)
        return LoliconProvider()

    provider_cls = PROVIDERS.get(api_type)
    if provider_cls is None:
        logger.warning("未知的 api_type '%s'，回退到 lolicon", api_type)
        provider_cls = LoliconProvider

    # 创建实例
    if api_type == "lolicon" and lolicon_config:
        return provider_cls(**lolicon_config)
    if api_type == "atri" and atri_config:
        return provider_cls(**atri_config)
    if api_type == "sexnyan" and sexnyan_config:
        return provider_cls(**sexnyan_config)
    return provider_cls()


__all__ = [
    "SetuImageProvider",
    "MultiApiProvider",
    "LoliconProvider",
    "AtriProvider",
    "SexNyanRunProvider",
    "CustomApiProvider",
    "get_provider",
    "init_provider",
    "init_provider_from_config",
    "clear_provider",
]
