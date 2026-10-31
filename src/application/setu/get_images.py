"""Use case for fetching Setu images."""

from __future__ import annotations

from ...domain.setu import SetuRequest
from ..ports import SetuImageProvider
from ..settings import get_setu_settings
from .dto import SetuImagesResult


class GetSetuImagesUseCase:
    """Fetch Setu image data without knowing how a chat platform will send it."""

    def __init__(self, image_provider: SetuImageProvider, on_images) -> None:
        self._provider = image_provider
        self._on_images = on_images

    async def execute(self, count: int, tags: list[str], r18: bool) -> SetuImagesResult:
        """Fetch image files according to current settings."""
        settings = get_setu_settings()
        request = SetuRequest.from_user_input(
            count=count,
            tags=tags,
            r18=r18,
            exclude_ai=settings.exclude_ai,
            max_replenish_rounds=settings.max_replenish_rounds,
        )

        payload = await self._provider.fetch_and_download(
            request, on_images=self._on_images
        )

        return SetuImagesResult(payload=payload)
