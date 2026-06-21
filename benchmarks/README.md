# BILBO Clustering and LLM Benchmark Helper

This directory contains a lightweight helper for measuring only the Clustering and LLM/RAG stages from an existing `DEG.xlsx` file.

The script intentionally does not benchmark download, trimming, alignment, quantification, or DEG generation. It starts from a prepared DEG workbook, writes intermediate files to temporary benchmark directories, removes generated files at the end, and preserves only the timing report.

## Example

```powershell
python benchmarks\run_clustering_llm_benchmark.py `
  --deg-xlsx C:\path\to\DEG.xlsx `
  --output benchmarks\clustering_llm_times.json
```

To benchmark only clustering:

```powershell
python benchmarks\run_clustering_llm_benchmark.py `
  --deg-xlsx C:\path\to\DEG.xlsx `
  --skip-llm `
  --output benchmarks\clustering_times.json
```

## Output

The output JSON includes:

- input workbook path;
- selected sheets;
- per-sheet clustering runtime;
- per-sheet LLM/RAG runtime, unless skipped;
- total runtime;
- success or failure status for each stage;
- error messages when a stage fails.

Intermediate cluster images, JSON files, LLM outputs, and temporary RAG bootstrap files are removed after the benchmark finishes.
