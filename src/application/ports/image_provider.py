"""图片提供商基类。"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from ...domain.setu import SetuRequest
from ...shared import get_logger
from ..setu.dto import ImageMetadata, ImagePayload

logger = get_logger()


class SetuImageProvider:
    """色图图片提供商基类（策略模式）。"""

    async def fetch_images(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[ImageMetadata]:
        """从 API 获取图片 URL 列表。

        参数:
            num: 要获取的图片数量。
            tags: 搜索标签/关键词。
            r18: 是否请求 R18 内容。
            exclude_ai: 是否排除 AI 生成的作品。

        返回:
            图片 URL 列表。
        """
        raise NotImplementedError

    async def fetch_and_download(
        self, request: SetuRequest, *, on_images
    ) -> ImagePayload:
        """Fetch and materialize image data for delivery."""
        raise NotImplementedError

    def _provider_name(self) -> str:
        return self.__class__.__name__

    def _apply_proxy_to_url(self, url: str, proxy: str | None) -> str:
        """Rewrite Pixiv-style image URLs to the configured reverse proxy host."""
        proxy_host = (proxy or "").strip()
        if not proxy_host:
            return url

        try:
            parsed = urlsplit(url)
        except ValueError:
            return url

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return url

        original_host = parsed.hostname or ""
        proxy_targets = {
            "i.pximg.net",
            "i.pixiv.re",
            "i.pixiv.cat",
            "proxy.pixivel.moe",
        }
        if original_host not in proxy_targets:
            return url

        netloc = proxy_host
        return urlunsplit(
            (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
        )
