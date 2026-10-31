"""Image sender service for adapter-level image delivery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import astrbot.api.message_components as Comp
from astrbot.api.event import AstrMessageEvent

from ...application.session_config import SessionConfigService
from ...application.setu.dto import ImagePayload
from ...shared import get_logger
from ...shared.cache import get_cache
from ...shared.config import should_auto_revoke
from ...shared.send_cache import get_send_cache
from ..astrbot.config import get_config, get_plugin_context
from ..astrbot.session_identity import get_event_session_identity
from .docx_service import R18DocxService
from .dto import SendAttemptResult, SendOptions
from .image_compressor import compress_image
from .image_sources import local_image_path, read_image_bytes
from .napcat_stream import upload_file_stream
from .platform_capabilities import is_onebot_like_platform, supports_forward_messages
from .revoke_scheduler import schedule_revoke
from .send_batching import estimate_base64_bytes, split_send_batches
from .send_strategies import (
    DirectSendStrategy,
    ForwardSendStrategy,
    resolve_send_mode,
)

ImageItem = Path | bytes | Comp.Image
logger = get_logger()


class ImageSender:
    """Send images with send-mode, stream-upload, and fallback strategies."""

    def __init__(
        self,
        config: Any = None,
        log: Any = None,
        *,
        docx_service: R18DocxService | None = None,
        content_type: Literal["setu", "fortune"] = "setu",
    ) -> None:
        self._docx_service = docx_service
        self._content_type = content_type
        self._user_config = config
        self._log = log or logger
        self._forward_supported_cache: dict[str, bool] = {}

    @property
    def _config(self):
        return self._user_config or get_config()

    @property
    def _context(self):
        ctx = get_plugin_context()
        if ctx is None:
            raise RuntimeError("Plugin context not initialized")
        return ctx

    async def _build_options(
        self, event: AstrMessageEvent, is_r18: bool = False
    ) -> SendOptions:
        config = self._config
        identity = get_event_session_identity(event)
        settings = SessionConfigService(config).resolve(identity.session_id)
        send_mode = settings.send_mode
        auto_revoke_scope = settings.auto_revoke_scope
        r18_docx_mode = settings.r18_docx_mode if is_r18 else False

        revoke_delay = config.auto_revoke_delay
        is_fortune = self._content_type == "fortune"
        if is_fortune:
            send_mode = "image"
            r18_docx_mode = False
            auto_revoke_scope = "none"
        return SendOptions(
            send_mode=send_mode,
            auto_revoke=(
                config.auto_revoke_fortune_enabled and revoke_delay > 0
                if is_fortune
                else config.auto_revoke_setu_enabled
                and revoke_delay > 0
                and should_auto_revoke(auto_revoke_scope, is_r18)
            ),
            auto_revoke_scope=auto_revoke_scope,
            revoke_delay=revoke_delay,
            r18_docx_mode=r18_docx_mode,
            napcat_stream_mode=config.napcat_stream_mode,
            napcat_stream_chunk_kb=config.napcat_stream_chunk_kb,
            napcat_local_file_mode=config.napcat_local_file_mode,
            napcat_local_file_allowed_roots=tuple(
                config.napcat_local_file_allowed_roots
            ),
            compress_enabled=config.compress_enabled,
            compress_max_mb=config.compress_max_mb,
        )

    async def send_images(self, payload, event):
        pending = False
        try:
            async for result in self._send_images(payload, event):
                if isinstance(result, dict):
                    pending = pending or result.get("send_pending", False)
                yield result
        finally:
            if not pending:
                for path in payload.file_paths:
                    get_cache().release(path, keep=self._config.cache.setu)

    async def _send_images(
        self,
        payload: ImagePayload,
        event: AstrMessageEvent,
    ) -> AsyncGenerator[Any, None]:
        """Send a fetched image payload to the current AstrBot event."""
        options = await self._build_options(event, payload.r18)
        items = self._payload_items(payload)
        self._log_send_summary(event, payload, items, options)
        if not items:
            self._log.warning(
                "[send] empty payload: session=%s, tags=%s, urls=%d",
                self._session_label(event),
                ",".join(payload.tags) or "-",
                len(payload.urls),
            )
            empty_message = self._resolve_message("empty_payload")
            if empty_message:
                yield event.plain_result(empty_message)
            return

        if payload.r18 and options.r18_docx_mode:
            try:
                docx_images = await self._read_image_bytes(items)
                if len(docx_images) != len(items):
                    raise ValueError("Failed to read all DOCX images")
                async for result in self._send_r18_docx(
                    event, docx_images, payload.tags, options
                ):
                    yield result
            except Exception:  # noqa: BLE001 - 封装/平台边界统一报告并终止 R18 分支
                self._log.exception("[send] R18 DOCX generation or delivery failed")
                message = self._resolve_message("r18_docx_failed")
                if message:
                    yield event.plain_result(message)
            return

        original_chain = self._build_image_chain(items)
        chain = original_chain

        supports_forward = self._is_forward_supported(event)
        effective_mode = resolve_send_mode(
            options.send_mode, payload.count, supports_forward
        )

        # 压图预处理:若启用,对本地文件/bytes 图压缩后重建 chain
        if options.compress_enabled:
            chain = await self._compress_chain(chain, options.compress_max_mb)

        # 估算每张图的 base64 体积,用于分批
        base64_sizes = await self._estimate_chain_sizes(chain)
        batch_indices = split_send_batches(base64_sizes, effective_mode)

        self._log.info(
            "[send] dispatch: session=%s, platform=%s, mode=%s, compress=%s, "
            "batches=%d (images=%d)",
            self._session_label(event),
            self._get_platform_name(event) or "unknown",
            effective_mode,
            options.compress_enabled,
            len(batch_indices),
            len(chain),
        )

        # 逐批发送,聚合结果
        any_pending = False
        any_failed = False
        all_failed = True

        for batch_idx, indices in enumerate(batch_indices):
            batch_chain = [chain[i] for i in indices]
            original_batch_chain = [original_chain[i] for i in indices]
            batch_num = batch_idx + 1
            send_result = await self._send_one_batch(
                event,
                batch_chain,
                original_batch_chain,
                effective_mode,
                options,
                batch_num,
                len(batch_indices),
            )
            if send_result.accepted:
                all_failed = False
                await self._schedule_revoke_for_result(event, send_result, options)
                if send_result.pending:
                    any_pending = True
            else:
                any_failed = True

        # 聚合结果决定最终 yield
        if all_failed:
            self._log.warning(
                "[send] all batches failed: session=%s, count=%d, mode=%s",
                self._session_label(event),
                payload.count,
                effective_mode,
            )
            fail_message = self._send_failed_message()
            if fail_message:
                yield event.plain_result(fail_message)
        elif any_failed:
            self._log.warning(
                "[send] partial batch failure: session=%s, count=%d, mode=%s",
                self._session_label(event),
                payload.count,
                effective_mode,
            )
            fail_message = self._send_failed_message()
            if fail_message:
                yield event.plain_result(fail_message)
            result: dict[str, Any] = {
                "send_success": False,
                "image_count": payload.count,
                "partial_failure": True,
            }
            if any_pending:
                result["send_pending"] = True
            yield result
        else:
            if any_pending:
                self._log.warning(
                    "[send] some batches pending: session=%s, count=%d, mode=%s",
                    self._session_label(event),
                    payload.count,
                    effective_mode,
                )
                yield {
                    "send_success": True,
                    "image_count": payload.count,
                    "send_pending": True,
                }
            else:
                self._log.info(
                    "[send] completed: session=%s, count=%d, mode=%s, batches=%d",
                    self._session_label(event),
                    payload.count,
                    effective_mode,
                    len(batch_indices),
                )
                yield {"send_success": True, "image_count": payload.count}

    async def _send_chain(
        self,
        event: AstrMessageEvent,
        chain: list[Comp.Image],
        effective_mode: str,
        options: SendOptions,
    ) -> SendAttemptResult:
        """Send an already-built image chain."""
        if effective_mode != "forward" and options.napcat_stream_mode == "always":
            self._log.info(
                "[send] pre-upload via NapCat stream: session=%s, count=%d",
                self._session_label(event),
                len(chain),
            )
            streamed_chain, changed = await self._stream_upload_chain(
                event, chain, options
            )
            if changed:
                chain = streamed_chain

        if effective_mode == "forward":
            chain = await self._materialize_local_chain(chain)
            return await ForwardSendStrategy(self._context).send_with_status(
                event, chain, options.auto_revoke
            )
        chain = await self._materialize_local_chain(chain)
        return await DirectSendStrategy(self._context).send_with_status(
            event, chain, options.auto_revoke
        )

    async def _materialize_local_chain(
        self, chain: list[Comp.Image]
    ) -> list[Comp.Image]:
        """Convert readable local-file images to in-memory payloads before send."""
        materialized: list[Comp.Image] = []
        for comp in chain:
            file_path = self._local_file_path(comp)
            if file_path is None:
                materialized.append(comp)
                continue
            try:
                data = await asyncio.to_thread(file_path.read_bytes)
            except OSError as exc:
                self._log.warning(
                    "[send] failed to read image before send: path=%s, error=%s",
                    file_path,
                    exc,
                )
                materialized.append(comp)
                continue
            self._log.debug("[send] materialized local image: path=%s", file_path)
            materialized.append(Comp.Image.fromBytes(data))
        return materialized

    async def _compress_chain(
        self, chain: list[Comp.Image], max_mb: int
    ) -> list[Comp.Image]:
        """Compress images in chain that exceed the target size."""
        max_bytes = max_mb * 1024 * 1024
        compressed: list[Comp.Image] = []
        for comp in chain:
            data = await self._read_comp_bytes(comp)
            if data is None or len(data) <= max_bytes:
                compressed.append(comp)
                continue
            compressed_data = await asyncio.to_thread(
                compress_image, data, max_bytes=max_bytes
            )
            compressed.append(Comp.Image.fromBytes(compressed_data))
        return compressed

    async def _read_comp_bytes(self, comp: Comp.Image) -> bytes | None:
        """Extract bytes from a Comp.Image, returning None if not file/base64."""
        return await read_image_bytes(comp)

    async def _estimate_chain_sizes(self, chain: list[Comp.Image]) -> list[int]:
        """Estimate base64 byte size for each image in chain."""
        sizes: list[int] = []
        for comp in chain:
            file_path = self._local_file_path(comp)
            if file_path and file_path.exists():
                raw_size = file_path.stat().st_size
                sizes.append(estimate_base64_bytes(raw_size))
                continue
            data = await self._read_comp_bytes(comp)
            if data:
                sizes.append(estimate_base64_bytes(len(data)))
            else:
                sizes.append(1024 * 1024)  # 1MB fallback estimate
        return sizes

    async def _send_one_batch(
        self,
        event: AstrMessageEvent,
        batch_chain: list[Comp.Image],
        original_batch_chain: list[Comp.Image],
        effective_mode: str,
        options: SendOptions,
        batch_num: int,
        total_batches: int,
    ) -> SendAttemptResult:
        """Send one batch with fallback logic (NapCat transport)."""
        self._log.info(
            "[send] batch %d/%d: session=%s, images=%d, mode=%s",
            batch_num,
            total_batches,
            self._session_label(event),
            len(batch_chain),
            effective_mode,
        )
        send_result: SendAttemptResult | None = None

        if effective_mode != "forward" and options.napcat_local_file_mode == "always":
            send_result = await self._try_local_file_passthrough(
                event, original_batch_chain, options
            )
            if send_result.accepted:
                return send_result

        send_result = await self._send_chain(
            event, batch_chain, effective_mode, options
        )

        if (
            not send_result.accepted
            and effective_mode != "forward"
            and options.napcat_local_file_mode == "fallback"
        ):
            self._log.warning(
                "[send] batch %d failed, trying NapCat local file passthrough: "
                "session=%s",
                batch_num,
                self._session_label(event),
            )
            local_result = await self._try_local_file_passthrough(
                event, original_batch_chain, options
            )
            if local_result.accepted:
                send_result = local_result

        # 合并转发保留自身的发送结果。
        if (
            not send_result.accepted
            and effective_mode != "forward"
            and options.napcat_stream_mode == "fallback"
            and self._has_local_image_paths(batch_chain)
        ):
            self._log.warning(
                "[send] batch %d failed, trying NapCat stream: session=%s",
                batch_num,
                self._session_label(event),
            )
            streamed, changed = await self._stream_upload_chain(
                event, batch_chain, options
            )
            if changed:
                retry_options = self._without_stream_upload(options)
                send_result = await self._send_chain(
                    event, streamed, effective_mode, retry_options
                )

        return send_result

    def _without_stream_upload(self, options: SendOptions) -> SendOptions:
        """Return options for a retry after stream upload has already run."""
        return replace(options, napcat_stream_mode="disabled")

    async def _send_r18_docx(
        self,
        event: AstrMessageEvent,
        images: tuple[bytes, ...],
        tags: tuple[str, ...],
        options: SendOptions,
    ) -> AsyncGenerator[Any, None]:
        """Generate and send a DOCX without falling back to images."""
        if self._docx_service is None:
            raise RuntimeError("R18 DOCX service is not initialized")
        docx_path = await asyncio.to_thread(
            self._docx_service.create_docx_with_images, list(images), list(tags)
        )
        pending = False
        try:
            send_result = await DirectSendStrategy(self._context).send_with_status(
                event,
                [Comp.File(file=str(docx_path), name=docx_path.name)],
                options.auto_revoke,
            )
            pending = send_result.pending
            if not send_result.accepted:
                fail_message = self._resolve_message("r18_docx_failed")
                if fail_message:
                    yield event.plain_result(fail_message)
                return

            await self._schedule_revoke_for_result(event, send_result, options)
            if send_result.pending:
                yield {
                    "send_success": True,
                    "image_count": len(images),
                    "send_pending": True,
                }
            else:
                yield {"send_success": True, "image_count": len(images)}

        finally:
            if not pending:
                get_cache().release(docx_path, keep=self._config.cache.setu)

    def _payload_items(self, payload: ImagePayload) -> tuple[ImageItem, ...]:
        return payload.items or (*payload.file_paths, *payload.raw_bytes)

    def _build_image_chain(self, images: tuple[ImageItem, ...]) -> list[Comp.Image]:
        chain = []
        for item in images:
            if isinstance(item, Comp.Image):
                chain.append(item)
            elif isinstance(item, bytes):
                chain.append(Comp.Image.fromBytes(item))
            elif isinstance(item, Path):
                chain.append(Comp.Image.fromFileSystem(str(item)))
        return chain

    async def _read_image_bytes(
        self, images: tuple[ImageItem, ...]
    ) -> tuple[bytes, ...]:
        """Materialize image items as bytes for DOCX output."""
        result: list[bytes] = []
        for item in images:
            if isinstance(item, bytes):
                result.append(item)
            elif isinstance(item, Path):
                try:
                    result.append(await asyncio.to_thread(item.read_bytes))
                except OSError as exc:
                    self._log.warning(
                        "[send] failed to read cached image: path=%s, error=%s",
                        item,
                        exc,
                    )
            elif isinstance(item, Comp.Image):
                try:
                    file_path = await item.convert_to_file_path()
                    result.append(await asyncio.to_thread(Path(file_path).read_bytes))
                except Exception as exc:
                    self._log.warning(
                        "[send] failed to read image component: file=%s, error=%s",
                        getattr(item, "file", None),
                        exc,
                    )
        return tuple(result)

    async def _try_local_file_passthrough(
        self,
        event: AstrMessageEvent,
        chain: list[Comp.Image],
        options: SendOptions,
    ) -> SendAttemptResult:
        """Try trusted local file passthrough through raw OneBot image action."""
        platform_name = self._get_platform_name(event)
        if not is_onebot_like_platform(platform_name):
            return SendAttemptResult.failed("platform is not OneBot-like")

        passthrough_chain = self._local_file_passthrough_chain(chain, options)
        if passthrough_chain is None:
            return SendAttemptResult.failed("no trusted local image path")

        self._log.info(
            "[send] trying NapCat local file passthrough: session=%s, count=%d",
            self._session_label(event),
            len(passthrough_chain),
        )
        return await DirectSendStrategy(
            self._context, allow_file_uri_passthrough=True
        ).send_with_status(event, passthrough_chain, options.auto_revoke)

    def _local_file_passthrough_chain(
        self, chain: list[Comp.Image], options: SendOptions
    ) -> list[Comp.Image] | None:
        """Build a file:// chain only when every local path is trusted."""
        converted: list[Comp.Image] = []
        changed = False
        for comp in chain:
            file_path = self._local_file_path(comp)
            if file_path is None:
                converted.append(comp)
                continue

            trusted_path = self._trusted_local_file_path(file_path, options)
            if trusted_path is None:
                self._log.debug(
                    "[send] local file passthrough rejected: path=%s", file_path
                )
                return None

            converted.append(Comp.Image(file=trusted_path.as_uri()))
            changed = True

        return converted if changed else None

    def _trusted_local_file_path(self, path: Path, options: SendOptions) -> Path | None:
        """Return a resolved file path if it is under an allowed local root."""
        try:
            resolved = path.expanduser().resolve(strict=True)
        except OSError:
            return None
        if not resolved.is_file():
            return None

        for root in self._allowed_local_file_roots(options):
            if self._path_is_relative_to(resolved, root):
                return resolved
        return None

    def _allowed_local_file_roots(self, options: SendOptions) -> tuple[Path, ...]:
        """Return send-cache root plus explicitly configured shared roots."""
        roots: list[Path] = []
        cache = get_send_cache()
        cache_root = getattr(cache, "root", None)
        if cache_root:
            roots.append(Path(cache_root))

        for raw_root in options.napcat_local_file_allowed_roots:
            root_text = str(raw_root).strip()
            if root_text:
                roots.append(Path(root_text))

        normalized: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            try:
                resolved = root.expanduser().resolve(strict=False)
            except OSError:
                continue
            if not resolved.is_absolute():
                continue
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(resolved)
        return tuple(normalized)

    def _path_is_relative_to(self, path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            return False

    async def _stream_upload_chain(
        self, event: AstrMessageEvent, chain: list[Comp.Image], options: SendOptions
    ) -> tuple[list[Comp.Image], bool]:
        """Upload local image files through NapCat Stream API and rebuild the chain."""
        changed = False
        streamed: list[Comp.Image] = []
        for comp in chain:
            file_path = self._local_file_path(comp)
            if file_path is None:
                streamed.append(comp)
                continue

            uploaded_path = await upload_file_stream(
                event,
                file_path,
                chunk_size=self._stream_chunk_size(options),
            )
            if uploaded_path:
                self._log.debug(
                    "[send] stream upload success: local=%s, remote=%s",
                    file_path,
                    uploaded_path,
                )
                streamed.append(self._image_from_ref(uploaded_path))
                changed = True
            else:
                self._log.warning(
                    "[send] stream upload failed, keep original image: local=%s",
                    file_path,
                )
                streamed.append(comp)
        return streamed, changed

    def _stream_chunk_size(self, options: SendOptions) -> int:
        return max(1, int(options.napcat_stream_chunk_kb or 64)) * 1024

    def _has_local_image_paths(self, chain: list[Comp.Image]) -> bool:
        return any(self._local_file_path(comp) is not None for comp in chain)

    def _local_file_path(self, comp: Comp.Image) -> Path | None:
        return local_image_path(getattr(comp, "path", None)) or local_image_path(
            getattr(comp, "file", None)
        )

    def _image_from_ref(self, ref: str | Path) -> Comp.Image:
        text = str(ref)
        if text.startswith("file:///"):
            return Comp.Image(file=text)
        path = local_image_path(ref)
        if path is not None:
            return Comp.Image.fromFileSystem(str(path))
        return Comp.Image(file=text)

    def _is_forward_supported(self, event: AstrMessageEvent) -> bool:
        """Check if platform supports forward messages (cached per platform)."""
        platform_name = self._get_platform_name(event)
        if platform_name in self._forward_supported_cache:
            return self._forward_supported_cache[platform_name]

        supported = self._check_forward_support(platform_name, event)
        self._forward_supported_cache[platform_name or ""] = supported
        return supported

    def _get_platform_name(self, event: AstrMessageEvent) -> str | None:
        """Extract platform name from event."""
        if hasattr(event, "platform") and event.platform:
            if hasattr(event.platform, "name"):
                return event.platform.name

        if hasattr(event, "get_platform_name"):
            try:
                return event.get_platform_name()
            except Exception:
                pass

        return None

    def _check_forward_support(
        self, platform_name: str | None, event: AstrMessageEvent
    ) -> bool:
        """Check forward support from platform info."""
        has_call_action = bool(
            not platform_name
            and hasattr(event, "bot")
            and event.bot
            and hasattr(event.bot, "call_action")
        )
        return supports_forward_messages(
            platform_name,
            has_call_action=has_call_action,
        )

    async def _schedule_revoke_for_result(
        self,
        event: AstrMessageEvent,
        send_result: SendAttemptResult,
        options: SendOptions,
    ) -> int:
        """Schedule revokes for every message id carried by one send result."""
        if not options.auto_revoke:
            return 0
        if not send_result.message_ids:
            self._log.warning(
                "[revoke] cannot schedule: no message_id returned, session=%s, scope=%s",
                self._session_label(event),
                options.auto_revoke_scope,
            )
            return 0

        scheduled = 0
        for message_id in send_result.message_ids:
            if await schedule_revoke(event, message_id, options.revoke_delay):
                scheduled += 1
        return scheduled

    def _send_failed_message(self) -> str | None:
        return self._resolve_message("send_failed")

    def _resolve_message(self, key: str, **kwargs: Any) -> str | None:
        return self._config.resolve_message(key, **kwargs)

    def _log_send_summary(
        self,
        event: AstrMessageEvent,
        payload: ImagePayload,
        items: tuple[ImageItem, ...],
        options: SendOptions,
    ) -> None:
        local_paths = sum(isinstance(item, Path) for item in items)
        raw_bytes = sum(isinstance(item, bytes) for item in items)
        image_components = sum(isinstance(item, Comp.Image) for item in items)
        self._log.info(
            "[send] payload ready: session=%s, platform=%s, count=%d, "
            "r18=%s, tags=%s, items=%d(paths=%d,bytes=%d,components=%d), "
            "config_mode=%s, napcat_stream=%s, "
            "stream_chunk_kb=%d, local_file=%s",
            self._session_label(event),
            self._get_platform_name(event) or "unknown",
            payload.count,
            payload.r18,
            ",".join(payload.tags) or "-",
            len(items),
            local_paths,
            raw_bytes,
            image_components,
            options.send_mode,
            options.napcat_stream_mode,
            options.napcat_stream_chunk_kb,
            options.napcat_local_file_mode,
        )

    def _session_label(self, event: AstrMessageEvent) -> str:
        group_id = event.get_group_id()
        sender_id = event.get_sender_id()
        if group_id:
            return f"group:{group_id}/user:{sender_id}"
        return f"user:{sender_id}"
