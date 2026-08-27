from pathlib import Path
from zipfile import BadZipFile, ZipFile

from django.conf import settings
from django.core.exceptions import ValidationError


ALLOWED_DOCX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
    "application/msword",
}

REQUIRED_DOCX_MEMBERS = {
    "[Content_Types].xml",
    "word/document.xml",
}

MAX_ARCHIVE_MEMBERS = 10_000


def validate_docx_file(uploaded_file) -> None:
    file_name = getattr(uploaded_file, "name", "")
    extension = Path(file_name).suffix.lower()

    if extension != ".docx":
        raise ValidationError(
            "Only DOCX files are allowed.",
            code="invalid_extension",
        )

    file_size = getattr(uploaded_file, "size", None)
    max_upload_size = settings.DOCUMENT_MAX_UPLOAD_SIZE_BYTES

    if file_size is not None and file_size > max_upload_size:
        max_size_mb = max_upload_size // (1024 * 1024)
        raise ValidationError(
            f"File size must not exceed {max_size_mb} MB.",
            code="file_too_large",
        )

    content_type = getattr(uploaded_file, "content_type", None)

    if (
        content_type
        and content_type not in ALLOWED_DOCX_CONTENT_TYPES
    ):
        raise ValidationError(
            "The uploaded file has an invalid content type.",
            code="invalid_content_type",
        )

    current_position = uploaded_file.tell()

    try:
        uploaded_file.seek(0)

        with ZipFile(uploaded_file) as archive:
            members = archive.infolist()

            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise ValidationError(
                    "The DOCX archive contains too many entries.",
                    code="too_many_archive_members",
                )

            member_names = {member.filename for member in members}

            if not REQUIRED_DOCX_MEMBERS.issubset(member_names):
                raise ValidationError(
                    "The uploaded file is not a valid DOCX document.",
                    code="invalid_docx_structure",
                )

            uncompressed_size = sum(
                member.file_size for member in members
            )

            if (
                uncompressed_size
                > settings.DOCUMENT_MAX_UNCOMPRESSED_SIZE_BYTES
            ):
                raise ValidationError(
                    "The uncompressed DOCX content is too large.",
                    code="uncompressed_file_too_large",
                )

    except BadZipFile as exc:
        raise ValidationError(
            "The uploaded file is corrupted or is not a valid DOCX document.",
            code="corrupted_docx",
        ) from exc

    finally:
        uploaded_file.seek(current_position)