"""随机本子文件的发送链构造。"""

from __future__ import annotations

import re

import astrbot.api.message_components as Comp

from ..doujinshi import GeneratedDoujinshiFile


def build_doujinshi_file_chain(
    generated: GeneratedDoujinshiFile,
) -> list[Comp.BaseMessageComponent]:
    """构造普通文件消息链。"""
    file_name = get_doujinshi_file_name(generated)
    return [Comp.File(name=file_name, file=str(generated.path))]


def get_doujinshi_file_name(generated: GeneratedDoujinshiFile) -> str:
    """使用本子标题作为文件名，并移除平台不接受的路径字符。"""
    title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", generated.gallery.title).strip(" .")
    if not title:
        title = f"随机本子-{generated.gallery.id}"
    mode = getattr(generated, "mode", "pdf")
    mode_value = getattr(mode, "value", mode)
    if mode_value == "pdf":
        suffix = ".pdf"
    elif mode_value == "archive":
        suffix = ".zip"
    else:
        raise ValueError(f"不支持的随机本子文件模式: {mode_value!r}")
    return f"{title}{suffix}"


__all__ = ["build_doujinshi_file_chain", "get_doujinshi_file_name"]
