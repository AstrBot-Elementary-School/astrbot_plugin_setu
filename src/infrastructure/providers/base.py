"""Infrastructure base class for provider URL fetch and image download."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import httpx

from ...application.ports import SetuImageProvider
from ...application.setu.dto import ImageMetadata, ImagePayload
from ...domain import HTTP_TIMEOUT_SECONDS
from ...domain.setu import SetuRequest
from ...shared import get_logger
from ...shared.cache import get_cache
from ...shared.send_cache import get_send_cache

logger = get_logger()


@dataclass(frozen=True)
class DownloadAttemptResult:
    """单个图片 URL 的下载结果，避免用 None 同时表示失败和未尝试。"""

    url: str
    item: Path | bytes | None

    @property
    def succeeded(self) -> bool:
        """下载是否已落地为可发送数据。"""
        return self.item is not None


def select_replenish_urls(
    urls: list[str],
    missing: int,
    *,
    reported_urls: set[str],
    completed_urls: set[str],
    download_attempts: dict[str, int],
    max_rounds: int,
) -> tuple[list[str], int]:
    """从一次 provider 响应中选择不超过当前缺口数量的候选 URL。"""
    selected: list[str] = []
    retry_candidates: list[str] = []
    round_seen: set[str] = set()
    exhausted_urls = 0

    for url in urls:
        if not url or url in completed_urls or url in round_seen:
            continue
        round_seen.add(url)
        if download_attempts.get(url, 0) >= max_rounds:
            exhausted_urls += 1
            continue
        if url in reported_urls:
            retry_candidates.append(url)
            continue
        if len(selected) < missing:
            selected.append(url)

    for url in retry_candidates:
        if len(selected) >= missing:
            break
        selected.append(url)

    return selected, exhausted_urls


class DownloadingSetuImageProvider(SetuImageProvider):
    """Provider base that materializes image URLs into sendable local data."""

    async def fetch_and_download(
        self, request: SetuRequest, *, on_images
    ) -> ImagePayload:
        """Fetch URLs, download images, and replenish short batches when needed."""
        provider_name = self._provider_name()
        logger.info(
            "[provider] fetch start: provider=%s, count=%d, r18=%s, tags=%s, exclude_ai=%s, replenish_rounds=%d",
            provider_name,
            request.count,
            request.r18,
            ",".join(request.tags) or "-",
            request.exclude_ai,
            request.max_replenish_rounds,
        )

        if request.count <= 0:
            return ImagePayload(
                urls=(), raw_bytes=(), file_paths=(), r18=request.r18, tags=request.tags
            )

        all_urls: list[str] = []
        metadata = []
        successful_urls = []
        reported_urls: set[str] = set()
        completed_urls: set[str] = set()
        download_attempts: dict[str, int] = {}
        items: list[Path | bytes] = []
        max_rounds = max(1, request.max_replenish_rounds)

        try:
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_SECONDS,
                follow_redirects=True,
            ) as client:
                for round_index in range(1, max_rounds + 1):
                    missing = request.count - len(items)
                    if missing <= 0:
                        break

                    images = await self._fetch_replenish_urls(
                        request, missing, round_index
                    )
                    await on_images(images)
                    metadata.extend(images)
                    urls = [image.image_url for image in images]
                    fresh_urls, exhausted_urls = select_replenish_urls(
                        urls,
                        missing,
                        reported_urls=reported_urls,
                        completed_urls=completed_urls,
                        download_attempts=download_attempts,
                        max_rounds=max_rounds,
                    )
                    for url in fresh_urls:
                        if url not in reported_urls:
                            reported_urls.add(url)
                            all_urls.append(url)

                    if not fresh_urls:
                        logger.warning(
                            "[provider] replenish round returned no fresh urls: provider=%s, round=%d, missing=%d, tags=%s",
                            provider_name,
                            round_index,
                            missing,
                            ",".join(request.tags) or "-",
                        )
                        continue
                    if exhausted_urls:
                        logger.warning(
                            "[provider] skipped exhausted download urls: provider=%s, round=%d, skipped=%d, max_attempts=%d",
                            provider_name,
                            round_index,
                            exhausted_urls,
                            max_rounds,
                        )

                    round_downloads = await self._download_urls(
                        client,
                        fresh_urls,
                        download_attempts,
                        max_attempts=max_rounds,
                        download_urls={
                            image.image_url: image.download_url for image in images
                        },
                    )
                    successful_downloads = [
                        result for result in round_downloads if result.succeeded
                    ]
                    completed_urls.update(result.url for result in successful_downloads)
                    successful_urls.extend(
                        result.url for result in successful_downloads
                    )
                    items.extend(
                        result.item
                        for result in successful_downloads
                        if result.item is not None
                    )

                    failed = len(round_downloads) - len(successful_downloads)
                    logger.info(
                        "[provider] replenish round summary: provider=%s, round=%d/%d, requested=%d, urls=%d, succeeded=%d, failed=%d, total=%d/%d",
                        provider_name,
                        round_index,
                        max_rounds,
                        missing,
                        len(fresh_urls),
                        len(successful_downloads),
                        failed,
                        len(items),
                        request.count,
                    )

        except BaseException:
            for item in items:
                if isinstance(item, Path):
                    get_cache().release(item, keep=get_send_cache().enabled)
            raise

        raw_bytes = tuple(item for item in items if isinstance(item, bytes))
        file_paths = tuple(item for item in items if isinstance(item, Path))
        logger.info(
            "[provider] download summary: provider=%s, urls=%d, succeeded=%d, failed_or_missing=%d, bytes=%d, files=%d",
            provider_name,
            len(all_urls),
            len(items),
            max(0, request.count - len(items)),
            len(raw_bytes),
            len(file_paths),
        )
        if not items:
            logger.error(
                "[provider] all downloads failed: provider=%s, requested=%d, tags=%s",
                provider_name,
                request.count,
                ",".join(request.tags) or "-",
            )
        return ImagePayload(
            urls=tuple(successful_urls),
            images=tuple(metadata),
            raw_bytes=raw_bytes,
            file_paths=file_paths,
            items=tuple(items),
            r18=request.r18,
            tags=request.tags,
        )

    async def _fetch_replenish_urls(
        self, request: SetuRequest, count: int, round_index: int
    ) -> list[ImageMetadata]:
        provider_name = self._provider_name()
        urls = await self.fetch_images(
            num=count,
            tags=list(request.tags),
            r18=request.r18,
            exclude_ai=request.exclude_ai,
        )
        if not urls:
            logger.warning(
                "[provider] no urls returned: provider=%s, round=%d, count=%d, r18=%s, tags=%s",
                provider_name,
                round_index,
                count,
                request.r18,
                ",".join(request.tags) or "-",
            )
        else:
            logger.info(
                "[provider] fetch result: provider=%s, round=%d, urls=%d, requested=%d",
                provider_name,
                round_index,
                len(urls),
                count,
            )
        return urls

    async def _download_urls(
        self,
        client: httpx.AsyncClient,
        urls: list[str],
        download_attempts: dict[str, int] | None = None,
        max_attempts: int = 1,
        download_urls: dict[str, str | None] | None = None,
    ) -> list[DownloadAttemptResult]:
        attempts = download_attempts if download_attempts is not None else {}
        tasks = [
            asyncio.create_task(
                self._download_one(
                    client, url, attempts, max_attempts, (download_urls or {}).get(url)
                )
            )
            for url in urls
        ]
        try:
            items = await asyncio.gather(*tasks)
        except BaseException:
            for task in tasks:
                task.cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item in results:
                if isinstance(item, Path):
                    get_cache().release(item, keep=get_send_cache().enabled)
            raise
        # 保留失败结果给上层统计；只由上层把成功 URL 记为 completed，
        # 避免 CDN/反代短暂不可用时被 seen 去重永久跳过。
        return [
            DownloadAttemptResult(url=url, item=item)
            for url, item in zip(urls, items, strict=False)
        ]

    async def _download_one(
        self,
        client: httpx.AsyncClient,
        url: str,
        download_attempts: dict[str, int] | None = None,
        max_attempts: int = 1,
        download_url: str | None = None,
    ) -> Path | bytes | None:
        attempts = download_attempts if download_attempts is not None else {}
        max_allowed = max(1, max_attempts)
        while attempts.get(url, 0) < max_allowed:
            attempts[url] = attempts.get(url, 0) + 1
            attempt = attempts[url]
            item = await self._download_one_attempt(
                client, url, attempt, max_allowed, download_url
            )
            if item is not None:
                return item
        return None

    async def _download_one_attempt(
        self,
        client: httpx.AsyncClient,
        url: str,
        attempt: int,
        max_attempts: int,
        download_url: str | None = None,
    ) -> Path | bytes | None:
        provider_name = self._provider_name()
        download_url = download_url or url
        cache = get_send_cache()
        cache_enabled = bool(cache and cache.enabled)
        try:
            if cache_enabled and cache:
                cached = await cache.get(url)
                if cached is not None:
                    logger.debug(
                        "[provider] cache hit: provider=%s, url=%s",
                        provider_name,
                        url,
                    )
                    return cached

            if cache_enabled and cache is not None:
                write = None
                try:
                    async with client.stream("GET", download_url) as response:
                        response.raise_for_status()
                        write = await cache.reserve(
                            url, response.headers.get("content-type")
                        )
                        with get_cache().open(write.temp_path) as file:
                            async for chunk in response.aiter_bytes():
                                if chunk:
                                    await asyncio.to_thread(file.write, chunk)
                    final_path = await cache.commit(write)
                    logger.debug(
                        "[provider] download cached: provider=%s, url=%s, path=%s",
                        provider_name,
                        url,
                        final_path,
                    )
                    return final_path
                except BaseException:
                    if write is not None:
                        await cache.discard(write)
                    raise

            if cache is not None:
                chunks: list[bytes] = []
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes():
                        if chunk:
                            chunks.append(chunk)
                content = b"".join(chunks)
                logger.debug(
                    "[provider] download bytes: provider=%s, url=%s, bytes=%d",
                    provider_name,
                    url,
                    len(content),
                )
                return content

            response = await client.get(download_url)
            response.raise_for_status()
            logger.debug(
                "[provider] download bytes: provider=%s, url=%s, bytes=%d",
                provider_name,
                url,
                len(response.content),
            )
            return response.content
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            if attempt < max_attempts:
                logger.warning(
                    "[provider] transient download failed, will retry: provider=%s, url=%s, attempt=%d/%d, error=%s",
                    provider_name,
                    url,
                    attempt,
                    max_attempts,
                    exc,
                )
            else:
                logger.warning(
                    "[provider] download failed: provider=%s, url=%s, attempts=%d, error=%s",
                    provider_name,
                    url,
                    max_attempts,
                    exc,
                )
            return None
