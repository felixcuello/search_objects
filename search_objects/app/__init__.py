import importlib

from flask import Flask, render_template
from sqlalchemy import text

from app.config import Config
from app.extensions import db, migrate
from app.routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    migrate.init_app(app, db)
    importlib.import_module("app.models")
    app.register_blueprint(bp)
    _register_cli(app)

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


def _register_cli(app: Flask) -> None:
    """Register Flask CLI commands that must run inside an app context."""

    @app.cli.command("db-ping")
    def db_ping() -> None:
        """Confirm the app must reach MySQL with SELECT 1."""
        db.session.execute(text("SELECT 1"))
        print("database ok")

    @app.cli.command("seed")
    def seed() -> None:
        """Create sample products for every detector category (idempotent)."""
        from app.seeds import seed_products

        print(f"created {seed_products()} products")
