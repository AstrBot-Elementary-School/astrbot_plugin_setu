"""自定义 API 提供商。

支持用户配置任意 API 地址，并提供灵活的响应解析方式。
"""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from ...application.setu.dto import ImageMetadata
from ...domain import HTTP_TIMEOUT_SECONDS
from ...shared import get_logger
from .base import DownloadingSetuImageProvider

logger = get_logger()

# Blocked private/network IP ranges for SSRF protection
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/29"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_BLOCKED_HEADERS = frozenset(
    {
        "host",
        "authorization",
        "cookie",
        "proxy-authorization",
        "x-forwarded-for",
        "x-forwarded-host",
        "x-forwarded-proto",
        "forwarded",
        "proxy-connection",
    }
)


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """Remove sensitive headers that could enable SSRF or credential leakage."""
    return {k: v for k, v in headers.items() if k.lower() not in _BLOCKED_HEADERS}


async def _validate_url(url: str) -> tuple[str, str | None]:
    """Validate URL scheme and block private IPs (SSRF protection).

    Resolves DNS, validates IPs, and pins the URL to the resolved IP
    to prevent DNS rebinding attacks.

    Args:
        url: URL to validate.

    Returns:
        Tuple of (ip_pinned_url, original_hostname).

    Raises:
        ValueError: If URL scheme is invalid or points to private IP.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid URL scheme: {parsed.scheme}. Only http/https allowed."
        )
    if not parsed.hostname:
        raise ValueError("URL has no hostname.")

    import socket

    try:
        loop = asyncio.get_running_loop()
        resolved = await loop.run_in_executor(
            None,
            lambda: socket.getaddrinfo(
                parsed.hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
            ),
        )
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve hostname: {parsed.hostname}") from e

    first_ip: str | None = None
    for family, _type, _proto, _canon, addr in resolved:
        ip = ipaddress.ip_address(addr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError(f"URL resolves to blocked private IP: {ip}")
        if first_ip is None:
            first_ip = str(addr[0])

    # Pin hostname to resolved IP to prevent DNS rebinding
    if first_ip and parsed.hostname != first_ip:
        if parsed.port:
            pinned_netloc = (
                f"[{first_ip}]:{parsed.port}"
                if ":" in first_ip
                else f"{first_ip}:{parsed.port}"
            )
        else:
            pinned_netloc = f"[{first_ip}]" if ":" in first_ip else first_ip
        pinned_url = url.replace(
            f"{parsed.scheme}://{parsed.netloc}",
            f"{parsed.scheme}://{pinned_netloc}",
            1,
        )
        return pinned_url, parsed.hostname

    return url, None


class CustomApiProvider(DownloadingSetuImageProvider):
    """自定义 API 提供商。

    支持用户配置任意 API 地址，并提供灵活的响应解析方式。
    """

    def __init__(
        self,
        api_config: dict[str, Any] | None = None,
        parser_config: dict[str, Any] | None = None,
    ):
        """初始化自定义 API 提供商。

        参数:
            api_config: API 配置（url, method, timeout, headers）。
            parser_config: 响应解析配置（type, json_path）。
        """
        self.api_config = api_config or {}
        self.parser_config = parser_config or {}

    async def _build_url(
        self, num: int, tags: list[str], r18: bool, exclude_ai: bool
    ) -> tuple[str, dict[str, Any] | None, str | None]:
        """构建请求 URL、请求体和原始主机名。"""
        url_template = self.api_config.get("url", "")
        method = self.api_config.get("method", "GET").upper()

        # 替换 URL 中的占位符
        tags_str = quote(",".join(tags)) if tags else ""
        url = url_template.replace("{num}", str(num))
        url = url.replace("{r18}", "1" if r18 else "0")
        url = url.replace("{tags}", tags_str)

        pinned_url, original_host = await _validate_url(url)

        if method == "POST":
            body = {
                "num": num,
                "r18": r18,
                "tags": tags,
                "exclude_ai": exclude_ai,
            }
            return pinned_url, body, original_host
        else:
            return pinned_url, None, original_host

    def _parse_response(self, data: Any) -> list[str]:
        """解析 API 响应，提取图片 URL 列表。"""
        parser_type = self.parser_config.get("type", "auto")

        if parser_type == "json":
            return self._parse_json_response(data)
        else:
            return self._parse_auto_response(data)

    def _parse_json_response(self, data: Any) -> list[str]:
        """使用 JSON 路径表达式解析响应。"""
        json_path = self.parser_config.get("json_path", "")

        if not json_path or not isinstance(data, (dict, list)):
            return []

        # 简单的 JSON 路径解析
        # 支持 $.data[*].url 或 $.images 等形式
        result = self._get_value_by_path(data, json_path)

        if isinstance(result, str):
            return [result]
        elif isinstance(result, list):
            urls = []
            for item in result:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict):
                    # 尝试从字典中提取 URL
                    url = item.get("url") or item.get("image") or item.get("link")
                    if url:
                        urls.append(url)
            return urls
        elif isinstance(result, dict):
            url = result.get("url") or result.get("image") or result.get("link")
            return [url] if url else []

        return []

    def _get_value_by_path(self, data: Any, path: str) -> Any:
        """根据路径表达式获取值。

        支持：
        - $.data.url (单级)
        - $.data[*].url (数组遍历)
        - $.data[0].url (指定索引)
        """
        # 移除开头的 $.
        path = path.lstrip("$.").strip()
        if not path:
            return data

        parts = path.split(".")
        current = data

        # 使用索引遍历，避免重复字段名导致的解析错误
        for idx, part in enumerate(parts):
            if current is None:
                return None

            # 处理数组索引 [*] 或 [n]
            if "[" in part and "]" in part:
                arr_name = part[: part.index("[")]
                idx_str = part[part.index("[") + 1 : part.index("]")]

                if arr_name:
                    current = (
                        current.get(arr_name) if isinstance(current, dict) else None
                    )

                if not isinstance(current, list):
                    return None

                if idx_str == "*":
                    # 遍历数组，获取下一级
                    # 使用 idx+1 代替 parts.index(part) 避免重复字段名问题
                    next_part = ".".join(parts[idx + 1 :])
                    if next_part:
                        results = []
                        for item in current:
                            val = self._get_value_by_path(item, next_part)
                            if val is not None:
                                if isinstance(val, list):
                                    results.extend(val)
                                else:
                                    results.append(val)
                        return results
                    else:
                        return current
                else:
                    try:
                        arr_idx = int(idx_str)
                        current = (
                            current[arr_idx] if 0 <= arr_idx < len(current) else None
                        )
                    except (ValueError, IndexError):
                        return None
            else:
                current = current.get(part) if isinstance(current, dict) else None

        return current

    def _parse_auto_response(self, data: Any) -> list[str]:
        """自动从响应中提取所有图片 URL。"""
        urls: list[str] = []

        def extract_urls(obj: Any) -> None:
            if isinstance(obj, str):
                # 检查是否是 URL
                if self._is_image_url(obj):
                    urls.append(obj)
            elif isinstance(obj, list):
                for item in obj:
                    extract_urls(item)
            elif isinstance(obj, dict):
                for key, value in obj.items():
                    # 优先检查可能的 URL 键
                    if key.lower() in (
                        "url",
                        "link",
                        "src",
                        "image",
                        "img",
                        "original",
                        "regular",
                    ):
                        if isinstance(value, str) and self._is_image_url(value):
                            urls.append(value)
                    else:
                        extract_urls(value)

        extract_urls(data)
        return list(dict.fromkeys(urls))  # 去重保持顺序

    def _is_image_url(self, url: str) -> bool:
        """检查字符串是否是图片 URL。"""
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return False

        # 检查是否包含图片扩展名或常见图片域名
        image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
        image_hosts = ("pixiv", "img", "image", "pic", "photo", "cdn")

        url_lower = url.lower()
        has_ext = any(url_lower.endswith(ext) for ext in image_exts)
        has_host = any(host in url_lower for host in image_hosts)

        # URL 中包含图片相关特征
        return has_ext or has_host or "/img" in url_lower or "/image" in url_lower

    def _metadata(self, data, urls, api_url):
        found = {}

        def visit(node, source=None, tags=()):
            if isinstance(node, dict):
                source = node.get("source_url") or node.get("source") or source
                if node.get("pid"):
                    source = f"https://www.pixiv.net/artworks/{node['pid']}"
                tags = node.get("tags") or tags
                if isinstance(tags, str):
                    tags = (tags,)
                for value in node.values():
                    visit(value, source, tags)
            elif isinstance(node, list):
                for value in node:
                    visit(value, source, tags)
            elif isinstance(node, str) and node in urls:
                found[node] = ImageMetadata(node, source or api_url, tuple(tags))

        visit(data)
        return [found[url] for url in urls]

    async def fetch_images(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[ImageMetadata]:
        """从自定义 API 获取图片 URL 列表。"""
        url, body, original_host = await self._build_url(num, tags, r18, exclude_ai)
        if not url:
            raise ValueError("请先配置自定义 API 地址。")
        timeout = self.api_config.get("timeout", HTTP_TIMEOUT_SECONDS)
        headers = _sanitize_headers(self.api_config.get("headers", {}))
        if original_host:
            headers["Host"] = original_host
        async with httpx.AsyncClient(timeout=timeout) as client:
            if body:
                resp = await client.post(url, json=body, headers=headers)
            else:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            urls = self._parse_response(data)
            api_url = (
                str(httpx.URL(url).copy_with(host=original_host))
                if original_host
                else url
            )
            return self._metadata(data, urls[:num], api_url)
