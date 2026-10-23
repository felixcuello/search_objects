from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db
from app.models.mixins import TimestampMixin


class Provider(TimestampMixin, db.Model):
    __tablename__ = "providers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    products = relationship("Product", back_populates="provider")
