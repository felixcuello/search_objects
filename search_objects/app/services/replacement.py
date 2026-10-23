import base64
import io
import mimetypes
from functools import lru_cache

from flask import current_app
from openai import OpenAI, OpenAIError
from PIL import Image

from app.models import Product
from app.services.detector import FURNITURE_LABELS, load_image
from app.services.storage import download_image

GENERAL_PROMPT = """
Image 1: photograph of a space, uploaded by a customer.
Image 2: product photograph from a store catalog. This is the product that has to replace an
object in Image 1.

Task:
Replace the {target} in Image 1 with the product in Image 2.
The {target} to replace is located {position}.
Replace only that object. Leave every other object untouched, even if it looks similar.

Keep from Image 1:
- camera angle, vanishing points, and perspective
- floor plane, walls, windows, and existing furniture
- lighting, color temperature, and shadows
- framing and composition

From Image 2:
- keep the same product design: shape, materials, color, and proportions
- re-render it from Image 1's camera so it sits correctly
- scale the product to a realistic size for this space

Integration:
- the product must rest or be mounted correctly for that kind of product
- add photorealistic contact shadows matching the room light
- do not paste the product as a flat cutout
- do not redesign the room or invent a different product
{product_notes}
Photorealistic photograph. Change only the insertion of the product.
"""

# Detector labels are English prompts, but the page sends the Spanish label back.
# Several prompts can share one Spanish label ("floor" and "wooden floor" are both "piso"), so the
# first one listed must be the most generic: it is the noun used in the replace prompt.
_ENGLISH_BY_SPANISH_LABEL: dict[str, str] = {}
for _english, _spanish in FURNITURE_LABELS.items():
    _ENGLISH_BY_SPANISH_LABEL.setdefault(_spanish, _english)


class ReplacementError(RuntimeError):
    """A failure with a message that is safe to show to the user."""


@lru_cache(maxsize=1)
def _openai_client() -> OpenAI:
    # Created on first use so the app can start (and search) without an OpenAI key.
    return OpenAI()


def describe_position(box: dict, image_width: int, image_height: int) -> str:
    """Describe where a detector box sits in the image, in words and in percentages.

    Percentages are measured from the top-left corner, so the model can narrow down the object.
    """
    left = round(100 * box["xmin"] / image_width)
    right = round(100 * box["xmax"] / image_width)
    top = round(100 * box["ymin"] / image_height)
    bottom = round(100 * box["ymax"] / image_height)
    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    horizontal = "left" if center_x < 33 else "right" if center_x > 67 else "center"
    vertical = "upper" if center_y < 33 else "lower" if center_y > 67 else "middle"
    region = "center" if (vertical, horizontal) == ("middle", "center") else f"{vertical} {horizontal}"
    return (
        f"in the {region} part of the image, inside the area that spans from {left}% to {right}% "
        f"of the image width and from {top}% to {bottom}% of the image height"
    )


def build_replace_prompt(target: str, position: str, product_notes: str | None) -> str:
    # The general prompt plus the notes written for this specific product, when it has any.
    notes = f"\nInstructions specific to this product:\n{product_notes.strip()}\n" if product_notes else ""
    return GENERAL_PROMPT.format(target=target, position=position, product_notes=notes)


def _image_file_for_upload(data: bytes) -> tuple[str, bytes, str]:
    # The input can be the uploaded JPEG or a PNG result of an earlier replacement.
    with Image.open(io.BytesIO(data)) as image:
        content_type = Image.MIME.get(image.format, "image/jpeg")
    extension = mimetypes.guess_extension(content_type) or ".jpg"
    return (f"image{extension}", data, content_type)


def replace_object_in_image(
    original_bytes: bytes,
    product: Product,
    label: str,
    box: dict,
    box_image_size: tuple[int, int] | None = None,
) -> bytes:
    """Replace the detected object with the product's first photo and return the PNG bytes.

    The box is in pixels of an image of box_image_size (the photo the detector saw). When the
    input is an earlier result, that size differs from the input, so the position is computed
    from box_image_size. It defaults to the size of the input image.
    Raises ReplacementError when the product has no photo or the image model fails.
    """
    photos = sorted(product.images, key=lambda image: image.id)
    if not photos:
        raise ReplacementError("Este producto no tiene fotos para reemplazar el objeto.")
    photo_key = photos[0].uri
    photo_type = mimetypes.guess_type(photo_key)[0] or "image/jpeg"

    original = load_image(original_bytes)
    prompt = build_replace_prompt(
        target=_ENGLISH_BY_SPANISH_LABEL.get(label, label),
        position=describe_position(box, *(box_image_size or original.size)),
        product_notes=product.replace_prompt,
    )
    try:
        response = _openai_client().images.edit(
            model=current_app.config["OPENAI_IMAGE_MODEL"],
            image=[
                _image_file_for_upload(original_bytes),
                (photo_key.rsplit("/", 1)[-1], download_image(photo_key), photo_type),
            ],
            prompt=prompt,
            n=1,
            size="auto",
            quality="high",
            output_format="png",
        )
    except OpenAIError as error:
        current_app.logger.exception("OpenAI image edit failed")
        raise ReplacementError("No pudimos generar la imagen. Intente nuevamente.") from error

    encoded = response.data[0].b64_json
    if not encoded:
        raise ReplacementError("No pudimos generar la imagen. Intente nuevamente.")
    return base64.b64decode(encoded)
