"""面向命令输入的标签解析与别名映射。"""

from __future__ import annotations

import re
from collections.abc import Iterable

from ...domain.setu import TagResolverService


def resolve_user_tags(raw_tags: str, configured_aliases: str) -> list[str]:
    """按命令分隔规则解析标签，并应用配置的别名映射。"""
    if not raw_tags or not raw_tags.strip():
        return []
    return _build_resolver(configured_aliases).resolve_tags(raw_tags)


def resolve_user_tag_list(
    raw_tags: Iterable[object], configured_aliases: str
) -> list[str]:
    """为结构化标签列表应用与命令文本相同的别名映射。"""
    resolver = _build_resolver(configured_aliases, split_alias_spaces=False)
    resolved_tags: list[str] = []
    for raw_tag in raw_tags:
        tag = str(raw_tag).strip()
        if tag:
            resolved_tags.append(resolver.resolve_tag(tag))
    return resolved_tags


def _build_resolver(
    configured_aliases: str, *, split_alias_spaces: bool = True
) -> TagResolverService:
    """构造优先使用插件配置的标签解析器。"""
    # 同一解析入口保证色图、本子与 LLM 的别名语义一致。
    alias_map = TagResolverService.parse_alias_map_from_string(
        configured_aliases, split_spaces=split_alias_spaces
    )
    return TagResolverService(alias_map or TagResolverService.DEFAULT_TAG_ALIAS)


def resolve_image_request_tags(
    raw_tags: str | Iterable[object], configured_aliases: str
) -> tuple[list[str], bool]:
    """Strip the per-request R18 marker before resolving ordinary tag aliases."""
    if isinstance(raw_tags, str):
        tokens = re.split(r"[\s,，、]+", raw_tags.strip())
    else:
        tokens = [str(tag).strip() for tag in raw_tags]
    r18 = any(token.casefold() == "r18" for token in tokens)
    tags = [token for token in tokens if token.casefold() != "r18"]
    if isinstance(raw_tags, str):
        return resolve_user_tags(" ".join(tags), configured_aliases), r18
    return resolve_user_tag_list(tags, configured_aliases), r18
