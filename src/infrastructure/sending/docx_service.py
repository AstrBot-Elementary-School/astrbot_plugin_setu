"""R18 图片 DOCX 封装。"""

from io import BytesIO
from pathlib import Path
from uuid import uuid4

from docx import Document
from PIL import Image


class R18DocxService:
    """按输入顺序将图片写入插件发送缓存。"""

    def __init__(self, data_dir: Path | str) -> None:
        self.root = Path(data_dir) / "send_cache"

    def create_docx_with_images(self, images: list[bytes], tags: list[str]) -> Path:
        if not images:
            raise ValueError("DOCX requires at least one image")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"r18-{uuid4().hex}.docx"
        partial = path.with_suffix(".docx.part")
        try:
            document = Document()
            document.core_properties.keywords = ", ".join(tags)
            section = document.sections[0]
            width = section.page_width - section.left_margin - section.right_margin
            # 段落行框也占页面高度，留出一行避免高图溢页。
            height = (
                section.page_height
                - section.top_margin
                - section.bottom_margin
                - 254000
            )
            for index, data in enumerate(images):
                with Image.open(BytesIO(data)) as image:
                    image.load()
                    stream = BytesIO(data)
                    if image.format not in {"JPEG", "PNG"}:
                        stream = BytesIO()
                        image.convert("RGB").save(stream, format="PNG")
                        stream.seek(0)
                    scale = min(width / image.width, height / image.height)
                    if index:
                        document.add_page_break()
                    document.add_picture(
                        stream,
                        width=int(image.width * scale),
                        height=int(image.height * scale),
                    )
            document.save(partial)
            partial.replace(path)
            return path
        except Exception:
            partial.unlink(missing_ok=True)
            raise
