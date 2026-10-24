from __future__ import annotations

import httpx
import pytest
from astrbot_plugin_setu.src.domain.setu import SetuRequest
from astrbot_plugin_setu.src.infrastructure.providers.base import (
    DownloadingSetuImageProvider,
)


class DummyProvider(DownloadingSetuImageProvider):
    async def fetch_image_urls(
        self,
        num: int,
        tags: list[str],
        r18: bool,
        exclude_ai: bool = True,
    ) -> list[str]:
        return ["https://example.com/a.jpg"]


@pytest.mark.asyncio
async def test_fetch_and_download_retries_transient_download_failure(
    monkeypatch,
) -> None:
    provider = DummyProvider()
    request = SetuRequest.from_user_input(
        count=1, tags=["cat"], r18=False, exclude_ai=True, max_replenish_rounds=2
    )
    calls = 0

    async def flaky_get(_self, url: str):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("temporary", request=httpx.Request("GET", url))
        return httpx.Response(
            200,
            content=b"image-data",
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", flaky_get)

    payload = await provider.fetch_and_download(request)

    assert payload.items == (b"image-data",)
    assert calls == 2


@pytest.mark.asyncio
async def test_fetch_and_download_keeps_requested_count_when_provider_overreturns(
    monkeypatch,
) -> None:
    """上游返回多于请求数量的 URL 时，只交付用户请求数量的图片。"""

    class OverreturningProvider(DummyProvider):
        async def fetch_image_urls(
            self,
            num: int,
            tags: list[str],
            r18: bool,
            exclude_ai: bool = True,
        ) -> list[str]:
            assert num == 1
            return [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ]

    provider = OverreturningProvider()
    request = SetuRequest.from_user_input(
        count=1, tags=["cat"], r18=False, exclude_ai=True, max_replenish_rounds=1
    )

    async def fake_get(_self, url: str) -> httpx.Response:
        return httpx.Response(
            200,
            content=url.rsplit("/", 1)[-1].encode(),
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    payload = await provider.fetch_and_download(request)

    assert payload.urls == ("https://example.com/a.jpg",)
    assert payload.items == (b"a.jpg",)


@pytest.mark.asyncio
async def test_fetch_and_download_skips_reported_url_before_capping_candidates(
    monkeypatch,
) -> None:
    """候选裁剪不能让前序失败 URL 挤掉后续可用的新 URL。"""

    class RetryThenFreshProvider(DummyProvider):
        def __init__(self) -> None:
            self.calls = 0

        async def fetch_image_urls(
            self,
            num: int,
            tags: list[str],
            r18: bool,
            exclude_ai: bool = True,
        ) -> list[str]:
            assert num == 1
            self.calls += 1
            if self.calls == 1:
                return ["https://example.com/a.jpg"]
            return [
                "https://example.com/a.jpg",
                "https://example.com/b.jpg",
            ]

    provider = RetryThenFreshProvider()
    request = SetuRequest.from_user_input(
        count=1, tags=["cat"], r18=False, exclude_ai=True, max_replenish_rounds=2
    )

    async def fake_get(_self, url: str) -> httpx.Response:
        request = httpx.Request("GET", url)
        if url.endswith("/a.jpg"):
            raise httpx.ConnectError("a is unavailable", request=request)
        return httpx.Response(200, content=b"b.jpg", request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    payload = await provider.fetch_and_download(request)

    assert payload.urls == ("https://example.com/a.jpg", "https://example.com/b.jpg")
    assert payload.items == (b"b.jpg",)
