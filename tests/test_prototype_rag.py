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
        self.assertEqual("insufficient_evidence", result[0]["interpretation_status"])
        self.assertEqual([], result[0]["claims"])
        self.assertEqual([], result[0]["chunk_interpretations"])
        self.assertEqual(
            "The retrieved literature is insufficient to support a gene-specific interpretation.",
            result[0]["cross_chunk_synthesis"],
        )

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
                    "claims": [
                        {
                            "claim": "Gene One is discussed with cell wall metabolism.",
                            "citations": ["C1"],
                            "evidence_level": "general",
                            "relationship_to_query": "unknown",
                            "confidence": "low",
                        }
                    ]
                },
            )
        finally:
            rag.search_chunks = original_search_chunks

        self.assertEqual("supported_claims", result[0]["interpretation_status"])
        self.assertEqual(1, len(result[0]["claims"]))
        self.assertEqual(
            "Gene One is discussed with cell wall metabolism. [C1]",
            result[0]["interpretation"],
        )
        self.assertEqual([], result[0]["chunk_interpretations"])

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
          "claims": [{"claim": "A related family participates in a process.", "citations": ["C1"], "evidence_level": "family", "relationship_to_query": "family"}]
        }
        ```
        """

        parsed = rag.parse_interpretation_response(response)

        self.assertTrue(parsed["model_output_valid"])
        self.assertEqual("A related family participates in a process.", parsed["claims"][0]["claim"])

    def test_parse_interpretation_response_rejects_truncated_json(self) -> None:
        parsed = rag.parse_interpretation_response('{"claims": [{"claim": "truncated"')
        self.assertFalse(parsed["model_output_valid"])
        self.assertEqual([], parsed["claims"])
        self.assertIn("truncated", parsed["raw_model_output"])

    def test_atomic_claim_validator_rejects_uncited_and_unverified_direct_claims(self) -> None:
        gene = pd.Series({"gene_id": "gene-1", "primary_name": "Gene One"})
        chunks = rag.annotate_chunks_for_generation(
            gene,
            [
                {
                    "citation_id": "C1",
                    "text": "Gene One was discussed in this study.",
                    "payload_match": {"alias_text_matches": ["Gene One"]},
                }
            ],
        )
        result = rag.finalize_interpretation_result(
            gene,
            chunks,
            {
                "claims": [
                    {"claim": "Gene One is essential.", "citations": [], "evidence_level": "direct"},
                    {
                        "claim": "Gene One controls growth.",
                        "citations": ["C1"],
                        "evidence_level": "direct",
                        "relationship_to_query": "same_gene",
                    },
                ]
            },
        )
        self.assertEqual("insufficient_evidence", result["status"])
        reasons = {reason for item in result["rejected_claims"] for reason in item["reasons"]}
        self.assertIn("missing_citation", reasons)
        self.assertIn("unverified_direct_evidence", reasons)

    def test_kor1_policy_blocks_korrigan_cellulose_chunk(self) -> None:
        gene = pd.Series({"gene_id": "Sh10_g009020", "primary_name": "Potassium channel KOR1"})
        chunks = rag.annotate_chunks_for_generation(
            gene,
            [{"citation_id": "C1", "text": "KORRIGAN1 (KOR1) participates in cellulose synthesis."}],
        )
        self.assertTrue(chunks[0]["evidence_assessment"]["blocked"])

    def test_atomic_claim_validator_rejects_unverified_orthology(self) -> None:
        gene = pd.Series({"gene_id": "Sh_gene", "primary_name": "Candidate protein"})
        chunks = rag.annotate_chunks_for_generation(
            gene,
            [{"citation_id": "C1", "text": "Candidate protein was described in Arabidopsis."}],
        )
        result = rag.finalize_interpretation_result(
            gene,
            chunks,
            {
                "claims": [
                    {
                        "claim": "The Arabidopsis ortholog participates in growth.",
                        "citations": ["C1"],
                        "evidence_level": "ortholog",
                        "relationship_to_query": "ortholog",
                    }
                ]
            },
        )
        self.assertEqual("insufficient_evidence", result["status"])
        self.assertIn("unverified_ortholog_attribution", result["rejected_claims"][0]["reasons"])

    def test_atomic_claim_validator_accepts_explicit_family_claim_with_name_signal(self) -> None:
        gene = pd.Series({"gene_id": "Sh_gene", "primary_name": "Candidate glycosyltransferase"})
        chunks = rag.annotate_chunks_for_generation(
            gene,
            [
                {
                    "citation_id": "C1",
                    "text": "Glycosyltransferase genes participate in cell wall polysaccharide biosynthesis.",
                    "payload_match": {"alias_text_matches": ["glycosyltransferase"]},
                }
            ],
        )
        result = rag.finalize_interpretation_result(
            gene,
            chunks,
            {
                "claims": [
                    {
                        "claim": "Glycosyltransferase family members participate in cell wall polysaccharide biosynthesis.",
                        "citations": ["C1"],
                        "evidence_level": "general",
                        "relationship_to_query": "family",
                    }
                ]
            },
        )
        self.assertEqual("supported_claims", result["status"])

    def test_atomic_claim_validator_rejects_family_evidence_attributed_to_query_gene(self) -> None:
        gene = pd.Series({"gene_id": "Sh_gene", "primary_name": "Candidate glycosyltransferase"})
        chunks = rag.annotate_chunks_for_generation(
            gene,
            [{"citation_id": "C1", "text": "Glycosyltransferase family members participate in cell walls.", "payload_match": {"alias_text_matches": ["glycosyltransferase"]}}],
        )
        result = rag.finalize_interpretation_result(
            gene,
            chunks,
            {"claims": [{"claim": "The gene's function involves cell walls.", "citations": ["C1"], "evidence_level": "general", "relationship_to_query": "family"}]},
        )
        self.assertEqual("insufficient_evidence", result["status"])
        self.assertIn("indirect_evidence_attributed_to_query_gene", result["rejected_claims"][0]["reasons"])

    def test_retrieval_queries_are_split_into_facets(self) -> None:
        gene = pd.Series(
            {
                "primary_name": "Gene One",
                "search_query": "Gene One, enzyme activity, response to drought, nucleus",
            }
        )
        queries = rag.retrieval_queries_for_gene(gene, [])
        facets = {item["facet"] for item in queries["facets"]}
        self.assertIn("identity", facets)
        self.assertIn("molecular_function", facets)
        self.assertIn("expression_or_stress", facets)
        self.assertIn("localization", facets)

    def test_validator_rejects_species_condition_combined_from_different_sentences(self) -> None:
        gene = pd.Series({"gene_id": "Sh_gene", "primary_name": "Glycosyltransferase"})
        chunks = rag.annotate_chunks_for_generation(
            gene,
            [
                {
                    "citation_id": "C1",
                    "text": "Arabidopsis genes responded to IM. Glycosyltransferases responded to TBM in tomato.",
                    "species_mentions": ["Arabidopsis", "tomato"],
                    "payload_match": {"alias_text_matches": ["Glycosyltransferases"]},
                }
            ],
        )
        result = rag.finalize_interpretation_result(
            gene,
            chunks,
            {
                "claims": [
                    {
                        "claim": "Glycosyltransferases responded to TBM in Arabidopsis.",
                        "citations": ["C1"],
                        "evidence_level": "general",
                        "relationship_to_query": "family",
                        "species": "Arabidopsis",
                        "conditions": ["TBM"],
                    }
                ]
            },
        )
        self.assertEqual("insufficient_evidence", result["status"])
        self.assertIn("unverified_species_condition_pair:Arabidopsis:TBM", result["rejected_claims"][0]["reasons"])

    def test_atp9_ambiguous_alias_requires_mitochondrial_context(self) -> None:
        gene = pd.Series({"gene_id": "Sh01_g044020", "primary_name": "ATP synthase subunit 9, mitochondrial"})
        blocked = rag.annotate_chunks_for_generation(
            gene,
            [{"citation_id": "C1", "text": "A lipid-binding protein controls pollen fertility."}],
        )
        accepted = rag.annotate_chunks_for_generation(
            gene,
            [{"citation_id": "C1", "text": "The mitochondrial ATP9 lipid-binding protein is ATP synthase subunit 9."}],
        )
        self.assertTrue(blocked[0]["evidence_assessment"]["blocked"])
        self.assertFalse(accepted[0]["evidence_assessment"]["blocked"])


if __name__ == "__main__":
    unittest.main()
