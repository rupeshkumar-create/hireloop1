"""Shared upload validation for candidate and recruiter resume surfaces."""

from __future__ import annotations

import io
import zipfile

MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
MAX_DOCX_ENTRIES = 2_000
ALLOWED_RESUME_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
    }
)


def resume_magic_ok(file_bytes: bytes) -> bool:
    """Accept real PDF, OOXML ZIP, or legacy OLE document signatures."""
    return file_bytes[:4] in (b"%PDF", b"PK\x03\x04", b"\xd0\xcf\x11\xe0")


def docx_archive_ok(file_bytes: bytes) -> bool:
    """Reject malformed OOXML, traversal entries, and compressed ZIP bombs."""
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_DOCX_ENTRIES:
                return False
            names = {entry.filename.replace("\\", "/") for entry in entries}
            if "word/document.xml" not in names:
                return False
            total_size = 0
            for entry in entries:
                normalized = entry.filename.replace("\\", "/")
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    return False
                if entry.flag_bits & 0x1:  # encrypted archives are not parseable safely
                    return False
                total_size += entry.file_size
                if total_size > MAX_DOCX_UNCOMPRESSED_BYTES:
                    return False
    except (OSError, ValueError, zipfile.BadZipFile):
        return False
    return True


def validate_resume_upload(content_type: str | None, file_bytes: bytes) -> str | None:
    """Return a user-safe validation error, or None when the upload is acceptable."""
    if content_type not in ALLOWED_RESUME_MIME_TYPES:
        return "Upload a PDF or DOCX resume."
    if len(file_bytes) > MAX_RESUME_BYTES:
        return "Resume must be under 10MB."
    if not resume_magic_ok(file_bytes):
        return "File content does not match a PDF or Word document."
    expected_magic = {
        "application/pdf": b"%PDF",
        "application/msword": b"\xd0\xcf\x11\xe0",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": b"PK\x03\x04",
    }.get(content_type or "")
    if expected_magic and file_bytes[:4] != expected_magic:
        return "File content does not match its declared PDF or Word type."
    if file_bytes[:4] == b"PK\x03\x04" and not docx_archive_ok(file_bytes):
        return "DOCX file is malformed or expands beyond the safe processing limit."
    return None
