import base64
import io

from PIL import Image


def encode_jpeg_data_uri(image: Image.Image) -> str:
    """Encode the unannotated RGB image as a JPEG data URI.

    The URI must carry the original photo so HTML boxes can sit on top.
    """
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=88)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + encoded


def box_css_percents(box: dict, image_width: int, image_height: int) -> dict[str, float]:
    """Map a detector box in pixels to CSS percent positions.

    Values must stay relative to the image so overlays track scaled layout.
    """
    width = max(image_width, 1)
    height = max(image_height, 1)
    return {
        "left": box["xmin"] / width * 100,
        "top": box["ymin"] / height * 100,
        "width": (box["xmax"] - box["xmin"]) / width * 100,
        "height": (box["ymax"] - box["ymin"]) / height * 100,
    }


def assign_display_names(objects: list[dict]) -> None:
    """Set display_name so duplicate labels must be numbered in the UI.

    The original label must stay unchanged for search query values.
    """
    counts: dict[str, int] = {}
    for obj in objects:
        counts[obj["label"]] = counts.get(obj["label"], 0) + 1
    seen: dict[str, int] = {}
    for obj in objects:
        label = obj["label"]
        if counts[label] == 1:
            obj["display_name"] = label
            continue
        seen[label] = seen.get(label, 0) + 1
        obj["display_name"] = f"{label} {seen[label]}"


def overlay_objects(objects: list[dict], image_width: int, image_height: int) -> list[dict]:
    """Attach CSS percents and stack smaller boxes above larger ones.

    Smaller detections must sit on top so nested objects stay clickable.
    """
    overlays = []
    for obj in objects:
        box = obj["box"]
        area = max(0, box["xmax"] - box["xmin"]) * max(0, box["ymax"] - box["ymin"])
        overlays.append(
            {
                **obj,
                "css": box_css_percents(box, image_width, image_height),
                "area": area,
            }
        )
    overlays.sort(key=lambda item: item["area"], reverse=True)
    for index, obj in enumerate(overlays, start=1):
        obj["z_index"] = index
    return overlays
