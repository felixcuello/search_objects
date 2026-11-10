from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.extensions import db

SOURCE_UPLOAD = "upload"
SOURCE_SAMPLE = "sample"


class PhotoSubmission(db.Model):
    """One photo sent to /detect, either uploaded by the visitor or chosen from the samples."""

    __tablename__ = "photo_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    # Only set when source is "sample"; says which pre-made photo was chosen.
    sample_id: Mapped[str | None] = mapped_column(String(64))


class DetectedObject(db.Model):
    """An object found by the detector in an uploaded photo (never in a sample photo)."""

    __tablename__ = "detected_objects"
    __table_args__ = (Index("ix_detected_objects_label", "label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_submission_id: Mapped[int] = mapped_column(
        ForeignKey(
            "photo_submissions.id",
            ondelete="CASCADE",
            name="fk_detected_objects_photo_submission_id",
        ),
        nullable=False,
    )
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)


class ObjectReplacement(db.Model):
    """A successful replacement of a detected object by a catalog product."""

    __tablename__ = "object_replacements"
    __table_args__ = (
        Index("ix_object_replacements_label", "label"),
        Index("ix_object_replacements_product_id", "product_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[DateTime] = mapped_column(
        DateTime, nullable=False, server_default=text("CURRENT_TIMESTAMP")
    )
    # Type of the replaced object, for example "mesa".
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    # The product id may go away if the catalog is re-imported, so the name is copied too.
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "products.id", ondelete="SET NULL", name="fk_object_replacements_product_id"
        )
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(255))
