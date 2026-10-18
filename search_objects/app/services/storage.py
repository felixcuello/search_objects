import os
from functools import lru_cache

import boto3
from botocore.config import Config as BotoConfig


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
        config=BotoConfig(s3={"addressing_style": "path"}),
    )


def upload_image(key: str, data: bytes, content_type: str) -> str:
    """Write an image to the bucket and return its public URL."""
    _client().put_object(
        Bucket=os.environ["S3_BUCKET"],
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return public_url(key)


def download_image(key: str) -> bytes:
    """Read an image from the bucket and return its bytes."""
    return _client().get_object(Bucket=os.environ["S3_BUCKET"], Key=key)["Body"].read()


def delete_image(key: str) -> None:
    _client().delete_object(Bucket=os.environ["S3_BUCKET"], Key=key)


def public_url(key: str) -> str:
    """URL the browser can use; the bucket allows anonymous reads."""
    return f"{os.environ['S3_PUBLIC_URL'].rstrip('/')}/{key}"
