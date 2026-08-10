Clustering and LLM Interpretation
=================================

Functional Clustering
---------------------

BILBO clusters DEG-derived records for each selected contrast sheet using an ontology-grounded functional annotation strategy. The clustering stage organizes genes according to the semantic relatedness of their Gene Ontology (GO) annotations rather than by textual proximity alone.

The method uses functional descriptors derived from GO records and UniProt annotation sources generated during annotation. Genes are separated by regulatory direction before clustering, so up- and down-regulated genes are not grouped only because they share broad functional labels. Clustering is also performed separately for the three GO ontologies:

* Biological Process (BP), emphasizing shared biological processes.
* Molecular Function (MF), emphasizing shared molecular activities.
* Cellular Component (CC), emphasizing shared localization or compartment association.

The implemented clustering workflow:

1. Loads one DEG sheet.
2. Separates genes according to regulatory direction and GO ontology.
3. Removes GO identifiers that are not present in the configured ``GO.db`` version.
4. Computes gene-level Wang semantic similarity from the GO directed acyclic graph.
5. Converts similarity to distance using ``distance = 1 - similarity``.
6. Applies agglomerative hierarchical clustering with complete linkage.
7. Treats small or weakly supported groups conservatively as unclustered.
8. Refines cluster assignments through silhouette-based pruning.
9. Reports cluster-level quality metrics, including silhouette values, mean silhouette, minimum silhouette, cluster size, minimum pairwise similarity, and quality labels.
10. Selects representative genes as semantic medoids, defined as the genes with highest mean Wang similarity to the other members of the same cluster.
11. Saves structured cluster outputs for downstream interpretation.

Interpretation of Clusters
--------------------------

Before literature retrieval, every eligible cluster is summarized once with
the prototype cluster prompt. Each gene is represented only by its ``function``
and ontology-specific ``go`` annotation. Gene identifiers, names, expression
statistics, similarity metrics, and external literature are deliberately not
sent to this prompt. BP, MF, and CC use different focus instructions, and the
result is persisted in ``clusters/interpretations.csv``.

After cluster interpretation, BILBO selects the Wang semantic medoid of each
cluster and deduplicates representatives across ontologies. A gene is selected
for literature search only when it represents clusters in at least two GO
ontologies. The complete ranking and selection rationale are stored in
``outputs/prioritized_genes.csv``.

Clusters are exploratory summaries of GO-based functional relatedness, not formal pathway enrichment tests. They are useful for organizing DEG lists and identifying broad biological modules, but users should validate cluster conclusions against:

* original gene annotations;
* DEG statistics;
* known organism biology;
* pathway or ontology enrichment, if available;
* experimental hypothesis.

RAG Interpretation
------------------

BILBO integrates clustering outputs with a Retrieval-Augmented Generation (RAG) module. The RAG layer connects representative genes and their cluster-level functional context to a curated scientific literature corpus. The plant-focused corpus is derived from PlantExp-associated studies and is distributed separately through Zenodo.

The retrieval workflow uses hybrid evidence recovery:

* Dense semantic retrieval uses the ``bge-m3`` embedding model.
* Sparse lexical retrieval uses BM25 to preserve exact gene aliases, protein-family names, and ontology terms.
* Dense and sparse rankings are fused using reciprocal rank fusion.
* A local reranking step favors chunks containing gene or alias matches, protein-family matches, GO-term matches, and contextual biological terms.
* Retrieved chunks carry source metadata, including article-level and section-level information, stable chunk identifiers, and DOI-linked evidence where available.

The interpretation workflow:

1. Loads only representatives selected by the multi-ontology rule.
2. Builds sparse queries from gene names and dynamic aliases.
3. Builds dense queries from ontology terms in the representative search query.
4. Retrieves and reranks evidence chunks from the literature corpus.
5. Executes local synthesis through Ollama under a closed-knowledge constraint.
6. Produces structured outputs containing chunk-level interpretations, cross-chunk synthesis, and final evidence-constrained interpretation.

RAG Output Should Be Treated as Assisted Interpretation
-------------------------------------------------------

.. warning::

   RAG outputs are interpretive aids, not primary statistical results. Although retrieval constrains the model to supplied evidence chunks, users must still inspect whether a conclusion is supported by direct gene evidence, protein-family evidence, GO or process context, or only weak background information.

Recommended use:

* Use RAG reports to prioritize themes for manual inspection.
* Verify all important biological claims against source literature and gene annotations.
* Do not report generated interpretation as a standalone finding without independent validation.

Prototype Models
----------------

The validated defaults are ``gemma4:e4b`` for both cluster summaries and RAG
synthesis, and ``bge-m3:latest`` for dense retrieval. Alternative models are
configurable for controlled experiments, but changing them means the execution
is no longer strictly equivalent to the reference prototype.
