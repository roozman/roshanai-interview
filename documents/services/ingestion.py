import logging
from hashlib import sha256
from typing import BinaryIO
from zipfile import BadZipFile

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

from documents.models import Document, DocumentChunk
from documents.validators import validate_docx_file

from documents.services.chunking import (
    ChunkingError,
    replace_document_chunks,
    split_text_into_chunks,
)

from documents.services.embeddings import (
    EmbeddingServiceError,
    embed_document_chunks,
)

logger = logging.getLogger(__name__)

READ_CHUNK_SIZE = 1024 * 1024


class EmptyDocumentError(ValueError):
    pass


def calculate_sha256(file_stream: BinaryIO) -> str:
    digest = sha256()

    while chunk := file_stream.read(READ_CHUNK_SIZE):
        digest.update(chunk)

    return digest.hexdigest()


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def extract_docx_text(file_stream: BinaryIO) -> str:
    docx_document = DocxDocument(file_stream)
    text_blocks: list[str] = []

    for block in docx_document.iter_inner_content():
        if isinstance(block, Paragraph):
            text = normalize_text(block.text)

            if text:
                text_blocks.append(text)

        elif isinstance(block, Table):
            for row in block.rows:
                cells = [
                    normalize_text(cell.text)
                    for cell in row.cells
                ]

                if any(cells):
                    text_blocks.append(" | ".join(cells))

    full_text = "\n".join(text_blocks).strip()

    if not full_text:
        raise EmptyDocumentError(
            "The DOCX document does not contain extractable text."
        )

    return full_text


def process_document(document_id: int) -> Document:
    document = Document.objects.get(pk=document_id)

    with transaction.atomic():
        DocumentChunk.objects.filter(
            document_id=document_id
        ).delete()

        Document.objects.filter(pk=document_id).update(
            status=Document.Status.PROCESSING,
            full_text="",
            checksum="",
            error_message="",
            updated_at=timezone.now(),
        )

    checksum = ""

    try:
        with document.file.open("rb") as file_stream:
            validate_docx_file(file_stream)

        with document.file.open("rb") as file_stream:
            checksum = calculate_sha256(file_stream)

        with document.file.open("rb") as file_stream:
            full_text = extract_docx_text(file_stream)

        chunks = split_text_into_chunks(full_text)

        with transaction.atomic():
            replace_document_chunks(
                document_id=document_id,
                chunks=chunks,
            )

            Document.objects.filter(
                pk=document_id
            ).update(
                status=Document.Status.PROCESSING,
                full_text=full_text,
                checksum=checksum,
                error_message="",
                updated_at=timezone.now(),
            )
        embed_document_chunks(document_id)

        Document.objects.filter(
            pk=document_id
        ).update(
            status=Document.Status.INDEXED,
            error_message="",
            updated_at=timezone.now(),
        )

    except ValidationError as exc:
        error_message = " ".join(exc.messages)

    except EmptyDocumentError as exc:
        error_message = str(exc)

    except EmbeddingServiceError:
        logger.warning(
            "Embeddings could not be generated "
            "for document %s.",
            document_id,
            exc_info=True,
        )
        error_message = (
            "The document embeddings could not "
            "be generated."
        )

    except ChunkingError as exc:
        logger.warning(
            "Document %s could not be chunked.",
            document_id,
            exc_info=True,
        )
        error_message = str(exc)

    except (BadZipFile, PackageNotFoundError, OSError, ValueError):
        logger.warning(
            "Document %s could not be parsed.",
            document_id,
            exc_info=True,
        )
        error_message = (
            "The DOCX document could not be processed."
        )

    except Exception:
        logger.exception(
            "Unexpected error while processing document %s.",
            document_id,
        )
        error_message = (
            "An unexpected error occurred while "
            "processing the document."
        )

    else:
        return Document.objects.get(pk=document_id)

    with transaction.atomic():
        DocumentChunk.objects.filter(
            document_id=document_id
        ).delete()

        Document.objects.filter(pk=document_id).update(
            status=Document.Status.FAILED,
            full_text="",
            checksum=checksum,
            error_message=error_message,
            updated_at=timezone.now(),
        )

    return Document.objects.get(pk=document_id)