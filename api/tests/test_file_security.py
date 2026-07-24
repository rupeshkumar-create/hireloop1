import io
import zipfile

from hireloop_api.services.file_security import MAX_RESUME_BYTES, validate_resume_upload


def _docx_bytes(*, name: str = "word/document.xml", content: bytes = b"<document />") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(name, content)
    return output.getvalue()


def test_accepts_supported_resume_signatures() -> None:
    assert validate_resume_upload("application/pdf", b"%PDF-1.7\n") is None
    assert (
        validate_resume_upload(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _docx_bytes(),
        )
        is None
    )
    assert validate_resume_upload("application/msword", b"\xd0\xcf\x11\xe0content") is None


def test_rejects_mime_spoofing_and_oversized_files() -> None:
    assert "does not match" in str(validate_resume_upload("application/pdf", b"<script>"))
    assert "PDF or DOCX" in str(validate_resume_upload("text/html", b"%PDF-1.7"))
    assert "under 10MB" in str(
        validate_resume_upload("application/pdf", b"%PDF" + b"x" * MAX_RESUME_BYTES)
    )


def test_rejects_malformed_and_traversing_docx_archives() -> None:
    assert "malformed" in str(
        validate_resume_upload(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            b"PK\x03\x04not-a-zip",
        )
    )
    assert "malformed" in str(
        validate_resume_upload(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _docx_bytes(name="../word/document.xml"),
        )
    )
