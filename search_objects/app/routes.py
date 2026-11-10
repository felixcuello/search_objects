import mimetypes
import re

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request
from sqlalchemy.orm import selectinload

from app.models import Product
from app.services.analytics import (
    InvalidTimeframeError,
    build_snapshot,
    record_photo_submission,
    record_replacement,
    resolve_window,
)
from app.services.catalog import product_to_dict, search_products
from app.services.detector import InvalidImageError, clamp_threshold, detect_objects, load_image
from app.services.overlay import (
    assign_display_names,
    attach_search_urls,
    encode_jpeg_data_uri,
    overlay_objects,
)
from app.services.replacement import ReplacementError, replace_object_in_image
from app.services.samples import read_sample
from app.services.storage import download_image

bp = Blueprint("main", __name__)

# Bucket keys are "<provider>/<sku>/<file>". Only plain segments are served, never "." or "..".
MEDIA_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-][A-Za-z0-9._-]*(/[A-Za-z0-9_-][A-Za-z0-9._-]*)+")
MEDIA_CACHE_SECONDS = 3600


def _render(
    *,
    error=None,
    threshold=None,
    objects=None,
    overlays=None,
    image_src=None,
    image_width=None,
    image_height=None,
    status=200,
):
    if threshold is None:
        threshold = current_app.config["DEFAULT_THRESHOLD"]
    return (
        render_template(
            "detect.html",
            error=error,
            threshold=threshold,
            objects=objects,
            overlays=overlays or [],
            image_src=image_src,
            image_width=image_width,
            image_height=image_height,
        ),
        status,
    )


def _requested_image_bytes() -> bytes | None:
    """Return the bytes of the sample chosen in the form, or of the uploaded file.

    A sample id wins over a file. Returns None when there is no usable image.
    """
    sample_id = request.form.get("sample")
    if sample_id:
        return read_sample(sample_id)
    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename:
        return None
    return uploaded.read()


@bp.get("/")
def index():
    return _render()


@bp.post("/detect")
def detect():
    threshold = clamp_threshold(request.form.get("threshold", type=float))
    image_bytes = _requested_image_bytes()
    if image_bytes is None:
        return _render(
            error="Debe seleccionar una imagen para continuar.",
            threshold=threshold,
            status=400,
        )

    try:
        image = load_image(image_bytes)
    except InvalidImageError:
        return _render(
            error="La imagen no es válida o está dañada.",
            threshold=threshold,
            status=400,
        )

    image_width, image_height = image.size
    objects = detect_objects(image, threshold=threshold)
    for index, obj in enumerate(objects):
        # Ids must be assigned before overlay stacking so list and boxes stay paired.
        obj["id"] = f"obj-{index}"
    record_photo_submission(
        [obj["label"] for obj in objects], sample_id=request.form.get("sample") or None
    )
    assign_display_names(objects)
    attach_search_urls(objects)
    overlays = overlay_objects(objects, image_width, image_height)
    return _render(
        threshold=threshold,
        objects=objects,
        overlays=overlays,
        image_src=encode_jpeg_data_uri(image),
        image_width=image_width,
        image_height=image_height,
    )


@bp.post("/replace")
def replace():
    """Replace a detected object of the uploaded image with a catalog product.

    Returns the new image as PNG, or a JSON error with a message for the user.
    """
    uploaded = request.files.get("image")
    product = (
        Product.query.options(selectinload(Product.images))
        .filter_by(uuid=request.form.get("product_uuid", ""))
        .first()
    )
    box = {key: request.form.get(key, type=int) for key in ("xmin", "ymin", "xmax", "ymax")}
    label = (request.form.get("label") or "").strip()
    # Size of the photo the box belongs to; it differs from the sent image when replacing again.
    box_width = request.form.get("image_width", type=int)
    box_height = request.form.get("image_height", type=int)
    box_image_size = (box_width, box_height) if box_width and box_height else None
    if uploaded is None or product is None or not label or None in box.values():
        return jsonify({"error": "Faltan datos para reemplazar el objeto."}), 400

    try:
        png = replace_object_in_image(uploaded.read(), product, label, box, box_image_size)
    except InvalidImageError:
        return jsonify({"error": "La imagen no es válida o está dañada."}), 400
    except ReplacementError as error:
        return jsonify({"error": str(error)}), 502
    record_replacement(label, product)
    return Response(png, mimetype="image/png")


@bp.get("/object_search")
def object_search():
    """Return the catalog products that match the label of a selected detection.

    The box is echoed back for the later replace step; the search only uses the label.
    """
    query = (request.args.get("q") or "").strip()
    box = {
        "xmin": request.args.get("xmin", type=int),
        "ymin": request.args.get("ymin", type=int),
        "xmax": request.args.get("xmax", type=int),
        "ymax": request.args.get("ymax", type=int),
    }
    results = [product_to_dict(product) for product in search_products(query)]
    return jsonify({"query": query, "box": box, "results": results})


@bp.get("/analytics")
def analytics():
    """Live usage dashboard; the page polls /analytics/data for its numbers."""
    return render_template("analytics.html")


@bp.get("/analytics/data")
def analytics_data():
    """Return the analytics numbers of a timeframe as JSON; never cached so the page stays live.

    The timeframe is a preset (?range=1d) or a custom window (?from=...&to=..., ISO 8601).
    """
    try:
        window = resolve_window(
            request.args.get("range"), request.args.get("from"), request.args.get("to")
        )
    except InvalidTimeframeError as error:
        return jsonify({"error": str(error)}), 400
    response = jsonify(build_snapshot(*window))
    response.headers["Cache-Control"] = "no-store"
    return response

@bp.get("/media/<path:key>")
def media(key):
    """Serve a product photo from the bucket, so browsers never need to reach the bucket itself.

    Only keys made of plain path segments that point to an image type are served.
    """
    content_type = mimetypes.guess_type(key)[0] or ""
    if not MEDIA_KEY_PATTERN.fullmatch(key) or not content_type.startswith("image/"):
        abort(404)
    try:
        data = download_image(key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
            abort(404)
        current_app.logger.exception("Bucket read failed for %s", key)
        abort(502)
    except BotoCoreError:
        current_app.logger.exception("Bucket unreachable for %s", key)
        abort(502)
    response = Response(data, mimetype=content_type)
    response.headers["Cache-Control"] = f"public, max-age={MEDIA_CACHE_SECONDS}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
