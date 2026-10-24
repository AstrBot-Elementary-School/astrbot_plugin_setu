"""Literal phrase templates and the three legacy natural-language grammars."""

from __future__ import annotations

import re
from dataclasses import dataclass
from string import Formatter

_BUILTINS = {
    "setu": r"/?来\s*(?P<count>.*?)(?:份|个|张|点)(?P<tags>.*?)(?:福利|色|瑟|涩|塞)?图(?:\s+(?P<r18>(?i:r18)))?",
    "doujinshi": r"/?来\s*(?:一\s*)?份(?P<tags>.*?)本子",
    "fortune": r"(今日运势|jrys)",
}


@dataclass(frozen=True)
class TriggerMatch:
    kind: str
    count: str = "1"
    tags: str = ""


def compile_trigger(kind: str, phrase: str) -> re.Pattern[str]:
    if not phrase.strip():
        return re.compile(_BUILTINS[kind])
    allowed = (
        {"数量", "标签"}
        if kind == "setu"
        else {"标签"}
        if kind == "doujinshi"
        else set()
    )
    seen: set[str] = set()
    parts = []
    for literal, name, spec, conversion in Formatter().parse(phrase):
        parts.append(re.escape(literal))
        if name is None:
            continue
        if name not in allowed or name in seen or spec or conversion:
            raise ValueError(f"{kind} 短语包含未知、重复或带格式的占位符：{{{name}}}")
        seen.add(name)
        parts.append(
            r"(?P<count>[0-9一二三四五六七八九十]*)"
            if name == "数量"
            else r"(?P<tags>.*?)"
        )
    return re.compile("".join(parts))


def match_trigger(message: str, templates) -> TriggerMatch | None:
    for template in templates:
        match = compile_trigger(template.template_key, template.phrase).fullmatch(
            message
        )
        if match:
            values = match.groupdict()
            tags = (values.get("tags") or "").strip()
            if values.get("r18"):
                tags = f"{tags} r18".strip()
            return TriggerMatch(
                template.template_key, (values.get("count") or "1").strip(), tags
            )
    return None
