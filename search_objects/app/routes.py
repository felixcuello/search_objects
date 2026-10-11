import base64

from flask import Blueprint, current_app, render_template, request

from app.services.detector import InvalidImageError, clamp_threshold, detect_objects, load_image
from app.services.overlay import annotate_image

bp = Blueprint("main", __name__)


def _render(*, error=None, threshold=None, objects=None, overlay_src=None, status=200):
    if threshold is None:
        threshold = current_app.config["DEFAULT_THRESHOLD"]
    return (
        render_template(
            "detect.html",
            error=error,
            threshold=threshold,
            objects=objects,
            overlay_src=overlay_src,
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

    objects = detect_objects(image, threshold=threshold)
    overlay_png = annotate_image(image, objects)
    overlay_src = "data:image/png;base64," + base64.b64encode(overlay_png).decode("ascii")
    return _render(threshold=threshold, objects=objects, overlay_src=overlay_src)
