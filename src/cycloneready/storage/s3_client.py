"""S3-compatible object storage client for CycloneReady."""

import os

import boto3
from botocore.config import Config


def create_s3_client():
    """Create an S3 client using local environment credentials."""

    endpoint_url = os.getenv("S3_ENDPOINT_URL")
    access_key = os.getenv("S3_ACCESS_KEY_ID")
    secret_key = os.getenv("S3_SECRET_ACCESS_KEY")
    region = os.getenv("S3_REGION", "us-east-1")

    required = {
        "S3_ENDPOINT_URL": endpoint_url,
        "S3_ACCESS_KEY_ID": access_key,
        "S3_SECRET_ACCESS_KEY": secret_key,
    }

    missing = [name for name, value in required.items() if not value]

    if missing:
        raise ValueError(f"Missing storage environment variables: {', '.join(missing)}")

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )
