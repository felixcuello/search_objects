from flask import Flask, render_template

from app.config import Config
from app.routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    app.register_blueprint(bp)

    @app.errorhandler(413)
    def request_entity_too_large(_error):
        return (
            render_template(
                "detect.html",
                error="La imagen supera el tamaño máximo permitido.",
                threshold=app.config["DEFAULT_THRESHOLD"],
                objects=None,
                overlays=[],
                image_src=None,
                image_width=None,
                image_height=None,
            ),
            413,
        )

    return app
