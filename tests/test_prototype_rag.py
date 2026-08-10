import tempfile
import unittest
from pathlib import Path

import pandas as pd

import app.backend.pipeline_rag.run as rag


class RagTest(unittest.TestCase):
    def test_load_prioritized_genes_defaults_to_selected_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = Path(temp_dir) / "prioritized.csv"
            pd.DataFrame(
                {
                    "rank": [1, 2],
                    "selected_for_search": [True, False],
                    "gene_id": ["selected", "ignored"],
                    "primary_name": ["Selected", "Ignored"],
                    "search_query": ["selected query", "ignored query"],
                    "represented_clusters": ["BP:up:1", ""],
                }
            ).to_csv(input_file, index=False)

            genes = rag.load_prioritized_genes(input_file)

        self.assertEqual(["selected"], genes["gene_id"].tolist())

    def test_retrieval_queries_separate_gene_name_from_ontology_context(self) -> None:
        gene = pd.Series(
            {
                "gene_id": "gene-1",
                "primary_name": "Gene One",
                "cluster_themes": "cluster theme",
                "search_query": "Gene One, root hair elongation, xyloglucan metabolic process",
            }
        )
        cluster_interpretations = [{"cluster": "BP:up:1", "interpretation": "cell wall biosynthesis"}]

        queries = rag.retrieval_queries_for_gene(gene, cluster_interpretations)

        self.assertEqual("Gene One", queries["bm25"])
        self.assertIn("root hair elongation", queries["embedding"])
        self.assertIn("xyloglucan metabolic process", queries["embedding"])
        self.assertNotIn("cluster theme", queries["embedding"])
        self.assertNotIn("cell wall biosynthesis", queries["embedding"])
        self.assertNotIn("gene-1", queries["bm25"])

    def test_retrieval_queries_include_dynamic_aliases_from_input_table(self) -> None:
        gene = pd.Series(
            {
                "gene_id": "Sh02_g028230",
                "primary_name": "Probable xyloglucan 6-xylosyltransferase 5",
                "Name GFF": "Glycosyltransferase",
                "Uniprot gene names": (
                    "Probable xyloglucan 6-xylosyltransferase 5 (EC 2.4.2.39) (Putative glycosyltransferase 5) (AtGT5)"
                ),
                "search_query": ("Probable xyloglucan 6-xylosyltransferase 5, xyloglucan biosynthetic process"),
            }
        )

        queries = rag.retrieval_queries_for_gene(gene, [])

        self.assertIn("AtGT5", queries["aliases"])
        self.assertIn("AtGT5", queries["bm25"])
        self.assertIn("xyloglucan biosynthetic process", queries["context_phrases"])
        self.assertNotIn("Sh02_g028230", queries["bm25"])

    def test_evidence_signals_reports_name_match_observations(self) -> None:
        gene = pd.Series({"primary_name": "Proline dehydrogenase"})
        queries = {
            "bm25": "Proline dehydrogenase",
            "embedding": "proline catabolic process",
            "aliases": ("Proline dehydrogenase",),
            "context_phrases": ("proline catabolic process",),
        }
        chunks = [
            {
                "text": "The proline dehydrogenase enzyme participates in proline catabolism.",
            }
        ]

        evidence = rag.evidence_signals(gene, queries, chunks)

        self.assertNotIn("level", evidence)
        self.assertTrue(evidence["name_and_alias_matches"]["full_name_in_text"])
        self.assertEqual(
            ["proline", "dehydrogenase"],
            evidence["name_and_alias_matches"]["matched_name_terms"],
        )
        self.assertEqual(1, evidence["retrieval_overview"]["chunks_returned"])

    def test_strip_markdown_removes_headings_lists_and_emphasis(self) -> None:
        text = "### Role\n1. **ATP synthase** uses *atp9* in mitochondria."

        self.assertEqual(
            "Role ATP synthase uses atp9 in mitochondria.",
            rag.strip_markdown(text),
        )

    def test_analyze_genes_groups_chunks_and_interpretation_per_gene(self) -> None:
        genes = pd.DataFrame(
            {
                "rank": [1],
                "selected_for_search": [True],
                "gene_id": ["gene-1"],
                "primary_name": ["Gene One"],
                "search_query": ["query"],
                "represented_clusters": ["BP:up:1"],
            }
        )

        original_search_chunks = rag.search_chunks
        try:
            rag.search_chunks = lambda *args, **kwargs: [
                {
                    "hit_rank": 1,
                    "source": "source-1",
                    "article_title": "",
                    "section": "",
                    "text": "doc 0",
                },
                {
                    "hit_rank": 2,
                    "source": "source-2",
                    "article_title": "",
                    "section": "",
                    "text": "doc 1",
                },
            ]
            result = rag.analyze_genes(
                genes,
                collection=None,
                cluster_interpretations={"BP:up:1": "cluster theme"},
                n_results=2,
                interpreter=lambda gene, chunks, clusters: f"{gene['gene_id']} ok: {clusters[0]['interpretation']}",
            )
        finally:
            rag.search_chunks = original_search_chunks

        self.assertEqual(1, len(result))
        self.assertEqual("gene-1", result[0]["gene_id"])
        self.assertEqual(["doc 0", "doc 1"], [chunk["text"] for chunk in result[0]["chunks"]])
        self.assertEqual(["C1", "C2"], [chunk["citation_id"] for chunk in result[0]["chunks"]])
        self.assertEqual(
            [{"cluster": "BP:up:1", "interpretation": "cluster theme"}],
            result[0]["cluster_interpretations"],
        )
        self.assertEqual("gene-1 ok: cluster theme", result[0]["interpretation"])
        self.assertEqual([], result[0]["chunk_interpretations"])
        self.assertEqual("", result[0]["cross_chunk_synthesis"])

    def test_analyze_genes_adds_structured_interpretation_fields(self) -> None:
        genes = pd.DataFrame(
            {
                "rank": [1],
                "selected_for_search": [True],
                "gene_id": ["gene-1"],
                "primary_name": ["Gene One"],
                "search_query": ["query"],
                "represented_clusters": ["BP:up:1"],
            }
        )

        original_search_chunks = rag.search_chunks
        try:
            rag.search_chunks = lambda *args, **kwargs: [
                {
                    "hit_rank": 1,
                    "source": "source-1",
                    "article_title": "Article",
                    "section": "Results",
                    "text": "Gene One is discussed with cell wall metabolism.",
                }
            ]
            result = rag.analyze_genes(
                genes,
                collection=None,
                cluster_interpretations={"BP:up:1": "cluster theme"},
                n_results=1,
                interpreter=lambda gene, chunks, clusters: {
                    "chunk_interpretations": [
                        {
                            "chunk_ref": "C1",
                            "source": "source-1",
                            "section": "Results",
                            "supported_observation": "Cell wall metabolism is discussed.",
                            "used_in_synthesis": True,
                        }
                    ],
                    "cross_chunk_synthesis": "The chunk supports cell wall context [C1].",
                    "interpretation": "Gene One is supported by cell wall context [C1].",
                },
            )
        finally:
            rag.search_chunks = original_search_chunks

        self.assertEqual(
            "The chunk supports cell wall context [C1].",
            result[0]["cross_chunk_synthesis"],
        )
        self.assertEqual(
            "Gene One is supported by cell wall context [C1].",
            result[0]["interpretation"],
        )
        self.assertEqual("C1", result[0]["chunk_interpretations"][0]["chunk_ref"])

    def test_cluster_interpretations_are_loaded_by_represented_cluster_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_file = Path(temp_dir) / "interpretations.csv"
            pd.DataFrame(
                {
                    "ontology": ["BP"],
                    "direction": ["up"],
                    "cluster": [1],
                    "n_genes": [3],
                    "interpretation": ["cluster theme"],
                }
            ).to_csv(input_file, index=False)

            interpretations = rag.load_cluster_interpretations(input_file)

        gene = pd.Series({"represented_clusters": "BP:up:1; MF:down:2"})
        self.assertEqual(
            [{"cluster": "BP:up:1", "interpretation": "cluster theme"}],
            rag.cluster_interpretations_for_gene(gene, interpretations),
        )

    def test_search_chunks_filters_noisy_candidates_before_reranking(self) -> None:
        raw_chunks = [
            {
                "hit_rank": 1,
                "source": "refs.md",
                "section": "References",
                "text": "reference-only text",
            },
            {
                "hit_rank": 2,
                "source": "table.md",
                "section": "Results",
                "text": "|".join(["cell"] * 20),
            },
            {
                "hit_rank": 3,
                "source": "source-a.md",
                "section": "Discussion",
                "text": "first useful discussion",
            },
            {
                "hit_rank": 4,
                "source": "source-a.md",
                "section": "Discussion",
                "text": "second useful discussion from same source",
            },
            {
                "hit_rank": 5,
                "source": "source-a.md",
                "section": "Discussion",
                "text": "third useful discussion from same source",
            },
            {
                "hit_rank": 6,
                "source": "source-b.md",
                "section": "Results",
                "text": "useful discussion from another source",
            },
        ]
        chunks = rag.select_retrieved_chunks(
            raw_chunks,
            n_results=3,
            max_chunks_per_source=1,
        )

        self.assertEqual(
            [
                "first useful discussion",
                "useful discussion from another source",
                "second useful discussion from same source",
            ],
            [chunk["text"] for chunk in chunks],
        )
        self.assertEqual([1, 2, 3], [chunk["hit_rank"] for chunk in chunks])
        self.assertEqual([3, 6, 4], [chunk["retrieved_rank"] for chunk in chunks])
        self.assertEqual(["C1", "C2", "C3"], [chunk["citation_id"] for chunk in chunks])

    def test_search_chunks_returns_empty_when_all_candidates_are_noisy(self) -> None:
        raw_chunks = [
            {
                "hit_rank": 1,
                "source": "table.md",
                "section": "Tables",
                "text": "table text",
            },
            {
                "hit_rank": 2,
                "source": "refs.md",
                "section": "Discussion",
                "text": "Pubmed: citation Google Scholar",
            },
        ]

        self.assertEqual([], rag.select_retrieved_chunks(raw_chunks, n_results=2))

    def test_rerank_prefers_chunks_matching_name_and_context(self) -> None:
        queries = {
            "bm25": "Potassium channel KOR1",
            "embedding": "voltage-gated potassium channel activity membrane",
            "aliases": ("Potassium channel KOR1", "KOR1"),
            "context_phrases": ("voltage-gated potassium channel activity", "membrane"),
        }
        chunks = [
            {
                "hit_rank": 1,
                "text": "Transporters coordinate iron translocation during stress.",
            },
            {
                "hit_rank": 2,
                "text": "Potassium channel activity regulates membrane potential.",
            },
        ]

        reranked = rag.rerank_chunks_by_name_and_context(chunks, queries)

        self.assertEqual(2, reranked[0]["hit_rank"])

    def test_rerank_prefers_payload_gene_and_context_matches(self) -> None:
        queries = {
            "bm25": "Potassium channel KOR1",
            "embedding": "voltage-gated potassium channel activity membrane",
            "aliases": ("Potassium channel KOR1", "KOR1"),
            "context_phrases": ("voltage-gated potassium channel activity", "membrane"),
        }
        chunks = [
            {
                "hit_rank": 1,
                "text": "Potassium transport is discussed generically.",
                "protein_family_mentions": ["potassium channel"],
            },
            {
                "hit_rank": 2,
                "text": "KOR1 regulates ion flux at the membrane.",
                "gene_like_mentions": ["KOR1"],
                "protein_family_mentions": ["potassium channel"],
                "go_mentions": ["voltage-gated potassium channel activity"],
            },
        ]

        reranked = rag.rerank_chunks_by_name_and_context(chunks, queries)

        self.assertEqual(2, reranked[0]["hit_rank"])
        self.assertEqual(
            ["KOR1"],
            reranked[0]["payload_match"]["alias_payload_matches"],
        )

    def test_evidence_signals_reports_context_without_final_classification(self) -> None:
        gene = pd.Series({"primary_name": "Potassium channel KOR1"})
        queries = {
            "bm25": "Potassium channel KOR1",
            "embedding": "voltage-gated potassium channel activity membrane",
            "aliases": ("Potassium channel KOR1", "KOR1"),
            "context_phrases": ("voltage-gated potassium channel activity", "membrane"),
        }
        chunks = [
            {
                "text": "Potassium channels regulate membrane potential and ion transport.",
            }
        ]

        evidence = rag.evidence_signals(gene, queries, chunks)

        self.assertNotIn("level", evidence)
        self.assertIn("context", evidence["observed_signal_types"])
        self.assertIn(
            "membrane",
            evidence["biological_context_matches"]["context_text_terms"],
        )

    def test_evidence_signals_reports_payload_gene_mentions(self) -> None:
        gene = pd.Series({"primary_name": "Potassium channel KOR1"})
        queries = {
            "bm25": "Potassium channel KOR1 KOR1",
            "embedding": "voltage-gated potassium channel activity",
            "aliases": ("Potassium channel KOR1", "KOR1"),
            "context_phrases": ("voltage-gated potassium channel activity",),
        }
        chunks = [
            {
                "text": "This channel regulates potassium flux.",
                "gene_like_mentions": ["KOR1"],
                "protein_family_mentions": ["potassium channel"],
                "go_mentions": ["voltage-gated potassium channel activity"],
            }
        ]

        evidence = rag.evidence_signals(gene, queries, chunks)

        self.assertNotIn("level", evidence)
        self.assertEqual(
            ["KOR1"],
            evidence["name_and_alias_matches"]["alias_payload_matches"],
        )
        self.assertIn("protein_family", evidence["observed_signal_types"])
        self.assertIn("go_process", evidence["observed_signal_types"])

    def test_build_interpretation_prompt_uses_chunk_citations_and_json_schema(self) -> None:
        gene = pd.Series(
            {
                "gene_id": "gene-1",
                "primary_name": "Gene One",
                "direction": "up",
            }
        )
        chunks = [
            {
                "citation_id": "C1",
                "chunk_id": "chunk-1",
                "hit_rank": 1,
                "retrieved_rank": 3,
                "source": "source-1.md",
                "article_title": "Article",
                "section": "Results",
                "payload_match": {"alias_text_matches": ["Gene One"]},
                "gene_like_mentions": ["Gene One"],
                "text": "Gene One participates in a biological process.",
            }
        ]

        prompt = rag.build_interpretation_prompt(gene, chunks, [])

        self.assertIn('"chunk_ref": "C1"', prompt)
        self.assertIn('"chunk_id": "chunk-1"', prompt)
        self.assertIn("Return valid JSON only", prompt)
        self.assertIn("Every biological claim", prompt)

    def test_parse_interpretation_response_extracts_structured_json(self) -> None:
        response = """
        ```json
        {
          "chunk_interpretations": [{"chunk_ref": "C1"}],
          "cross_chunk_synthesis": "The article supports a process [C1].",
          "interpretation": "The gene is connected to the process [C1]."
        }
        ```
        """

        parsed = rag.parse_interpretation_response(response)

        self.assertEqual([{"chunk_ref": "C1"}], parsed["chunk_interpretations"])
        self.assertEqual(
            "The article supports a process [C1].",
            parsed["cross_chunk_synthesis"],
        )
        self.assertEqual(
            "The gene is connected to the process [C1].",
            parsed["interpretation"],
        )


if __name__ == "__main__":
    unittest.main()
