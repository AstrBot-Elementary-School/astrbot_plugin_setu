"""装配主题资源并调用 AstrBot 渲染。"""

import base64
import json
import mimetypes
import random
import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from jinja2 import Environment, StrictUndefined

THEMES = ("arona", "endfield", "persona5", "minecraft", "minimal")


class FortuneRenderer:
    def __init__(self, card_theme="endfield"):
        self.card_theme = card_theme
        self.root = Path(__file__).resolve().parents[2] / "template" / "fortune"
        self.environment = Environment(autoescape=True, undefined=StrictUndefined)
        self._assets = {}
        self.versions = {}

    def choose_theme(self, theme=None):
        selected = theme or self.card_theme
        if selected == "random":
            selected = random.choice(THEMES)
        if selected not in THEMES:
            raise ValueError(f"未知运势主题：{selected}")
        return selected

    def assets(self, theme):
        if theme not in self._assets:
            root = self.root / theme
            css = (root / "index.css").read_text()

            def embed(match):
                name = match.group(1).strip(" \"'")
                if name.startswith(("data:", "https:", "http:", "#")):
                    return match.group(0)
                path = (root / name).resolve()
                data = base64.b64encode(path.read_bytes()).decode()
                return f"url('data:{mimetypes.guess_type(path)[0] or 'application/octet-stream'};base64,{data}')"

            css = re.sub(r"url\(([^)]+)\)", embed, css)
            text = json.loads((root / "text.json").read_text())
            js = (root / "index.js").read_text() if (root / "index.js").exists() else ""
            source = (root / "index.jinja2").read_text()
            template = self.environment.from_string(source)
            self.versions[theme] = uuid5(
                NAMESPACE_URL, source + css + js + json.dumps(text, ensure_ascii=False)
            ).hex
            self._assets[theme] = (template, css, js, text)
        return self._assets[theme]

    def render(self, fortune, image=None, card_theme=None):
        template, css, js, text = self.assets(self.choose_theme(card_theme))
        return template.render(
            username=fortune["username"],
            date_str=fortune["date_str"],
            stars=fortune["stars"],
            image=image,
            css=css,
            js=js,
            text=text,
        )

    def format_text(self, record, theme):
        text = self.assets(theme)[3]
        return (
            f"{record.date_str} · {text['titles'][record.star_count]}\n{text['messages'][record.star_count]}"
            + (f"\n{text['tip']}" if text["tip"] else "")
        )

    async def render_to_image(self, fortune, image=None, card_theme=None):
        from astrbot.core import html_renderer

        template = self.render(fortune, image, card_theme)
        output = await html_renderer.render_custom_template(
            tmpl_str="{{ html | safe }}",
            tmpl_data={"html": template},
            return_url=False,
            options={"full_page": True, "type": "png", "scale": "device"},
        )
        return output if isinstance(output, bytes) else Path(output).read_bytes()
