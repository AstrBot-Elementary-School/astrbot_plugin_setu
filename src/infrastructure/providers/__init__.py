"""按当前配置建立图片来源。"""

from ...application.ports import SetuImageProvider
from .custom import CustomApiProvider
from .lolicon import LoliconProvider
from .multi import MultiApiProvider
from .sexnyan import SexNyanRunProvider

_provider: SetuImageProvider | None = None


def get_provider() -> SetuImageProvider:
    if _provider is None:
        raise RuntimeError("图片来源尚未初始化")
    return _provider


def init_provider_from_config(config) -> SetuImageProvider:
    global _provider
    if config.api_type in ("lolicon", "sexnyan", "all"):
        providers = {
            "lolicon": LoliconProvider(
                image_size=config.image_size,
                proxy=config.proxy,
                aspect_ratio=config.aspect_ratio,
                uid=config.uid,
                keyword=config.keyword,
            ),
            "sexnyan": SexNyanRunProvider(
                proxy=config.sexnyan_proxy,
                uid=config.sexnyan_uid,
                keyword=config.sexnyan_keyword,
            ),
        }
        _provider = (
            MultiApiProvider(list(providers.values()))
            if config.api_type == "all"
            else providers[config.api_type]
        )
    elif config.api_type == "custom":
        providers = [
            CustomApiProvider(
                {
                    "url": item["url"],
                    "method": item["method"],
                    "timeout": item["timeout"],
                },
                {"type": item["parser_type"], "json_path": item["json_path"]},
            )
            for item in config.custom_api_configs
        ]
        if not providers:
            raise ValueError("自定义图片来源需要至少一个 API 配置。")
        _provider = providers[0] if len(providers) == 1 else MultiApiProvider(providers)
    else:
        raise ValueError(f"未知图片来源：{config.api_type}")
    return _provider


def clear_provider() -> None:
    global _provider
    _provider = None
