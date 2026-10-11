import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
)


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def annotate_image(image: Image.Image, objects: list[dict]) -> bytes:
    annotated = image.copy().convert("RGBA")
    draw = ImageDraw.Draw(annotated, "RGBA")
    shortest_side = min(annotated.size)
    line_width = max(3, shortest_side // 200)
    font = _load_font(max(14, shortest_side // 40))
    box_color = (225, 29, 72, 255)
    label_bg = (225, 29, 72, 220)
    label_fg = (255, 255, 255, 255)

    for obj in objects:
        box = obj["box"]
        xmin, ymin, xmax, ymax = box["xmin"], box["ymin"], box["xmax"], box["ymax"]
        draw.rectangle([xmin, ymin, xmax, ymax], outline=box_color, width=line_width)

        caption = f"{obj['label']} {obj['confidence']:.0%}"
        text_bbox = draw.textbbox((xmin, ymin), caption, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        padding = max(4, line_width)
        label_top = max(0, ymin - text_height - padding * 2)
        label_box = [
            xmin,
            label_top,
            xmin + text_width + padding * 2,
            label_top + text_height + padding * 2,
        ]
        draw.rectangle(label_box, fill=label_bg)
        draw.text((xmin + padding, label_top + padding), caption, fill=label_fg, font=font)

    buffer = io.BytesIO()
    annotated.save(buffer, format="PNG")
    return buffer.getvalue()
