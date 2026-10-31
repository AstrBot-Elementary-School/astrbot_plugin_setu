"""多个图片来源轮流处理请求。"""

from ...application.ports import SetuImageProvider
from ...application.setu.dto import ImageMetadata
from .base import DownloadingSetuImageProvider


class MultiApiProvider(DownloadingSetuImageProvider):
    def __init__(self, providers: list[SetuImageProvider]):
        self.providers = providers
        self.index = 0

    async def fetch_images(
        self, num: int, tags: list[str], r18: bool, exclude_ai: bool = True
    ) -> list[ImageMetadata]:
        for _ in self.providers:
            provider = self.providers[self.index]
            self.index = (self.index + 1) % len(self.providers)
            images = await provider.fetch_images(num, tags, r18, exclude_ai)
            if images:
                return images
        return []
