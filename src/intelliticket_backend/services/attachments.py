from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from intelliticket_backend.errors import AppError

_CHUNK_SIZE = 1024 * 1024
_ALLOWED_TYPES = {
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".log": "text/plain",
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".txt": "text/plain",
}


@dataclass(frozen=True)
class StoredAttachment:
    original_name: str
    storage_key: str
    content_type: str
    size_bytes: int
    sha256: str


class LocalAttachmentStorage:
    """Local attachment store with server-generated, non-user-controlled paths."""

    def __init__(self, root: Path, max_bytes: int) -> None:
        self.root = root.resolve()
        self.max_bytes = max_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def store(
        self,
        filename: str | None,
        content_type: str | None,
        stream: BinaryIO,
    ) -> StoredAttachment:
        original_name, suffix, normalized_type = self._validate_metadata(filename, content_type)
        storage_key = f"{uuid4().hex}{suffix}"
        temporary = self.root / f".{storage_key}.uploading"
        target = self.root / storage_key
        digest = hashlib.sha256()
        prefix = bytearray()
        size = 0
        try:
            with temporary.open("xb") as output:
                while chunk := stream.read(_CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise AppError(
                            "ATTACHMENT_TOO_LARGE",
                            "附件超过允许的大小",
                            413,
                            {"max_bytes": self.max_bytes},
                        )
                    if len(prefix) < 16:
                        prefix.extend(chunk[: 16 - len(prefix)])
                    digest.update(chunk)
                    output.write(chunk)
            if size == 0:
                raise AppError("ATTACHMENT_EMPTY", "附件内容不能为空", 400, {})
            self._validate_signature(suffix, bytes(prefix))
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return StoredAttachment(
            original_name=original_name,
            storage_key=storage_key,
            content_type=normalized_type,
            size_bytes=size,
            sha256=digest.hexdigest(),
        )

    def path_for(self, storage_key: str) -> Path:
        if Path(storage_key).name != storage_key or "/" in storage_key or "\\" in storage_key:
            raise AppError("ATTACHMENT_STORAGE_INVALID", "附件存储标识无效", 500, {})
        path = (self.root / storage_key).resolve()
        if path.parent != self.root or not path.is_file():
            raise AppError("ATTACHMENT_FILE_MISSING", "附件文件不存在", 404, {})
        return path

    def delete(self, storage_key: str) -> None:
        if (
            Path(storage_key).name == storage_key
            and "/" not in storage_key
            and "\\" not in storage_key
        ):
            (self.root / storage_key).unlink(missing_ok=True)

    @staticmethod
    def _validate_metadata(filename: str | None, content_type: str | None) -> tuple[str, str, str]:
        name = (filename or "").strip()
        if not name or len(name) > 255 or "/" in name or "\\" in name or name in {".", ".."}:
            raise AppError("ATTACHMENT_NAME_INVALID", "附件文件名无效", 400, {})
        suffix = Path(name).suffix.lower()
        expected_type = _ALLOWED_TYPES.get(suffix)
        if expected_type is None:
            raise AppError(
                "ATTACHMENT_TYPE_NOT_ALLOWED",
                "不支持该附件类型",
                415,
                {"allowed_extensions": sorted(_ALLOWED_TYPES)},
            )
        normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
        if normalized_type != expected_type:
            raise AppError(
                "ATTACHMENT_CONTENT_TYPE_MISMATCH",
                "附件扩展名与内容类型不匹配",
                415,
                {"expected": expected_type},
            )
        return name, suffix, normalized_type

    @staticmethod
    def _validate_signature(suffix: str, prefix: bytes) -> None:
        valid = True
        if suffix == ".pdf":
            valid = prefix.startswith(b"%PDF-")
        elif suffix == ".png":
            valid = prefix.startswith(b"\x89PNG\r\n\x1a\n")
        elif suffix in {".jpg", ".jpeg"}:
            valid = prefix.startswith(b"\xff\xd8\xff")
        elif suffix in {".txt", ".log"}:
            valid = b"\x00" not in prefix
        if not valid:
            raise AppError(
                "ATTACHMENT_SIGNATURE_INVALID",
                "附件内容与声明的文件类型不匹配",
                415,
                {},
            )
