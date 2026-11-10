# Models must import db from app.extensions so Alembic can collect metadata.
from app.models.analytics import DetectedObject, ObjectReplacement, PhotoSubmission
from app.models.image import Image
from app.models.product import Product
from app.models.provider import Provider

__all__ = [
    "DetectedObject",
    "Image",
    "ObjectReplacement",
    "PhotoSubmission",
    "Product",
    "Provider",
]
