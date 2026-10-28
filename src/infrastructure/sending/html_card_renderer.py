"""Render fallback image cards through AstrBot's configured t2i service."""

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from astrbot.core import html_renderer
from PIL import Image


class HtmlCardRenderer:
    async def render_single_image(
        self, *, context: Any, image: bytes, style_options: dict
    ) -> bytes:
        output = await html_renderer.render_custom_template(
            tmpl_str="""<!doctype html><html><body style="margin:0;padding:{{ padding }}px;background:white;width:fit-content"><img src="data:image/png;base64,{{ image }}" style="display:block"></body></html>""",
            tmpl_data={
                "padding": style_options.get("card_padding", 6),
                "image": base64.b64encode(image).decode("ascii"),
            },
            return_url=False,
            options={"full_page": True, "type": "png"},
        )
        data = output if isinstance(output, bytes) else Path(output).read_bytes()
        # AstrBot's downloader also returns HTTP error pages as files.
        with Image.open(BytesIO(data)) as rendered_image:
            rendered_image.verify()
        return data
