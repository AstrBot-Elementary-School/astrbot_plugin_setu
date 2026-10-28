"""Today's fortune HTML renderer."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.core import html_renderer
from jinja2 import Template


class FortuneRenderer:
    """Render fortune cards to images via AstrBot's HTML renderer."""

    def __init__(self, template_path: Path | None = None) -> None:
        if template_path is None:
            template_path = (
                Path(__file__).resolve().parents[3] / "templates" / "fortune.html"
            )
        self.template_path = template_path
        self._fonts_dir = self.template_path.parent / "res" / "fonts"
        self._embedded_fonts_css: str | None = None

    def _get_embedded_fonts_css(self) -> str:
        if self._embedded_fonts_css is not None:
            return self._embedded_fonts_css

        fonts_config = [
            ("NotoSansSC-Regular", "NotoSansSC-Regular.woff2"),
            ("NotoSansSC-Bold", "NotoSansSC-Bold.woff2"),
            ("SSFangTangTi", "SSFangTangTi.woff2"),
        ]
        css_parts = ["    /* Embedded fonts - auto-generated */"]

        for font_name, file_name in fonts_config:
            font_path = self._fonts_dir / file_name
            try:
                if not font_path.exists():
                    logger.warning("[fortune] Font file not found: %s", font_path)
                    continue
                font_data = font_path.read_bytes()
                b64_data = base64.b64encode(font_data).decode("ascii")
                css_parts.append(
                    f"""    @font-face {{
      font-family: '{font_name}';
      src: url('data:font/woff2;base64,{b64_data}') format('woff2');
      font-weight: normal;
      font-style: normal;
      font-display: swap;
    }}"""
                )
            except OSError as exc:
                logger.error("[fortune] Failed to read font %s: %s", file_name, exc)

        self._embedded_fonts_css = "\n".join(css_parts)
        return self._embedded_fonts_css

    @staticmethod
    def _truncate_username(username: str, max_length: int = 15) -> str:
        return username[:max_length] + "..." if len(username) > max_length else username

    def _get_template(self) -> str:
        try:
            return self.template_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("[fortune] Failed to read template: %s", exc)
            return """<!DOCTYPE html>
<html><body style="width:480px;padding:20px;">
<div style="background:#f0f0f0;border-radius:10px;padding:20px;">
<h2>{{ username | e }} 的今日运势 ({{ date_str | e }})</h2>
<p>运势: {{ title | e }}</p>
<p>星级: {{ stars_display | safe }}</p>
<p>{{ description | e }}</p>
</div></body></html>"""

    @staticmethod
    def _format_stars(count: int, max_count: int = 7) -> str:
        stars_html = []
        for _ in range(count):
            stars_html.append('<span class="star-glyph">✦</span>')
        for _ in range(max_count - count):
            stars_html.append('<span class="star-glyph empty">✦</span>')
        return "".join(stars_html)

    def render(self, fortune: dict[str, Any], image_base64: str | None = None) -> str:
        template = self._get_template()
        data = self.build_template_data(fortune, image_base64=image_base64)
        return Template(template, autoescape=True).render(**data)

    def build_template_data(
        self, fortune: dict[str, Any], image_base64: str | None = None
    ) -> dict[str, Any]:
        """Build Jinja template data for fortune cards."""
        username = self._truncate_username(fortune.get("username", "用户"))
        return {
            "fonts_css": self._get_embedded_fonts_css(),
            "username": username,
            "date_str": fortune.get("date_str", ""),
            "title": fortune.get("title", "未知"),
            "stars_display": self._format_stars(
                fortune.get("star_count", 3), fortune.get("max_stars", 7)
            ),
            "description": fortune.get("description", ""),
            "extra_message": fortune.get("extra_message", ""),
            "theme_color": fortune.get("theme_color", "theme-gray"),
            "image_base64": image_base64 or "",
        }

    async def render_to_image(
        self, fortune: dict[str, Any], image_base64: str | None = None
    ) -> bytes | None:
        try:
            template = self._get_template()
            tmpl_data = self.build_template_data(fortune, image_base64=image_base64)
            output = await html_renderer.render_custom_template(
                tmpl_str=template,
                tmpl_data=tmpl_data,
                return_url=False,
                options={"full_page": True, "type": "png", "scale": "device"},
            )
            if output is None:
                return None
            if isinstance(output, bytes):
                return output
            if isinstance(output, str):
                path = Path(output)
                if path.exists():
                    if path.stat().st_size < 100:
                        return None
                    return path.read_bytes()
            return None
        except Exception as exc:  # noqa: BLE001 - Keep text fallback for t2i failures.
            logger.exception("[fortune] Failed to render image: %s", exc)
            return None
