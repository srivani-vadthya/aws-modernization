"""Optional S3 staging for source retained by an engagement."""

from __future__ import annotations

import os
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path


SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "target"}


def configured() -> bool:
    return bool(os.getenv("AWS_S3_INTAKE_BUCKET"))


def _archive(source: Path) -> bytes:
    """Build an in-memory, portable source archive without dependency caches."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in source.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts) or not path.is_file():
                continue
            zf.write(path, path.relative_to(source).as_posix())
    return buf.getvalue()


def stage_source(engagement_id: str, source: Path) -> dict:
    """Upload a sanitized source archive using the standard AWS credential chain.

    A named AWS profile is optional; without it boto3 uses the normal SDK chain
    (environment, shared credentials/configuration, or an attached IAM role).
    """
    bucket = os.getenv("AWS_S3_INTAKE_BUCKET")
    if not bucket:
        raise RuntimeError("AWS_S3_INTAKE_BUCKET is not configured")
    if not source.exists():
        raise RuntimeError("Engagement source directory is missing")
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("boto3 is required for S3 intake; install API requirements") from exc

    profile = os.getenv("AWS_PROFILE") or None
    region = os.getenv("AWS_REGION", "us-east-1")
    session = boto3.Session(profile_name=profile, region_name=region)
    client = session.client("s3", endpoint_url=os.getenv("AWS_S3_ENDPOINT_URL") or None)
    prefix = os.getenv("AWS_S3_INTAKE_PREFIX", "nexus-modernize/intake").strip("/")
    key = f"{prefix}/{engagement_id}/source.zip"
    args = {
        "Bucket": bucket,
        "Key": key,
        "Body": _archive(source),
        "ContentType": "application/zip",
        "ServerSideEncryption": os.getenv("AWS_S3_SSE", "AES256"),
    }
    kms_key = os.getenv("AWS_S3_KMS_KEY_ID")
    if args["ServerSideEncryption"] == "aws:kms" and kms_key:
        args["SSEKMSKeyId"] = kms_key
    client.put_object(**args)
    return {
        "bucket": bucket,
        "key": key,
        "uri": f"s3://{bucket}/{key}",
        "region": region,
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "encryption": args["ServerSideEncryption"],
    }
