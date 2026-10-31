"""SexNyanRun API 提供商。

文档: https://sex.nyan.run
"""

from __future__ import annotations

import httpx

from ...application.setu.dto import ImageMetadata
from ...domain import HTTP_TIMEOUT_SECONDS
from ...shared import get_logger
from .base import DownloadingSetuImageProvider

logger = get_logger()


class SexNyanRunProvider(DownloadingSetuImageProvider):
    """SexNyanRun API 提供商。

    文档: https://sex.nyan.run
    """

    API_URL = "https://sex.nyan.run/api/v2/"

    def __init__(
        self,
        proxy: str = "",
        uid: list[int] | None = None,
        keyword: str = "",
    ):
        """初始化 SexNyanRun 提供商。

        参数:
            proxy: 图片反代服务
            uid: 指定作者 UID 列表,映射到 SexNyan 的 author_uuid
            keyword: 关键词搜索
        """
        self.proxy = proxy
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
            "[provider] SexNyan request: count=%d, r18=%s, tags=%s, "
            "proxy=%s, uid=%d, keyword=%s",
            num,
            r18,
            ",".join(tags) or "-",
            self.proxy or "-",
            len(self.uid),
            self.keyword or "-",
        )
        query_params: list[tuple[str, str | int]] = [
            ("r18", str(r18).lower()),
            ("num", num),
        ]
        if self.keyword:
            query_params.append(("keyword", self.keyword))
        for author_uid in self.uid:
            if author_uid is not None:
                query_params.append(("author_uuid", author_uid))
        for tag in tags:
            if tag:
                query_params.append(("tag", tag))

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(self.API_URL, params=query_params)
            resp.raise_for_status()
            data = resp.json()

        urls: list[ImageMetadata] = []
        for item in data.get("data", []):
            if isinstance(item, dict):
                img_url = item.get("url")
                if img_url:
                    urls.append(
                        ImageMetadata(
                            img_url,
                            item.get("page") or self.API_URL,
                            tuple(item.get("tags") or ()),
                            self._apply_proxy_to_url(img_url, self.proxy),
                        )
                    )

        logger.info(
            "[provider] SexNyan response: requested=%d, returned=%d",
            num,
            len(urls),
        )
        return urls
