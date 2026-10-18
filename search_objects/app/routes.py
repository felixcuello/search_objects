from flask import Blueprint, Response, current_app, jsonify, render_template, request
from sqlalchemy.orm import selectinload

from app.models import Product
from app.services.catalog import product_to_dict, search_products
from app.services.detector import InvalidImageError, clamp_threshold, detect_objects, load_image
from app.services.overlay import (
    assign_display_names,
    attach_search_urls,
    encode_jpeg_data_uri,
    overlay_objects,
)
from app.services.replacement import ReplacementError, replace_object_in_image

bp = Blueprint("main", __name__)


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


@bp.get("/")
def index():
    return _render()


@bp.post("/detect")
def detect():
    threshold = clamp_threshold(request.form.get("threshold", type=float))
    uploaded = request.files.get("image")
    if uploaded is None or not uploaded.filename:
        return _render(
            error="Debe seleccionar una imagen para continuar.",
            threshold=threshold,
            status=400,
        )

    try:
        image = load_image(uploaded.read())
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
    if uploaded is None or product is None or not label or None in box.values():
        return jsonify({"error": "Faltan datos para reemplazar el objeto."}), 400

    try:
        png = replace_object_in_image(uploaded.read(), product, label, box)
    except InvalidImageError:
        return jsonify({"error": "La imagen no es válida o está dañada."}), 400
    except ReplacementError as error:
        return jsonify({"error": str(error)}), 502
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

