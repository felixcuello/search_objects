from app.extensions import db
from app.models import Product, Provider

PROVIDER_NAME = "Bercomat"
PRODUCTS_PER_CATEGORY = 2


def seed_products() -> int:
    """Create PRODUCTS_PER_CATEGORY products per detector category and return how many were created.

    The description is the Spanish category label and the name is "<label> <n>".
    Every product belongs to the PROVIDER_NAME provider, which is created if missing.
    Existing names are skipped (but get the provider if they have none), so it is safe to re-run.
    """
    from app.services.detector import FURNITURE_LABELS

    provider = Provider.query.filter_by(name=PROVIDER_NAME).first()
    if provider is None:
        provider = Provider(name=PROVIDER_NAME)
        db.session.add(provider)
        db.session.flush()

    created = 0
    for label in FURNITURE_LABELS.values():
        for number in range(1, PRODUCTS_PER_CATEGORY + 1):
            name = f"{label} {number}"
            product = Product.query.filter_by(name=name).first()
            if product is None:
                db.session.add(Product(name=name, description=label, provider=provider))
                created += 1
            elif product.provider_id is None:
                product.provider = provider
    db.session.commit()
    return created
