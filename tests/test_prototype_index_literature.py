import tempfile
import unittest
from pathlib import Path

import app.backend.pipeline_rag.index as index_literature
import app.backend.pipeline_rag.literature as literature_entities


class IndexLiteratureTest(unittest.TestCase):
    def test_chunks_do_not_cross_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            article = Path(temp_dir) / "article.md"
            article.write_text(
                "# Article Title\n\n"
                "First sentence. Second sentence. Third sentence.\n\n"
                "## Results\n\n"
                "Fourth sentence. Fifth sentence. Sixth sentence.\n",
                encoding="utf-8",
            )

            chunks = index_literature.chunk_article(
                article,
                target_words=4,
                overlap_sentences=1,
                min_chunk_words=1,
            )

        self.assertTrue(chunks)
        self.assertEqual({"article.md"}, {chunk["metadata"]["fonte"] for chunk in chunks})
        self.assertFalse(
            any("Third sentence" in chunk["text"] and "Fourth sentence" in chunk["text"] for chunk in chunks)
        )

    def test_sentence_overlap_is_preserved_within_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            article = Path(temp_dir) / "article.md"
            article.write_text(
                "# Article Title\n\nAlpha sentence. Beta sentence. Gamma sentence. Delta sentence.",
                encoding="utf-8",
            )

            chunks = index_literature.chunk_article(
                article,
                target_words=4,
                overlap_sentences=1,
                min_chunk_words=1,
            )

        self.assertGreaterEqual(len(chunks), 2)
        repeated = [
            sentence
            for sentence in ["Alpha sentence", "Beta sentence", "Gamma sentence"]
            if sum(sentence in chunk["text"] for chunk in chunks) > 1
        ]
        self.assertTrue(repeated)

    def test_low_value_sections_are_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            article = Path(temp_dir) / "article.md"
            article.write_text(
                "# Article Title\n\n"
                "Useful biological evidence.\n\n"
                "## References\n\n"
                "Noisy citation that should not be indexed.\n",
                encoding="utf-8",
            )

            chunks = index_literature.chunk_article(article, min_chunk_words=1)

        self.assertTrue(any("Useful biological evidence" in chunk["text"] for chunk in chunks))
        self.assertFalse(any("Noisy citation" in chunk["text"] for chunk in chunks))

    def test_table_like_chunks_are_skipped_by_default(self) -> None:
        table = " | ".join(f"cell {index}" for index in range(20))
        with tempfile.TemporaryDirectory() as temp_dir:
            article = Path(temp_dir) / "article.md"
            article.write_text(
                f"# Article Title\n\n## Results\n\n{table}\n\n## Discussion\n\nUseful discussion sentence.",
                encoding="utf-8",
            )

            chunks = index_literature.chunk_article(article, min_chunk_words=1)

        self.assertTrue(any("Useful discussion sentence" in chunk["text"] for chunk in chunks))
        self.assertFalse(any("cell 19" in chunk["text"] for chunk in chunks))

    def test_short_metadata_chunks_are_skipped_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            article = Path(temp_dir) / "article.md"
            abstract = " ".join(["Useful biological evidence"] * 20)
            article.write_text(
                "# Article Title\n\n"
                "## Author List\n\n"
                "Alyssa A. Gulledge, Hiral Vora, Ketan Patel, and Ann E. Loraine.\n\n"
                f"## Abstract\n\n{abstract}",
                encoding="utf-8",
            )

            chunks = index_literature.chunk_article(article)

        self.assertTrue(any("Useful biological evidence" in chunk["text"] for chunk in chunks))
        self.assertFalse(any("Alyssa A. Gulledge" in chunk["text"] for chunk in chunks))

    def test_bm25_tokenizer_keeps_compound_and_split_terms(self) -> None:
        tokens = index_literature.tokenize_for_bm25("Carbamoyl-phosphate synthase")

        self.assertIn("carbamoyl-phosphate", tokens)
        self.assertIn("carbamoyl", tokens)
        self.assertIn("phosphate", tokens)
        self.assertIn("synthase", tokens)

    def test_bm25_sparse_vector_prioritizes_exact_terms(self) -> None:
        model = index_literature.build_bm25_model(
            [
                "carbamoyl-phosphate synthase chloroplastic",
                "xyloglucan xylosyltransferase",
            ]
        )

        indices, values = index_literature.bm25_sparse_vector(
            "carbamoyl-phosphate synthase",
            model,
        )

        self.assertEqual(len(indices), len(values))
        self.assertTrue(indices)
        self.assertIn(model["vocabulary"]["carbamoyl-phosphate"], indices)
        self.assertIn(model["vocabulary"]["synthase"], indices)

    def test_index_chunks_adds_entity_annotations_to_payload(self) -> None:
        def fake_embed_texts(texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

        def fake_annotate_many(
            nlp: object,
            texts: list[str],
            batch_size: int,
        ) -> list[dict[str, object]]:
            return [
                {
                    "gene_like_mentions": ["PIF3"],
                    "has_gene_like_mention": True,
                }
                for _ in texts
            ]

        class FakeClient:
            def __init__(self) -> None:
                self.points = []

            def upsert(self, collection_name: str, points: list[object]) -> None:
                self.points.extend(points)

        original_embed_texts = index_literature.embed_texts
        original_annotate_many = literature_entities.annotate_many
        index_literature.embed_texts = fake_embed_texts
        literature_entities.annotate_many = fake_annotate_many
        try:
            client = FakeClient()
            chunks = [
                {
                    "id": "chunk-1",
                    "text": "PIF3 regulates light signaling.",
                    "metadata": {
                        "fonte": "article.md",
                        "article_title": "Article",
                        "section": "Discussion",
                    },
                }
            ]
            model = index_literature.build_bm25_model([chunks[0]["text"]])

            index_literature.index_chunks(
                client=client,
                collection_name="test",
                chunks=chunks,
                bm25_model=model,
                batch_size=1,
                annotator=object(),
            )
        finally:
            index_literature.embed_texts = original_embed_texts
            literature_entities.annotate_many = original_annotate_many

        self.assertEqual(["PIF3"], client.points[0].payload["gene_like_mentions"])
        self.assertTrue(client.points[0].payload["has_gene_like_mention"])


if __name__ == "__main__":
    unittest.main()
