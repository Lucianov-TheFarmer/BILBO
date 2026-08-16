# Public SEQC test dataset

This directory documents a small, real, publicly accessible RNA-seq dataset
derived from the SEQC/MAQC-III study deposited as GEO series GSE47774.

## Included subset

The manifest contains four paired-end Illumina SRA runs:

- group A: SRR898111 and SRR898119;
- group B: SRR898143 and SRR898151.

The two runs assigned to each group provide a replicated two-group example for
exercising the RNA-seq workflow. These accessions are part of the SEQC dataset
used in the BILBO benchmark.

## Reference files

Use Ensembl GRCh38 release 112:

- FASTA: https://ftp.ensembl.org/pub/release-112/fasta/homo_sapiens/dna/Homo_sapiens.GRCh38.dna.primary_assembly.fa.gz
- GTF: https://ftp.ensembl.org/pub/release-112/gtf/homo_sapiens/Homo_sapiens.GRCh38.112.gtf.gz

## Execution in BILBO

1. Deploy BILBO according to `docs/source/installation.rst`.
2. Register the four SRA accessions listed in `seqc_test_manifest.csv`.
3. Assign SRR898111 and SRR898119 to group A.
4. Assign SRR898143 and SRR898151 to group B.
5. Select Ensembl GRCh38 release 112 as the reference.
6. Run acquisition, quality control, trimming, STAR alignment, HTSeq-count
   quantification, preprocessing, and the A-versus-B comparison.

The libraries are paired-end and unstranded. The manifest preserves the public
identifiers and experimental assignments needed to reproduce the input
selection.

## Storage

Only the manifest and instructions are versioned in GitHub. Raw reads remain
available through SRA, avoiding duplication of several gigabytes of public data.
