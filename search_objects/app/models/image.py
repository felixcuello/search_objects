from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.mixins import TimestampMixin, UuidMixin


class Image(UuidMixin, TimestampMixin, db.Model):
    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    # Object key in the S3 bucket (not a URL); see app.services.storage.public_url.
    uri: Mapped[str] = mapped_column(String(512), nullable=False)

    product = relationship("Product", back_populates="images")
