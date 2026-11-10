from datetime import timedelta

from flask import current_app
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.models import Product
from app.models.analytics import (
    SOURCE_SAMPLE,
    SOURCE_UPLOAD,
    DetectedObject,
    ObjectReplacement,
    PhotoSubmission,
)

# Detected objects are always counted for this provider until more providers are imported.
DETECTION_PROVIDER = "bercomat"
RANKING_SIZE = 10
TIMELINE_MINUTES = 60


def record_photo_submission(labels: list[str], sample_id: str | None = None) -> None:
    """Store one photo submission and, for uploaded photos only, the labels found in it.

    Sample photos always give the same objects, so their labels would only add noise.
    A failure is logged and swallowed because analytics must never break the user flow.
    """
    try:
        source = SOURCE_SAMPLE if sample_id else SOURCE_UPLOAD
        submission = PhotoSubmission(
            provider=DETECTION_PROVIDER, source=source, sample_id=sample_id
        )
        db.session.add(submission)
        if source == SOURCE_UPLOAD:
            db.session.flush()
            db.session.add_all(
                DetectedObject(
                    photo_submission_id=submission.id,
                    label=label,
                    provider=DETECTION_PROVIDER,
                )
                for label in labels
            )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not record the photo submission")


def record_replacement(label: str, product: Product) -> None:
    """Store one successful replacement of an object type by a catalog product.

    A failure is logged and swallowed because analytics must never break the user flow.
    """
    try:
        db.session.add(
            ObjectReplacement(
                label=label,
                product_id=product.id,
                product_name=product.name,
                provider=product.provider.name if product.provider else None,
            )
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Could not record the replacement")


def _ranking(statement) -> list[dict]:
    """Run a grouped (name, total) query and return it as JSON-ready rows."""
    return [{"name": name, "total": total} for name, total in db.session.execute(statement)]


def _top_by(column) -> list[dict]:
    """Return the most frequent values of a column, most frequent first."""
    total = func.count().label("total")
    statement = (
        select(column, total)
        .group_by(column)
        .order_by(total.desc(), column)
        .limit(RANKING_SIZE)
    )
    return _ranking(statement)


def _timeline() -> dict:
    """Count photos and replacements per minute for the last hour, one slot per minute."""
    now = db.session.scalar(select(func.now())).replace(second=0, microsecond=0)
    first_minute = now - timedelta(minutes=TIMELINE_MINUTES - 1)
    minutes = [first_minute + timedelta(minutes=offset) for offset in range(TIMELINE_MINUTES)]

    def per_minute(model) -> dict[str, int]:
        bucket = func.date_format(model.created_at, "%Y-%m-%d %H:%i")
        rows = db.session.execute(
            select(bucket, func.count())
            .where(model.created_at >= first_minute)
            .group_by(bucket)
        )
        return {minute: total for minute, total in rows}

    photos = per_minute(PhotoSubmission)
    replacements = per_minute(ObjectReplacement)
    keys = [minute.strftime("%Y-%m-%d %H:%M") for minute in minutes]
    return {
        # The database runs in UTC, so the browser must read these as UTC.
        "minutes": [minute.isoformat() + "Z" for minute in minutes],
        "photos": [photos.get(key, 0) for key in keys],
        "replacements": [replacements.get(key, 0) for key in keys],
    }


def build_snapshot() -> dict:
    """Return every number the analytics page shows, in one JSON-ready dictionary."""
    by_source = dict(
        db.session.execute(
            select(PhotoSubmission.source, func.count()).group_by(PhotoSubmission.source)
        ).all()
    )
    uploads = by_source.get(SOURCE_UPLOAD, 0)
    samples = by_source.get(SOURCE_SAMPLE, 0)
    return {
        "totals": {
            "photos": uploads + samples,
            "uploads": uploads,
            "samples": samples,
            "detected_objects": db.session.scalar(select(func.count(DetectedObject.id))),
            "replacements": db.session.scalar(select(func.count(ObjectReplacement.id))),
        },
        "top_detected": _top_by(DetectedObject.label),
        "top_replaced": _top_by(ObjectReplacement.label),
        "top_products": _top_by(ObjectReplacement.product_name),
        "timeline": _timeline(),
    }
