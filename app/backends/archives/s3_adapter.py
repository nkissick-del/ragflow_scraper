"""S3-compatible archive backend (works with AWS S3, Garage, MinIO).

Uploads PDFs with metadata to an S3-compatible object store.
Verification is immediate (S3 uploads are synchronous).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from app.backends.archives.base import ArchiveBackend, ArchiveResult
from app.utils import get_logger


class S3ArchiveBackend(ArchiveBackend):
    """Archive backend using S3-compatible object storage."""

    def __init__(
        self,
        endpoint_url: str = "",
        access_key: str = "",
        secret_key: str = "",
        bucket: str = "",
        region: str = "us-east-1",
    ):
        self._endpoint_url = endpoint_url.rstrip("/") if endpoint_url else ""
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._client = None
        self.logger = get_logger("backends.archive.s3")

    @property
    def name(self) -> str:
        return "s3"

    def is_configured(self) -> bool:
        return bool(
            self._endpoint_url
            and self._access_key
            and self._secret_key
            and self._bucket
        )

    def is_available(self) -> bool:
        if not self.is_configured():
            return False
        try:
            client = self._get_client()
            client.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False

    def _get_client(self):
        """Get or create the boto3 S3 client (lazy init)."""
        if self._client is None:
            import boto3

            self._client = boto3.client(
                "s3",
                endpoint_url=self._endpoint_url,
                aws_access_key_id=self._access_key,
                aws_secret_access_key=self._secret_key,
                region_name=self._region,
            )
        return self._client

    def _build_key(
        self, source: str, filename: str, created: str | None = None
    ) -> str:
        """Build S3 object key: {source}/{YYYYMM}/{filename}."""
        if created:
            try:
                dt = datetime.fromisoformat(created)
                month_prefix = dt.strftime("%Y%m")
            except (ValueError, TypeError):
                month_prefix = datetime.now(timezone.utc).strftime("%Y%m")
        else:
            month_prefix = datetime.now(timezone.utc).strftime("%Y%m")
        return f"{source}/{month_prefix}/{filename}"

    def archive_document(
        self,
        file_path: Path,
        title: str,
        created: Optional[str] = None,
        correspondent: Optional[str] = None,
        document_type: Optional[str] = None,
        tags: list[str] | None = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> ArchiveResult:
        if not self.is_configured():
            return ArchiveResult(
                success=False,
                error="S3 backend not configured",
                archive_name=self.name,
            )

        try:
            client = self._get_client()
            source = (metadata or {}).get("scraper_name", "default")
            filename = file_path.name
            key = self._build_key(source, filename, created)

            # Build S3 metadata (values must be strings, max 2KB total)
            s3_meta: dict[str, str] = {"title": title[:256]}
            if correspondent:
                s3_meta["correspondent"] = correspondent[:256]
            if document_type:
                s3_meta["document_type"] = document_type[:256]
            if tags:
                s3_meta["tags"] = ",".join(tags)[:512]

            client.upload_file(
                str(file_path),
                self._bucket,
                key,
                ExtraArgs={
                    "Metadata": s3_meta,
                    "ContentType": "application/pdf",
                },
            )

            self.logger.info(f"Uploaded to S3: {key}")
            return ArchiveResult(
                success=True,
                document_id=key,
                archive_name=self.name,
            )
        except Exception as e:
            error_msg = f"S3 upload failed: {e}"
            self.logger.error(error_msg)
            return ArchiveResult(
                success=False,
                error=error_msg,
                archive_name=self.name,
            )

    def verify_document(self, document_id: str, timeout: int = 60) -> bool:
        """Verify document exists in S3 (synchronous — always immediate)."""
        try:
            client = self._get_client()
            client.head_object(Bucket=self._bucket, Key=document_id)
            return True
        except Exception as e:
            self.logger.warning(f"S3 verify failed for {document_id}: {e}")
            return False

    def delete_by_tag(self, tag: str) -> int:
        """Delete objects by metadata tag prefix (best-effort).

        S3 doesn't support metadata-based listing natively,
        so this lists all objects and checks metadata individually.
        """
        if not self.is_configured():
            return 0
        try:
            client = self._get_client()
            paginator = client.get_paginator("list_objects_v2")
            deleted = 0
            for page in paginator.paginate(Bucket=self._bucket):
                for obj in page.get("Contents", []):
                    try:
                        head = client.head_object(
                            Bucket=self._bucket, Key=obj["Key"]
                        )
                        obj_tags = head.get("Metadata", {}).get("tags", "")
                        if tag in obj_tags.split(","):
                            client.delete_object(
                                Bucket=self._bucket, Key=obj["Key"]
                            )
                            deleted += 1
                    except Exception:  # noqa: S112 — best-effort per-object deletion
                        continue
            return deleted
        except Exception as e:
            self.logger.warning(f"S3 delete_by_tag failed: {e}")
            return 0
