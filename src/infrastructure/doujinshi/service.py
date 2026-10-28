"""随机本子 API 的响应解析与文件生成服务。"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
import mimetypes
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4
import zipfile

import httpx
from PIL import Image
from PIL import ImageOps

from ...domain import HTTP_TIMEOUT_SECONDS


@dataclass(frozen=True)
class DoujinshiGallery:
    """可下载并封装为文件的本子元数据。

    ``title`` 可在上游缺失时回退为本地标题；其余两个字段保留上游实际
    返回的元数据，便于诊断和未来扩展，但不会再被拼装成合并转发节点。
    """

    id: int
    title: str
    page_urls: tuple[str, ...]
    upstream_title: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class GeneratedDoujinshiFile:
    """已经落盘、可作为 AstrBot 文件消息发送的随机本子文件。"""

    gallery: DoujinshiGallery
    path: Path
    mode: str = "pdf"


# 保留旧名称，避免外部调用方在升级后导入失败；新代码使用通用文件类型。
GeneratedDoujinshiPdf = GeneratedDoujinshiFile


class DoujinshiService:
    """解析 Atri 随机本子 API 的公开响应。"""

    API_URL = "https://api.atri.rodeo/v1/doujinshi/random"
    REQUEST_HEADERS = {
        "Accept": "application/json",
        "User-Agent": (
            "astrbot-plugin-setu/2.2.0 "
            "(+https://github.com/FlanChanXwO/astrbot_plugin_setu)"
        ),
        "Sec-Fetch-Dest": "empty",
    }

    def __init__(self, data_dir: Path | str) -> None:
        self._output_dir = Path(data_dir) / "doujinshi"

    async def fetch_random_file(
        self,
        tags: list[str] | None = None,
        *,
        mode: str = "pdf",
        max_page: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> GeneratedDoujinshiFile:
        """获取随机本子，并按 ``mode`` 生成 PDF 或 ZIP 文件。

        ``max_page`` 大于 0 时作为 ``max_page`` 查询参数传给 API，限制本子
        最大页数；为 ``None`` 或 0 时不传该参数。
        """
        normalized_mode = self._normalize_mode(mode)
        normalized_tags = [tag for tag in tags or [] if tag]
        if client is not None:
            return await self._fetch_random_file_with_client(
                client, normalized_tags, normalized_mode, max_page
            )

        async with httpx.AsyncClient(
            timeout=HTTP_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as managed_client:
            return await self._fetch_random_file_with_client(
                managed_client, normalized_tags, normalized_mode, max_page
            )

    async def fetch_random_pdf(
        self,
        tags: list[str] | None = None,
        *,
        max_page: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> GeneratedDoujinshiFile:
        """兼容旧调用方：强制生成 PDF 文件。"""
        return await self.fetch_random_file(
            tags, mode="pdf", max_page=max_page, client=client
        )

    async def fetch_random_archive(
        self,
        tags: list[str] | None = None,
        *,
        max_page: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> GeneratedDoujinshiFile:
        """获取随机本子并生成 ZIP 压缩包。"""
        return await self.fetch_random_file(
            tags, mode="archive", max_page=max_page, client=client
        )

    async def _fetch_random_file_with_client(
        self,
        client: httpx.AsyncClient,
        tags: list[str],
        mode: str,
        max_page: int | None,
    ) -> GeneratedDoujinshiFile:
        # 与 Atri 图片接口一致，重复 tag 参数以保留所有解析后的标签。
        params: list[tuple[str, str]] = [("tag", tag) for tag in tags]
        if max_page is not None and max_page > 0:
            params.append(("max_page", str(max_page)))
        response = await client.get(
            self.API_URL,
            headers=self.REQUEST_HEADERS,
            params=params,
        )
        response.raise_for_status()
        try:
            raw_payload = response.json()
        except ValueError as exc:
            raise ValueError("随机本子 API 返回的不是有效 JSON") from exc
        if not isinstance(raw_payload, Mapping):
            raise ValueError("随机本子 API 响应格式无效")

        gallery = self.parse_gallery(raw_payload)
        output_path = self._build_output_path(gallery, mode)
        try:
            if mode == "pdf":
                await self._create_pdf_from_urls(
                    client, gallery.page_urls, output_path, gallery.title
                )
            else:
                await self._create_archive_from_urls(
                    client, gallery.page_urls, output_path
                )
        except BaseException:
            output_path.unlink(missing_ok=True)
            raise
        return GeneratedDoujinshiFile(
            gallery=gallery,
            path=output_path,
            mode=mode,
        )

    @staticmethod
    def parse_gallery(payload: Mapping[str, object]) -> DoujinshiGallery:
        """将 API 响应校验为完整的本子元数据。"""
        gallery_id = payload.get("id")
        if not isinstance(gallery_id, int) or isinstance(gallery_id, bool):
            raise ValueError("随机本子 API 响应缺少有效 ID")

        raw_title = payload.get("title")
        upstream_title = DoujinshiService._resolve_upstream_title(raw_title)
        title = DoujinshiService._resolve_title(raw_title, gallery_id)
        source_url = DoujinshiService._resolve_source_url(payload.get("url"))
        page_urls = DoujinshiService._resolve_page_urls(payload.get("pages"))
        return DoujinshiGallery(
            id=gallery_id,
            title=title,
            page_urls=tuple(page_urls),
            upstream_title=upstream_title,
            source_url=source_url,
        )

    @staticmethod
    def create_pdf(pages: list[Image.Image], output_path: Path, title: str) -> None:
        """按下载顺序将所有页图写入一个多页 PDF。"""
        if not pages:
            raise ValueError("无法从空页图列表生成 PDF")

        prepared_pages = [DoujinshiService._prepare_pdf_page(page) for page in pages]
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            first_page, *remaining_pages = prepared_pages
            first_page.save(
                output_path,
                "PDF",
                save_all=True,
                append_images=remaining_pages,
                title=title,
                resolution=72.0,
            )
        finally:
            for page in prepared_pages:
                page.close()

    async def _create_pdf_from_urls(
        self,
        client: httpx.AsyncClient,
        page_urls: tuple[str, ...],
        output_path: Path,
        title: str,
    ) -> None:
        for page_number, page_url in enumerate(page_urls, start=1):
            try:
                response = await client.get(page_url, headers=self.REQUEST_HEADERS)
                response.raise_for_status()
                await asyncio.to_thread(
                    self._append_pdf_page,
                    output_path,
                    response.content,
                    title,
                    is_first_page=page_number == 1,
                )
            except (httpx.HTTPError, OSError) as exc:
                raise RuntimeError(
                    f"随机本子第 {page_number} 页下载或转换失败"
                ) from exc

    async def _create_archive_from_urls(
        self,
        client: httpx.AsyncClient,
        page_urls: tuple[str, ...],
        output_path: Path,
    ) -> None:
        """按页下载图片并写入 ZIP，成员名按页码保证客户端排序稳定。"""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(
            output_path, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as archive:
            for page_number, page_url in enumerate(page_urls, start=1):
                try:
                    response = await client.get(page_url, headers=self.REQUEST_HEADERS)
                    response.raise_for_status()
                    member_name = self._archive_member_name(
                        page_number,
                        page_url,
                        response.headers.get("content-type", ""),
                    )
                    # 压缩写入可能有一定 CPU 开销，放到线程中避免阻塞事件循环。
                    await asyncio.to_thread(
                        archive.writestr, member_name, response.content
                    )
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    raise RuntimeError(
                        f"随机本子第 {page_number} 页下载或压缩失败"
                    ) from exc

    def _build_output_path(self, gallery: DoujinshiGallery, mode: str) -> Path:
        self._output_dir.mkdir(parents=True, exist_ok=True)
        if mode == "pdf":
            suffix = ".pdf"
        elif mode == "archive":
            suffix = ".zip"
        else:
            raise ValueError(f"不支持的随机本子文件模式: {mode!r}")
        return self._output_dir / f"doujinshi-{gallery.id}-{uuid4().hex}{suffix}"

    @staticmethod
    def _normalize_mode(mode: object) -> str:
        value = getattr(mode, "value", mode)
        if not isinstance(value, str) or value not in {"pdf", "archive"}:
            raise ValueError("随机本子发送模式必须是 pdf 或 archive")
        return value

    @staticmethod
    def _archive_member_name(page_number: int, page_url: str, content_type: str) -> str:
        """从 URL 或响应类型推断扩展名，未知类型保留为 bin。"""
        suffix = Path(urlparse(page_url).path).suffix.lower()
        if not suffix or not suffix[1:].replace("_", "").replace("-", "").isalnum():
            media_type = content_type.split(";", 1)[0].strip().lower()
            suffix = mimetypes.guess_extension(media_type) or ".bin"
        return f"page-{page_number:04d}{suffix}"

    @staticmethod
    def _append_pdf_page(
        output_path: Path,
        page_bytes: bytes,
        title: str,
        *,
        is_first_page: bool,
    ) -> None:
        with Image.open(BytesIO(page_bytes)) as source:
            prepared_page = DoujinshiService._prepare_pdf_page(source)
        try:
            if is_first_page:
                prepared_page.save(
                    output_path,
                    "PDF",
                    title=title,
                    resolution=72.0,
                )
            else:
                prepared_page.save(output_path, "PDF", append=True)
        finally:
            prepared_page.close()

    @staticmethod
    def _prepare_pdf_page(page: Image.Image) -> Image.Image:
        normalized_page = ImageOps.exif_transpose(page)
        try:
            if (
                "A" in normalized_page.getbands()
                or "transparency" in normalized_page.info
            ):
                rgba_page = normalized_page.convert("RGBA")
                background = Image.new("RGB", rgba_page.size, "white")
                background.paste(rgba_page, mask=rgba_page.getchannel("A"))
                rgba_page.close()
                return background
            if normalized_page.mode == "RGB":
                return normalized_page.copy()
            return normalized_page.convert("RGB")
        finally:
            if normalized_page is not page:
                normalized_page.close()

    @staticmethod
    def _resolve_title(raw_title: object, gallery_id: int) -> str:
        return (
            DoujinshiService._resolve_upstream_title(raw_title)
            or f"随机本子 {gallery_id}"
        )

    @staticmethod
    def _resolve_upstream_title(raw_title: object) -> str | None:
        """提取可展示的上游标题，不把本地回退值伪装成上游元数据。"""
        if isinstance(raw_title, Mapping):
            for key in ("pretty", "english", "japanese"):
                value = raw_title.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        if isinstance(raw_title, str) and raw_title.strip():
            return raw_title.strip()
        return None

    @staticmethod
    def _resolve_source_url(raw_url: object) -> str | None:
        """仅保留上游提供的有效原始地址，缺失时交由发送器省略节点。"""
        if not isinstance(raw_url, str):
            return None
        source_url = raw_url.strip()
        if not source_url or not DoujinshiService._is_http_url(source_url):
            return None
        return source_url

    @staticmethod
    def _resolve_page_urls(raw_pages: object) -> list[str]:
        if not isinstance(raw_pages, list) or not raw_pages:
            raise ValueError("随机本子 API 响应不包含页图")

        page_urls: list[str] = []
        for page_number, raw_page in enumerate(raw_pages, start=1):
            if not isinstance(raw_page, Mapping):
                raise ValueError(f"随机本子第 {page_number} 页格式无效")
            raw_url = raw_page.get("url")
            if not isinstance(raw_url, str) or not DoujinshiService._is_http_url(
                raw_url
            ):
                raise ValueError(f"随机本子第 {page_number} 页缺少可下载的图片 URL")
            page_urls.append(raw_url)
        return page_urls

    @staticmethod
    def _is_http_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
