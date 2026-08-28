from django.test import SimpleTestCase

from documents.services.chunking import (
    ChunkingError,
    split_text_into_chunks,
)
from documents.tests.helpers import FakeTokenizer


class ChunkingTests(SimpleTestCase):
    def setUp(self):
        self.tokenizer = FakeTokenizer()

    def test_returns_no_chunks_for_empty_text(self):
        chunks = split_text_into_chunks(
            " \n ",
            tokenizer=self.tokenizer,
            chunk_size=10,
            chunk_overlap=2,
        )

        self.assertEqual(chunks, [])

    def test_preserves_content_order_and_offsets(self):
        text = (
            "یک دو سه چهار پنج شش هفت هشت نه ده. "
            * 20
        ).strip()

        chunks = split_text_into_chunks(
            text,
            tokenizer=self.tokenizer,
            chunk_size=20,
            chunk_overlap=4,
        )

        self.assertGreater(len(chunks), 1)

        for index, chunk in enumerate(chunks):
            self.assertTrue(chunk.content)
            self.assertLessEqual(chunk.token_count, 20)
            self.assertEqual(
                text[
                    chunk.start_offset:chunk.end_offset
                ],
                chunk.content,
            )

            if index == 0:
                continue

            previous_chunk = chunks[index - 1]

            self.assertGreater(
                chunk.start_offset,
                previous_chunk.start_offset,
            )

            overlap_text = text[
                chunk.start_offset:
                previous_chunk.end_offset
            ]

            overlap_token_count = len(
                self.tokenizer.encode(
                    overlap_text,
                    add_special_tokens=False,
                ).ids
            )

            self.assertLessEqual(
                overlap_token_count,
                4,
            )

    def test_rejects_invalid_overlap(self):
        with self.assertRaises(ChunkingError):
            split_text_into_chunks(
                "متن آزمایشی",
                tokenizer=self.tokenizer,
                chunk_size=10,
                chunk_overlap=10,
            )
