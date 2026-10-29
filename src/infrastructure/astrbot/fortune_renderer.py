"""Today's fortune HTML renderer."""

from __future__ import annotations

import base64
import random
from pathlib import Path
from typing import Any

from astrbot.api import logger  # type: ignore[import-untyped,import-not-found]
from astrbot.core import (  # type: ignore[import-untyped,import-not-found]
    html_renderer,
)
from jinja2 import (  # type: ignore[import-untyped,import-not-found]
    Environment,
    Template,
    meta,
)

FORTUNE_THEME_TEMPLATES: dict[str, str] = {
    "default": "fortune.html",
    "endfield": "fortune_endfield.html",
    "blue_archive": "fortune_blue_archive.html",
}
RANDOM_THEME_POOL: tuple[str, ...] = ("endfield", "blue_archive")


class FortuneRenderer:
    """Render fortune cards to images via AstrBot's HTML renderer."""

    def __init__(
        self,
        template_path: Path | None = None,
        card_theme: str = "endfield",
    ) -> None:
        self._templates_dir = Path(__file__).resolve().parents[3] / "templates"
        self.card_theme = card_theme
        self._explicit_template_path = template_path
        self.template_path = template_path or self._resolve_template_path(card_theme)
        self._fonts_dir = self.template_path.parent / "res" / "fonts"
        self._embedded_fonts_css: str | None = None

    def _resolve_template_path(self, card_theme: str | None = None) -> Path:
        if self._explicit_template_path is not None:
            return self._explicit_template_path
        theme_key = self.card_theme if card_theme is None else card_theme
        if theme_key == "random":
            theme_key = random.choice(RANDOM_THEME_POOL)
        filename = FORTUNE_THEME_TEMPLATES[theme_key]
        return self._templates_dir / filename

    def _get_embedded_fonts_css(self) -> str:
        if self._embedded_fonts_css is not None:
            return self._embedded_fonts_css

        fonts_config = [
            ("NotoSansSC-Regular", "NotoSansSC-Regular.woff2", "woff2"),
            ("NotoSansSC-Bold", "NotoSansSC-Bold.woff2", "woff2"),
            ("SSFangTangTi", "SSFangTangTi.woff2", "woff2"),
            ("Novecentosanswide-Bold", "Novecentosanswide-Bold.woff2", "woff2"),
            ("SpaceGrotesk", "SpaceGrotesk.woff2", "woff2"),
            ("Gilroy-ExtraBold", "Gilroy-ExtraBold.woff2", "woff2"),
            ("TVPS-Vain-Capital-2", "TVPS-Vain-Capital-2.ttf", "truetype"),
        ]
        css_parts = ["    /* Embedded fonts - auto-generated */"]

        for font_name, file_name, fmt in fonts_config:
            font_path = self._fonts_dir / file_name
            font_data = font_path.read_bytes()
            b64_data = base64.b64encode(font_data).decode("ascii")
            mime = "font/ttf" if fmt == "truetype" else "font/woff2"
            css_parts.append(
                f"""    @font-face {{
  font-family: '{font_name}';
  src: url('data:{mime};base64,{b64_data}') format('{fmt}');
  font-weight: normal;
  font-style: normal;
  font-display: swap;
}}"""
            )

        self._embedded_fonts_css = "\n".join(css_parts)
        return self._embedded_fonts_css

    @staticmethod
    def _truncate_username(username: str, max_length: int = 15) -> str:
        return username[:max_length] + "..." if len(username) > max_length else username

    def _get_template(self, card_theme: str | None = None) -> str:
        target_path = self._resolve_template_path(card_theme)
        return target_path.read_text(encoding="utf-8")

    @staticmethod
    def _format_stars(count: int, max_count: int = 7) -> str:
        stars_html = []
        for _ in range(count):
            stars_html.append('<span class="star-glyph">✦</span>')
        for _ in range(max_count - count):
            stars_html.append('<span class="star-glyph empty">✦</span>')
        return "".join(stars_html)

    def render(
        self,
        fortune: dict[str, Any],
        image_base64: str | None = None,
        card_theme: str | None = None,
    ) -> str:
        template = self._get_template(card_theme=card_theme)
        data = self.build_template_data(fortune, image_base64, template=template)
        return Template(template, autoescape=True).render(**data)

    @staticmethod
    def template_variables(template: str) -> set[str]:
        return meta.find_undeclared_variables(Environment().parse(template))

    def build_template_data(
        self,
        fortune: dict[str, Any],
        image_base64: str | None = None,
        *,
        template: str | None = None,
    ) -> dict[str, Any]:
        """Only prepare values referenced by the selected template."""
        variables = self.template_variables(
            self._get_template() if template is None else template
        )
        data = {}
        for name in variables:
            if name == "fonts_css":
                data[name] = self._get_embedded_fonts_css()
            elif name == "username":
                data[name] = self._truncate_username(fortune[name])
            elif name == "stars_display":
                data[name] = self._format_stars(
                    fortune["star_count"], fortune["max_stars"]
                )
            elif name == "image_base64":
                data[name] = image_base64
            else:
                data[name] = fortune[name]
        return data

    async def render_to_image(
        self,
        fortune: dict[str, Any],
        image_base64: str | None = None,
        card_theme: str | None = None,
        *,
        template: str | None = None,
    ) -> bytes | None:
        try:
            if template is None:
                template = self._get_template(card_theme=card_theme)
            tmpl_data = self.build_template_data(
                fortune, image_base64, template=template
            )
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
            return Path(output).read_bytes()
        except Exception as exc:  # noqa: BLE001 - Keep text fallback for t2i failures.
            logger.exception("[fortune] Failed to render image: %s", exc)
            return None
