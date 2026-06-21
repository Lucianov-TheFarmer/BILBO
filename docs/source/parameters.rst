Parameter Guide
===============

This page is the main user-facing guide to BILBO parameters. It emphasizes how choices affect downstream quantification and differential expression.

Trimmomatic Parameters
----------------------

The trimming interface exposes the main Trimmomatic operations used by ``app/backend/scripts/trimmagem.sh``.

.. list-table:: Trimming parameters
   :header-rows: 1
   :widths: 20 18 30 32

   * - Parameter
     - Current default
     - Usually appropriate when
     - Caution
   * - Threads
     - ``1``
     - Running on limited local resources or testing.
     - Increase only according to available CPU and I/O capacity.
   * - Phred encoding
     - ``autodetect``
     - Data source may be mixed or unknown.
     - Modern Illumina data are usually Phred+33. Incorrect encoding makes quality thresholds meaningless.
   * - Adapter file
     - ``TruSeq3-PE.fa``
     - Libraries were prepared with compatible Illumina TruSeq paired-end adapters.
     - Use Nextera, TruSeq single-end, or a custom FASTA when the library kit differs.
   * - Seed mismatches
     - ``2``
     - Standard Illumina adapter detection.
     - Higher values may remove more true sequence; lower values may miss adapters.
   * - Palindrome threshold
     - ``30``
     - Paired-end adapter read-through is expected.
     - Too stringent can leave adapters; too permissive can trim real sequence.
   * - Simple threshold
     - ``10``
     - Single-end or simple adapter matching.
     - Should be adjusted if post-trim FastQC still reports adapter contamination.
   * - Minimum adapter length
     - ``8``
     - Standard adapter remnants are expected.
     - Very short matches can increase false trimming.
   * - Sliding window
     - ``4:15``
     - Typical RNA-seq where low-quality 3' tails should be removed.
     - Aggressive trimming changes read length distribution and can reduce mapping across splice junctions.
   * - ``LEADING``
     - ``3``
     - Low-quality leading bases are rare or mild.
     - High values may remove informative 5' sequence.
   * - ``TRAILING``
     - ``3``
     - Low-quality trailing bases are mild.
     - If FastQC shows strong 3' decay, consider stricter sliding-window or trailing thresholds.
   * - ``CROP``
     - Empty
     - No fixed read-length truncation is needed.
     - Use only for known technical reasons; it discards all bases after the cutoff.
   * - ``HEADCROP``
     - Empty
     - No fixed 5' technical sequence is present.
     - Useful for primer/UMI remnants only when confirmed.
   * - ``MINLEN``
     - ``36``
     - Reads are sufficiently long after trimming.
     - Short-read experiments may need smaller values; long-read-like or stringent mapping workflows may need larger values.
   * - ``AVGQUAL``
     - Empty
     - Per-base trimming is sufficient.
     - Can remove whole reads and change library-size distribution.

STAR Indexing Parameters
------------------------

``sjdbOverhang`` is the most important indexing parameter exposed by the interface. It should normally be set to read length minus one. For example, use ``99`` for 100 bp reads. If multiple read lengths are present, choose the value corresponding to the longest or dominant read length, and evaluate alignment metrics carefully.

The indexing script computes a genome-size-informed ``genomeSAindexNbases`` and can receive a memory limit from the backend. Large genomes require substantial RAM and disk space.

STAR Alignment Parameters
-------------------------

BILBO passes selected optional STAR parameters as additional command-line options. These include:

.. list-table:: STAR parameters exposed by the backend model
   :header-rows: 1
   :widths: 28 72

   * - Parameter
     - Interpretation
   * - ``outFilterType``
     - Controls filtering behavior. Some settings can reduce spurious junctions but may also reduce sensitivity.
   * - ``outFilterMultimapNmax``
     - Maximum number of loci a read may map to. Lower values reduce ambiguous mapping but may remove reads from paralogs, repetitive genes, or transposable elements.
   * - ``alignSJoverhangMin``
     - Minimum overhang for unannotated splice junctions. Higher values reduce false junctions but may miss weakly supported splicing.
   * - ``alignSJDBoverhangMin``
     - Minimum overhang for annotated splice junctions. Affects sensitivity to known junctions.
   * - ``outFilterMismatchNmax``
     - Absolute maximum mismatches per pair/read.
   * - ``outFilterMismatchNoverReadLmax``
     - Maximum mismatch rate relative to read length.
   * - ``alignIntronMin`` and ``alignIntronMax``
     - Expected intron-size limits. These should reflect the organism and annotation.
   * - ``alignMatesGapMax``
     - Maximum genomic distance between paired-end mates.

