"""Lolicon API V2 提供商。

文档: https://api.lolicon.app
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from ...application.setu.dto import ImageMetadata
from ...domain import HTTP_TIMEOUT_SECONDS
from ...shared import get_logger
from .base import DownloadingSetuImageProvider

logger = get_logger()


class LoliconProvider(DownloadingSetuImageProvider):
    """Lolicon API V2 提供商。

    文档: https://api.lolicon.app
    """

    API_URL = "https://api.lolicon.app/setu/v2"

    def __init__(
        self,
        image_size: str = "original",
        proxy: str = "",
        aspect_ratio: str = "",
        uid: list[int] | None = None,
        keyword: str = "",
    ):
        """初始化 Lolicon 提供商。

        参数:
            image_size: 图片规格 (original, regular, small, thumb, mini)
            proxy: 反代服务
            aspect_ratio: 图片长宽比
            uid: 指定作者 UID 列表
            keyword: 关键词搜索
        """
        self.image_size = image_size
        self.proxy = proxy
        self.aspect_ratio = aspect_ratio
        self.uid = uid or []
        self.keyword = keyword

    async def fetch_images(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[ImageMetadata]:
        logger.info(
            "[provider] Lolicon request: count=%d, r18=%s, tags=%s, size=%s, proxy=%s, exclude_ai=%s",
            num,
            r18,
            ",".join(tags) or "-",
            self.image_size,
            self.proxy or "-",
            exclude_ai,
        )
        exclude_ai_flag = exclude_ai
        query_params: list[tuple[str, str | int]] = [
            ("r18", 1 if r18 else 0),
            ("num", num),
            ("excludeAI", str(exclude_ai_flag).lower()),
            ("size", self.image_size),
        ]

        # 添加可选参数
        if self.proxy:
            query_params.append(("proxy", self.proxy))
        if self.aspect_ratio:
            query_params.append(("aspectRatio", self.aspect_ratio))
        if self.keyword:
            query_params.append(("keyword", self.keyword))

        # Handle uid as repeated parameters
        for uid in self.uid:
            if uid is not None:
                query_params.append(("uid", uid))

        # 构建 URL — handle repeated tag params separately
        tag_params = "&".join(f"tag={quote(t, safe='')}" for t in tags) if tags else ""
        base_params = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in query_params)
        url = f"{self.API_URL}?{base_params}"
        if tag_params:
            url += f"&{tag_params}"

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        urls: list[ImageMetadata] = []
        for item in data.get("data", []):
            # 根据 size 参数返回对应的 URL
            urls_obj = item.get("urls", {})
            img_url = urls_obj.get(self.image_size)
            if img_url:
                urls.append(
                    ImageMetadata(
                        img_url,
                        f"https://www.pixiv.net/artworks/{item['pid']}"
                        if item.get("pid")
                        else self.API_URL,
                        tuple(item.get("tags") or ()),
                        self._apply_proxy_to_url(img_url, self.proxy),
                    )
                )

        logger.info(
            "[provider] Lolicon response: requested=%d, returned=%d",
            num,
            len(urls),
        )
        return urls
