from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload, selectinload

from app.extensions import db
from app.models import Product
from app.services.storage import public_url

MAX_RESULTS = 50


def search_products(query: str) -> list[Product]:
    """Find products whose name or description contains the query, ignoring case and accents.

    Photos and provider are loaded together with the products to avoid one query per product.
    The match is a substring scan (no index), which is fine for a small catalog.
    """
    if not query:
        return []
    statement = (
        select(Product)
        .options(joinedload(Product.provider), selectinload(Product.images))
        .where(
            or_(
                Product.name.icontains(query, autoescape=True),
                Product.description.icontains(query, autoescape=True),
            )
        )
        .order_by(Product.id)
        .limit(MAX_RESULTS)
    )
    return list(db.session.scalars(statement))


def product_to_dict(product: Product) -> dict:
    # JSON shape returned to the browser; photos are public URLs in the order they were imported.
    photos = sorted(product.images, key=lambda image: image.id)
    return {
        "uuid": product.uuid,
        "name": product.name,
        "description": product.description,
        "provider": product.provider.name if product.provider else None,
        "images": [public_url(photo.uri) for photo in photos],
    }