Duplicate Handling
------------------

The current alignment script runs:

.. code-block:: text

   picard MarkDuplicates REMOVE_DUPLICATES=true

This setting removes duplicate reads from the final BAM.

.. warning::

   Duplicate removal is not universally appropriate for bulk RNA-seq. In RNA-seq, highly expressed genes naturally produce many reads with identical or similar coordinates, especially in deep sequencing or small transcriptomes. Removing duplicates can reduce counts for highly expressed genes and distort differential expression. It may be more appropriate for assays where duplicate molecules are clearly technical artifacts, or when UMIs or protocol-specific evidence support duplicate removal.

Until duplicate behavior is exposed as a GUI option, users should document this setting and interpret abundance estimates accordingly.

HTSeq-count Parameters
----------------------

The implemented quantification command is:

.. code-block:: text

   htseq-count -a 10 -t <feature_type> -i <id_attribute> -f bam --stranded=no <sample.bam> <annotation>

.. list-table:: Quantification parameters
   :header-rows: 1
   :widths: 22 20 58

   * - Parameter
     - Current behavior
     - Guidance
   * - ``-t`` feature type
     - User-defined.
     - Choose the annotation feature that corresponds to the biological unit to count. For gene-level analysis, ``gene`` is often appropriate in GFF/GTF files with gene features. For exon-union counting, workflows often use ``exon`` with a gene-level parent attribute, but this depends on annotation structure.
   * - ``-i`` ID attribute
     - User-defined with fallback.
     - Choose the attribute that names the intended count unit. Common examples are ``gene_id`` for GTF, ``ID`` for gene features, ``Parent`` for exon-to-gene relationships, or ``locus_tag`` for prokaryotic-style annotations.
   * - ``-a``
     - Fixed at ``10``.
     - Reads with alignment quality below 10 are not counted. This removes weak alignments but may affect repetitive regions.
   * - ``-f``
     - Fixed at ``bam``.
     - Input is the final BAM generated by BILBO.
   * - ``--stranded``
     - Fixed at ``no``.
     - Valid only for unstranded libraries. Use caution for strand-specific protocols.

Strandedness
------------

.. warning::

   The current implementation fixes ``htseq-count --stranded=no``. This is appropriate for unstranded bulk RNA-seq libraries. It is inappropriate for libraries prepared with stranded protocols, where ``yes`` or ``reverse`` may be required depending on the kit. Wrong strandedness can cause severe undercounting, antisense misassignment, and false differential expression.

Users should determine strandedness from library preparation metadata, provider documentation, or empirical tools such as RSeQC ``infer_experiment.py`` before relying on counts.

Feature and Attribute Choice
----------------------------

Feature and ID settings should be chosen by inspecting the annotation file:

* For GTF files, gene-level counting often uses ``-t exon -i gene_id``.
* For NCBI-style GFF3 files, gene-level counting may use ``-t gene -i ID`` or ``-t CDS -i Parent`` depending on the analysis goal.
* For functional interpretation of protein-coding genes, ``CDS`` or gene features linked to protein annotations may be preferred.
* For transcript-level questions, transcript features and transcript identifiers are needed, but the current edgeR workflow is primarily gene/feature-count oriented.

Changing ``-t`` and ``-i`` changes the rows in the count matrix. Therefore, it can change normalization factors, dispersion estimates, DEG calls, enrichment, clustering, and LLM interpretations.

edgeR Parameters
----------------

BILBO uses edgeR with:

* Removal of HTSeq metadata rows beginning with ``__``.
* Low-expression filtering by row mean count ``>= 10``.
* TMM normalization using ``calcNormFactors``.
* GLM common, trended, and tagwise dispersion estimation.
* ``glmFit`` followed by ``glmLRT``.
* Significant DEG export with ``FDR <= 0.05`` and ``abs(logFC) >= 1``.

These settings are reasonable for many simple replicated two-group comparisons but are not a substitute for proper design specification.
