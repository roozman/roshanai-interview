from dataclasses import dataclass
from functools import lru_cache

from django.db import transaction
from documents.models import DocumentChunk

from django.conf import settings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tokenizers import Tokenizer

from documents.constants import TOKENIZER_MODEL_NAME


PERSIAN_SEPARATORS = [
    "\n\n",
    "\n",
    "؟ ",
    "! ",
    ". ",
    "؛ ",
    "، ",
    " ",
    "",
]


class ChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class TextChunk:
    content: str
    start_offset: int
    end_offset: int
    token_count: int


@lru_cache(maxsize=1)
def get_tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(TOKENIZER_MODEL_NAME)


def count_tokens(
    text: str,
    tokenizer: Tokenizer | None = None,
) -> int:
    active_tokenizer = tokenizer or get_tokenizer()

    return len(
        active_tokenizer.encode(
            text,
            add_special_tokens=False,
        ).ids
    )

def find_chunk_start_offset(
    *,
    text: str,
    content: str,
    tokenizer: Tokenizer,
    previous_start_offset: int | None,
    previous_end_offset: int | None,
    max_overlap_tokens: int,
) -> int:
    search_position = (
        0
        if previous_start_offset is None
        else previous_start_offset + 1
    )

    while True:
        candidate = text.find(content, search_position)

        if candidate < 0:
            raise ChunkingError(
                "Could not determine chunk offset."
            )

        if previous_end_offset is None:
            return candidate

        overlap_text = (
            text[candidate:previous_end_offset]
            if candidate < previous_end_offset
            else ""
        )

        overlap_token_count = count_tokens(
            overlap_text,
            tokenizer,
        )

        if overlap_token_count <= max_overlap_tokens:
            return candidate

        search_position = candidate + 1

def split_text_into_chunks(
    text: str,
    *,
    tokenizer: Tokenizer | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[TextChunk]:
    if not text.strip():
        return []

    active_tokenizer = tokenizer or get_tokenizer()
    active_chunk_size = (
        chunk_size or settings.DOCUMENT_CHUNK_SIZE_TOKENS
    )
    active_chunk_overlap = (
        chunk_overlap
        if chunk_overlap is not None
        else settings.DOCUMENT_CHUNK_OVERLAP_TOKENS
    )

    if active_chunk_size <= 0:
        raise ChunkingError(
            "Chunk size must be greater than zero."
        )

    if not 0 <= active_chunk_overlap < active_chunk_size:
        raise ChunkingError(
            "Chunk overlap must be zero or greater and "
            "smaller than chunk size."
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=active_chunk_size,
        chunk_overlap=active_chunk_overlap,
        length_function=lambda value: count_tokens(
            value,
            active_tokenizer,
        ),
        separators=PERSIAN_SEPARATORS,
        keep_separator="end",
        strip_whitespace=True,
    )

    split_contents = splitter.split_text(text)
    chunks: list[TextChunk] = []

    previous_start_offset: int | None = None
    previous_end_offset: int | None = None

    for content in split_contents:
        token_count = count_tokens(
            content,
            active_tokenizer,
        )

        if not content or token_count == 0:
            continue

        start_offset = find_chunk_start_offset(
            text=text,
            content=content,
            tokenizer=active_tokenizer,
            previous_start_offset=previous_start_offset,
            previous_end_offset=previous_end_offset,
            max_overlap_tokens=active_chunk_overlap,
        )
        end_offset = start_offset + len(content)

        chunks.append(
            TextChunk(
                content=content,
                start_offset=start_offset,
                end_offset=end_offset,
                token_count=token_count,
            )
        )

        previous_start_offset = start_offset
        previous_end_offset = end_offset

    return chunks

@transaction.atomic
def replace_document_chunks(
    document_id: int,
    chunks: list[TextChunk],
) -> list[DocumentChunk]:
    if not chunks:
        raise ChunkingError(
            "The document did not produce any valid chunks."
        )

    DocumentChunk.objects.filter(
        document_id=document_id
    ).delete()

    chunk_objects = [
        DocumentChunk(
            document_id=document_id,
            content=chunk.content,
            chunk_index=chunk_index,
            start_offset=chunk.start_offset,
            end_offset=chunk.end_offset,
            token_count=chunk.token_count,
        )
        for chunk_index, chunk in enumerate(chunks)
    ]

    return DocumentChunk.objects.bulk_create(
        chunk_objects
    )