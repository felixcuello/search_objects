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

    @app.cli.command("import-bercomat")
    def import_bercomat() -> None:
        """Import the curated Bercomat catalog products and their photos (idempotent)."""
        from app.services.bercomat import import_bercomat_products

        summary = import_bercomat_products()
        print(f"imported {summary['products']} products and {summary['images']} new photos")
        if summary["missing_skus"]:
            print(f"SKUs not found in the catalog: {', '.join(summary['missing_skus'])}")
        if summary["failed_images"]:
            print(f"photos that failed to download: {', '.join(summary['failed_images'])}")
        if summary["missing_skus"] or summary["failed_images"]:
            raise SystemExit(1)
