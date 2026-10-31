"""运势命令、个人偏好和 LLM 工具。"""

import asyncio
import base64
import json
import random
from contextlib import asynccontextmanager
from io import BytesIO
from uuid import NAMESPACE_URL, uuid5

import astrbot.api.message_components as Comp
import httpx
from astrbot.core.provider.register import llm_tools
from PIL import Image

from ....application.session_config import SessionConfigService
from ....application.setu import ImagePayload
from ....domain import HTTP_TIMEOUT_SECONDS
from ....domain.access_control.service import AccessControlService
from ....domain.fortune import FortuneGenerationRequest
from ....domain.fortune.service import FortuneService
from ....domain.setu import SetuRequest
from ....shared import get_logger
from ....shared.cache import get_cache
from ...permission_service import PermissionService
from ...persistence import get_access_control_repo, get_fortune_repo
from ...persistence.database import get_database
from ...providers import get_provider
from ...sending import ImageSender
from ..config import get_config
from ..fortune_renderer import THEMES, FortuneRenderer
from ..session_identity import get_event_session_identity

logger = get_logger()


class FortuneCommandHandler:
    def __init__(self):
        self.renderer = FortuneRenderer()
        self.locks = {}

    @asynccontextmanager
    async def _user_lock(self, session_id, user_id):
        key = user_id
        entry = self.locks.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                del self.locks[key]

    async def _access(self, event):
        if not get_config().fortune.enabled:
            raise ValueError("今日运势已关闭。")
        if not AccessControlService(get_access_control_repo()).check_access(
            "fortune", get_event_session_identity(event).session_id
        ):
            raise PermissionError("当前会话没有今日运势的使用权限。")

    def request(self, event, user_id=None):
        return FortuneGenerationRequest.for_today(
            str(user_id or event.get_sender_id()),
            event.get_sender_name(),
            get_event_session_identity(event).session_id,
        )

    async def _get(self, event):
        await self._access(event)
        request = self.request(event)
        async with self._user_lock(request.session_id, request.user_id):
            record = await FortuneService(get_fortune_repo()).get_or_create_fortune(
                request
            )
            pref = await get_database().preference(str(event.get_sender_id()))
            theme = self.renderer.choose_theme(
                pref["theme"] or get_config().fortune.card_theme.value,
                random_themes=get_config().fortune.random_themes,
            )
            try:
                image = await self.render(event, record, request.username, pref, theme)
            except Exception as exc:
                logger.exception("运势卡片生成失败")
                return (
                    self.renderer.format_text(record, theme) + f"\n卡片生成失败：{exc}"
                )
            payload = ImagePayload(urls=(), raw_bytes=(image,), r18=False, tags=())
            async for result in ImageSender(
                get_config(), logger, content_type="fortune"
            ).send_images(payload, event):
                if isinstance(result, dict) and result.get("send_success"):
                    return "ok"
            return self.renderer.format_text(record, theme) + "\n卡片发送失败。"

    async def fortune_command(self, event):
        try:
            result = await self._get(event)
            if result != "ok":
                yield event.plain_result(result)
        except Exception as exc:
            logger.exception("获取运势失败")
            yield event.plain_result(f"获取运势失败：{exc}")
        event.stop_event()

    async def refresh(self, event, target=None):
        await self._access(event)
        if target is not None or not get_config().fortune.allow_user_refresh:
            allowed, message = PermissionService.require_admin(event)
            if not allowed:
                raise PermissionError(message)
        request = self.request(event, target)
        async with self._user_lock(request.session_id, request.user_id):
            await FortuneService(get_fortune_repo()).refresh_fortune(request)
        return (
            f"已刷新{'该用户' if target is not None else '你'}在当前会话中的今日运势。"
        )

    async def refresh_fortune_command(self, event):
        try:
            targets = [
                str(component.qq)
                for component in event.get_messages()
                if isinstance(component, Comp.At)
                and str(component.qq) != str(event.get_self_id())
            ]
            if len(targets) > 1:
                raise ValueError("每次请只 At 一位用户。")
            yield event.plain_result(
                await self.refresh(event, targets[0] if targets else None)
            )
        except Exception as exc:
            yield event.plain_result(f"刷新失败：{exc}")

    async def refresh_all(self, event):
        await self._access(event)
        allowed, message = PermissionService.require_super_user(event)
        if not allowed:
            raise PermissionError(message)
        count = await FortuneService(get_fortune_repo()).refresh_all_fortunes()
        return f"已清理今天的 {count} 条运势，下次查看时重新生成。"

    async def refresh_all_fortune_command(self, event):
        try:
            yield event.plain_result(await self.refresh_all(event))
        except Exception as exc:
            yield event.plain_result(f"全局刷新失败：{exc}")

    async def preference(self, event, field=None, value=None):
        await self._access(event)
        async with self._user_lock(None, str(event.get_sender_id())):
            user_id = str(event.get_sender_id())
            if field is not None:
                if field == "theme" and value is not None:
                    value = self.renderer.resolve_theme(value)
                await get_database().set_preference(user_id, field, value)
                # 用户偏好跨会话共享，所有相关卡片随偏好失效。
                rows = await (
                    await get_database().connection.execute(
                        "SELECT id,session_id FROM daily_fortune WHERE user_id=?",
                        (str(event.get_sender_id()),),
                    )
                ).fetchall()
                for row in rows:
                    get_fortune_repo().invalidate(row["id"])
                    if field == "tags":
                        async with get_database().transaction() as db:
                            await db.execute(
                                "UPDATE daily_fortune SET setu_history_id=NULL WHERE id=?",
                                (row["id"],),
                            )
            pref = await get_database().preference(user_id)
            return f"主题：{pref['theme'] or '使用默认主题'}\n搜索标签：{'、'.join(json.loads(pref['tags'])) if pref['tags'] is not None else '使用会话配置或默认标签'}\n可选主题：{'、'.join((*THEMES, 'random'))}"

    async def render(self, event, record, username, pref, theme):
        cache = get_cache()
        db = get_database()
        row = await (
            await db.connection.execute(
                "SELECT setu_history_id FROM daily_fortune WHERE id=?", (record.id,)
            )
        ).fetchone()
        history_id = row["setu_history_id"]
        display = {
            "username": username,
            "date_str": record.date_str,
            "stars": record.star_count,
        }
        self.renderer.assets(theme)
        rendered = json.dumps(
            [display, theme, self.renderer.versions[theme]], ensure_ascii=False
        )

        def card_path(image_id):
            key = uuid5(NAMESPACE_URL, rendered + str(image_id)).hex
            return cache.root / "fortune" / f"{record.id}-{key}.png"

        path = card_path(history_id)
        if get_config().cache.fortune and cache.acquire(path):
            try:
                return await asyncio.to_thread(path.read_bytes)
            finally:
                cache.release(path, keep=True)

        image = None
        if history_id is not None:
            history = await (
                await db.connection.execute(
                    "SELECT image_url FROM setu_history WHERE id=?", (history_id,)
                )
            ).fetchone()
            async with httpx.AsyncClient(
                timeout=HTTP_TIMEOUT_SECONDS, follow_redirects=True
            ) as client:
                response = await client.get(history["image_url"])
                response.raise_for_status()
                image = response.content
        else:
            settings = SessionConfigService(get_config()).resolve(record.session_id)
            tags = (
                json.loads(pref["tags"])
                if pref["tags"] is not None
                else [
                    tag.strip()
                    for tag in settings.fortune_tags.split(",")
                    if tag.strip()
                ]
            )
            r18 = settings.fortune_content_mode == "r18" or (
                settings.fortune_content_mode == "mix" and random.random() > 0.5
            )
            ids = []

            async def record_images(images):
                ids.extend(
                    await db.add_history(
                        record.session_id, record.user_id, images, tags
                    )
                )

            payload = await get_provider().fetch_and_download(
                SetuRequest.from_user_input(
                    count=1,
                    tags=tags,
                    r18=r18,
                    exclude_ai=get_config().exclude_ai,
                    max_replenish_rounds=get_config().max_replenish_rounds,
                ),
                on_images=record_images,
            )
            try:
                if payload.items:
                    item = payload.items[0]
                    image = (
                        item
                        if isinstance(item, bytes)
                        else await asyncio.to_thread(item.read_bytes)
                    )
                    image_index = next(
                        i
                        for i, metadata in enumerate(payload.images)
                        if metadata.image_url == payload.urls[0]
                    )
                    history_id = ids[image_index]
                    await get_fortune_repo().attach_image(record.id, history_id)
                    path = card_path(history_id)
            finally:
                for file in payload.file_paths:
                    cache.release(file, keep=get_config().cache.setu)
        encoded = None
        if image:
            with Image.open(BytesIO(image)) as decoded:
                mime = Image.MIME[decoded.format]
            encoded = f"data:{mime};base64," + base64.b64encode(image).decode()
        result = await self.renderer.render_to_image(
            {
                "username": username,
                "date_str": record.date_str,
                "stars": record.star_count,
            },
            encoded,
            theme,
        )
        if get_config().cache.fortune:
            async with db.lock:
                current = await (
                    await db.connection.execute(
                        "SELECT stars,setu_history_id FROM daily_fortune WHERE id=?",
                        (record.id,),
                    )
                ).fetchone()
                if (
                    current is not None
                    and current["stars"] == record.star_count
                    and current["setu_history_id"] == history_id
                ):
                    await asyncio.to_thread(cache.write, path, result)
        return result

    async def _llm_get_fortune(self, event):
        return await self._get(event)

    async def _llm_refresh_fortune(self, event):
        return await self.refresh(event)

    async def _llm_refresh_all_fortune(self, event):
        return await self.refresh_all(event)

    async def _llm_refresh_group_fortune(self, event):
        await self._access(event)
        allowed, message = PermissionService.require_admin(event)
        if not allowed:
            raise PermissionError(message)
        if not event.get_group_id():
            raise ValueError("请在群聊中刷新本群运势。")
        count = await FortuneService(get_fortune_repo()).refresh_group_fortunes(
            get_event_session_identity(event).session_id
        )
        return f"已清理本群今天的 {count} 条运势。"


TOOL_HANDLERS = {
    "get_today_fortune": "_llm_get_fortune",
    "refresh_my_fortune": "_llm_refresh_fortune",
    "refresh_group_fortune": "_llm_refresh_group_fortune",
    "refresh_all_fortune": "_llm_refresh_all_fortune",
}


def register_llm_tools(handler):
    for name, method in TOOL_HANDLERS.items():
        llm_tools.add_func(
            name=name,
            func_args=[],
            desc={
                "get_today_fortune": "发送当前会话中的个人今日运势。",
                "refresh_my_fortune": "按用户明确要求刷新本人的今日运势。",
                "refresh_group_fortune": "按管理员明确要求刷新本群今日运势。",
                "refresh_all_fortune": "按超级管理员明确要求刷新全局今日运势。",
            }[name],
            handler=getattr(handler, method),
        )
        llm_tools.get_func(name).handler_module_path = __name__


def unregister_llm_tools():
    for name in TOOL_HANDLERS:
        if llm_tools.get_func(name) is not None:
            llm_tools.remove_func(name)
