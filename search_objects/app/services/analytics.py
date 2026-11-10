import math
from datetime import datetime, timedelta, timezone

from flask import current_app
from sqlalchemy import func, literal_column, select
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
DEFAULT_RANGE = "1h"
# Timeframes offered by the page, in minutes. A month is 30 days.
RANGE_MINUTES = {"15m": 15, "1h": 60, "2h": 120, "1d": 1440, "1w": 10080, "1mo": 43200}
MAX_CUSTOM_RANGE_MINUTES = 400 * 1440
# Bucket sizes in minutes, from one minute to one day; the chart uses the smallest that fits.
BUCKET_MINUTES = (1, 2, 5, 10, 15, 30, 60, 120, 360, 720, 1440)
MAX_TIMELINE_POINTS = 100


class InvalidTimeframeError(ValueError):
    """The requested timeframe is unknown or malformed; the message is safe to show the user."""


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


def _parse_utc(value: str, name: str) -> datetime:
    """Parse an ISO 8601 timestamp into a naive UTC datetime, truncated to the minute."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise InvalidTimeframeError(f"El parámetro '{name}' no es una fecha válida.") from None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed.replace(second=0, microsecond=0)


def _bucket_minutes(span_minutes: int) -> int:
    """Pick the smallest bucket size that keeps the chart within MAX_TIMELINE_POINTS."""
    for bucket in BUCKET_MINUTES:
        if math.ceil(span_minutes / bucket) <= MAX_TIMELINE_POINTS:
            return bucket
    return BUCKET_MINUTES[-1]


def resolve_window(
    range_name: str | None, start_text: str | None, end_text: str | None
) -> tuple[datetime, datetime, int]:
    """Turn the requested timeframe into (start, end, bucket minutes); end is exclusive.

    A preset such as "1d" slides with the clock and includes the current minute.
    A custom window comes from two ISO timestamps. Raises InvalidTimeframeError if it is bad.
    """
    if start_text or end_text:
        if not (start_text and end_text):
            raise InvalidTimeframeError("Indicá el inicio y el fin del rango.")
        start, end = _parse_utc(start_text, "from"), _parse_utc(end_text, "to")
        span = int((end - start).total_seconds() // 60)
        if span <= 0:
            raise InvalidTimeframeError("El inicio debe ser anterior al fin.")
        if span > MAX_CUSTOM_RANGE_MINUTES:
            raise InvalidTimeframeError("El rango máximo es de 400 días.")
        return start, end, _bucket_minutes(span)
    span = RANGE_MINUTES.get(range_name or DEFAULT_RANGE)
    if span is None:
        raise InvalidTimeframeError("El rango no es válido.")
    now = db.session.scalar(select(func.now())).replace(second=0, microsecond=0)
    end = now + timedelta(minutes=1)
    return end - timedelta(minutes=span), end, _bucket_minutes(span)


def _top_by(column, start: datetime, end: datetime, joined_to_submission: bool = False) -> list[dict]:
    """Return the most frequent values of a column inside the window, most frequent first.

    Detected objects have no timestamp of their own, so they are filtered by their photo's.
    """
    total = func.count().label("total")
    created_at = PhotoSubmission.created_at if joined_to_submission else column.class_.created_at
    statement = select(column, total)
    if joined_to_submission:
        statement = statement.join(
            PhotoSubmission, PhotoSubmission.id == column.class_.photo_submission_id
        )
    statement = (
        statement.where(created_at >= start, created_at < end)
        .group_by(column)
        .order_by(total.desc(), column)
        .limit(RANKING_SIZE)
    )
    return [{"name": name, "total": count} for name, count in db.session.execute(statement)]


def _timeline(start: datetime, end: datetime, bucket_minutes: int) -> dict:
    """Count photos and replacements per bucket of the window, one slot per bucket."""
    span = int((end - start).total_seconds() // 60)
    slots = math.ceil(span / bucket_minutes)

    def per_bucket(model) -> list[int]:
        # Both numbers are integers made here, so writing them into the SQL is safe, and it
        # keeps SELECT and GROUP BY identical, which MySQL needs.
        position = func.timestampdiff(literal_column("MINUTE"), start, model.created_at)
        bucket = position.op("DIV")(literal_column(str(bucket_minutes))).label("bucket")
        rows = db.session.execute(
            select(bucket, func.count())
            .where(model.created_at >= start, model.created_at < end)
            .group_by(bucket)
        )
        counts = [0] * slots
        for index, total in rows:
            if 0 <= index < slots:
                counts[index] = total
        return counts

    return {
        # The database runs in UTC, so the browser must read these as UTC.
        "buckets": [
            (start + timedelta(minutes=index * bucket_minutes)).isoformat() + "Z"
            for index in range(slots)
        ],
        "bucket_minutes": bucket_minutes,
        "photos": per_bucket(PhotoSubmission),
        "replacements": per_bucket(ObjectReplacement),
    }


def build_snapshot(start: datetime, end: datetime, bucket_minutes: int) -> dict:
    """Return every number the analytics page shows for the window, as a JSON-ready dictionary."""
    by_source = dict(
        db.session.execute(
            select(PhotoSubmission.source, func.count())
            .where(PhotoSubmission.created_at >= start, PhotoSubmission.created_at < end)
            .group_by(PhotoSubmission.source)
        ).all()
    )
    uploads = by_source.get(SOURCE_UPLOAD, 0)
    samples = by_source.get(SOURCE_SAMPLE, 0)
    detected_objects = db.session.scalar(
        select(func.count(DetectedObject.id))
        .join(PhotoSubmission, PhotoSubmission.id == DetectedObject.photo_submission_id)
        .where(PhotoSubmission.created_at >= start, PhotoSubmission.created_at < end)
    )
    replacements = db.session.scalar(
        select(func.count(ObjectReplacement.id)).where(
            ObjectReplacement.created_at >= start, ObjectReplacement.created_at < end
        )
    )
    return {
        "window": {"start": start.isoformat() + "Z", "end": end.isoformat() + "Z"},
        "totals": {
            "photos": uploads + samples,
            "uploads": uploads,
            "samples": samples,
            "detected_objects": detected_objects,
            "replacements": replacements,
        },
        "top_detected": _top_by(DetectedObject.label, start, end, joined_to_submission=True),
        "top_replaced": _top_by(ObjectReplacement.label, start, end),
        "top_products": _top_by(ObjectReplacement.product_name, start, end),
        "timeline": _timeline(start, end, bucket_minutes),
    }
