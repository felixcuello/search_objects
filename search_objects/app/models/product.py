from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.mixins import TimestampMixin, UuidMixin


class Product(UuidMixin, TimestampMixin, db.Model):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    add_prompt: Mapped[str | None] = mapped_column(Text)
    replace_prompt: Mapped[str | None] = mapped_column(Text)
    provider_id: Mapped[int | None] = mapped_column(
        ForeignKey("providers.id", ondelete="RESTRICT", name="fk_products_provider_id")
    )

    provider = relationship("Provider", back_populates="products")

    images = relationship("Image", back_populates="product", passive_deletes=True)
