# Ajuste para rodar no diretório correto e ignorar gráficos de expressão gênica individuais

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 0) {
  stop("user_id deve ser passado como argumento para o script R.")
}
user_id <- args[1]

# Determine script directory robustly even when invoked via Rscript from any cwd
cmd_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("--file=", cmd_args, value = TRUE)
if (length(file_arg) > 0) {
  script_path <- sub("^--file=", "", file_arg[1])
  script_dir <- normalizePath(dirname(script_path))
  project_root <- normalizePath(file.path(script_dir, "..", "..", ".."))
  target_preprocess_dir <- file.path(project_root, "users", user_id, "preprocess")
} else {
  # Fallback: assume current working directory is project root or similar
  target_preprocess_dir <- file.path("..", "users", user_id, "preprocess")
}

setwd(target_preprocess_dir)

library(edgeR)
library(ggplot2)
library(pheatmap)
library(gplots)

# Lê o arquivo Targets.txt
targets <- readTargets(fileEncoding="latin1")
names <- targets$description

# Debug prints: working dir and Targets.txt content
cat("[DEBUG] Working directory:", getwd(), "\n")
targets_path <- file.path(getwd(), "Targets.txt")
cat("[DEBUG] Targets.txt path:", targets_path, "exists=", file.exists(targets_path), "\n")
if (file.exists(targets_path)) {
  cat("[DEBUG] Targets.txt content:\n")
  try({
    tlines <- readLines(targets_path, encoding = "UTF-8")
    cat(paste0(tlines, collapse = "\n"), "\n")
  }, silent = TRUE)
}

# Debug: list files and check existence
if (!is.null(targets$files)) {
  cat("[DEBUG] Targets files:\n")
  print(as.character(targets$files))
  cat("[DEBUG] Files exist?\n")
  print(sapply(as.character(targets$files), function(f) file.exists(f)))
}

# Wrap readDGE with tryCatch to capture and print diagnostics on error
matrix_input <- tryCatch({
  readDGE(targets, comment.char="!")
}, error = function(e) {
  cat("[ERROR] readDGE failed:\n")
  cat(conditionMessage(e), "\n")
  cat("[DEBUG] targets object:\n")
  try(print(targets), silent = TRUE)
  cat("[DEBUG] files existence:\n")
  try(print(sapply(as.character(targets$files), function(f) file.exists(f))), silent = TRUE)
  stop(e)
})

cat("[DEBUG] readDGE succeeded. Class:", paste(class(matrix_input), collapse=","), "\n")
if (!is.null(matrix_input$counts)) {
  cat("[DEBUG] counts dim:", paste(dim(matrix_input$counts), collapse = " x "), "\n")
} else {
  cat("[DEBUG] matrix_input$counts is NULL\n")
}

## Safely remove meta-tag rows (rows starting with '__') if present.
## Use rownames(matrix_input$counts) to avoid subsetting the DGEList incorrectly
if (!is.null(matrix_input$counts)) {
  rn <- rownames(matrix_input$counts)
  if (!is.null(rn)) {
    MetaTags <- grep("^__", rn)
    if (length(MetaTags) > 0) {
      keep <- setdiff(seq_len(nrow(matrix_input$counts)), MetaTags)
      matrix_input$counts <- matrix_input$counts[keep, , drop = FALSE]
      if (!is.null(matrix_input$genes)) {
        # keep genes frame in sync if present
        matrix_input$genes <- matrix_input$genes[keep, , drop = FALSE]
      }
      cat("[DEBUG] Removed", length(MetaTags), "MetaTags rows from counts\n")
    } else {
      cat("[DEBUG] No MetaTags rows found; skipping removal\n")
    }
  } else {
    cat("[DEBUG] No rownames in matrix_input$counts; skipping MetaTags removal\n")
  }
} else {
  cat("[DEBUG] matrix_input$counts is NULL; skipping MetaTags removal\n")
}

reads_before <- sum(matrix_input$counts)

rnaseqmatrix <- matrix_input$counts

# Compute row means and filter low-expression genes
row_means <- tryCatch({
  rowMeans(rnaseqmatrix)
}, error = function(e) {
  cat("[ERROR] rowMeans failed:", conditionMessage(e), "\n")
  stop(e)
})
cat("[DEBUG] rowMeans summary:", paste(capture.output(summary(row_means)), collapse = " | "), "\n")
keep <- which(row_means >= 10)
cat("[DEBUG] number of genes before filter:", nrow(rnaseqmatrix), "\n")
cat("[DEBUG] number of genes after >=10 filter:", length(keep), "\n")
if (length(keep) == 0) {
  cat("[WARN] Filtering removed all genes; falling back to unfiltered counts.\n")
  rnaseqmatrix <- matrix_input$counts
} else {
  rnaseqmatrix <- rnaseqmatrix[keep, , drop = FALSE]
}

conditions = matrix_input$samples[,2]

analysis_matrix <- DGEList(counts = rnaseqmatrix, group = conditions)
colnames(analysis_matrix$counts) <- names

design <- model.matrix(~0+group, data=analysis_matrix$samples)
colnames(design) <- levels(analysis_matrix$samples$group)

analysis_matrix <- calcNormFactors(analysis_matrix)

analysis_matrix <- estimateGLMCommonDisp(analysis_matrix, design)
analysis_matrix <- estimateGLMTrendedDisp(analysis_matrix, design)
analysis_matrix <- estimateGLMTagwiseDisp(analysis_matrix, design)

fit <- glmFit(analysis_matrix,design)

normalized.cpm.matrix <- cpm(analysis_matrix,normalized.lib.sizes=T)
colnames(normalized.cpm.matrix) <- names

# Função auxiliar para salvar PNG com 300 dpi
save_png <- function(filename, width=12, height=8, expr) {
  png(filename, width=width, height=height, units="in", res=300)
  on.exit(dev.off())
  force(expr)
}

# Libraries size barplot usando ggplot2 para melhor estética e robustez
save_png("libraries_sizes.png", width=12, height=8, expr={
  library(ggplot2)
  lib_sizes <- data.frame(
    Sample = rownames(fit$samples),
    Size = fit$samples$lib.size
  )
  # Ordena por tamanho para melhor visualização
  lib_sizes$Sample <- factor(lib_sizes$Sample, levels = lib_sizes$Sample[order(lib_sizes$Size, decreasing = TRUE)])
  mean_size <- mean(lib_sizes$Size)
  sd_size <- sd(lib_sizes$Size)
  gg <- ggplot(lib_sizes, aes(x=Sample, y=Size, fill=Size)) +
    geom_bar(stat="identity", color="black", width=0.7) +
    scale_fill_gradient(low="skyblue", high="navy") +
    geom_hline(yintercept=mean_size, linetype="dashed", color="red", size=1) +
    geom_hline(yintercept=mean_size-2*sd_size, linetype="solid", color="black", size=1) +
    labs(title="Library Sizes", y="Library size", x="Sample") +
    theme_minimal(base_size=18) +
    theme(
      axis.text.x = element_text(angle=60, hjust=1, vjust=1, size=ifelse(nrow(lib_sizes) > 20, 8, 12)),
      plot.title = element_text(hjust=0.5)
    )
  print(gg)
})

# BCV plot
save_png("edgeR_BCV.png", width=12, height=8, expr={
  plotBCV(analysis_matrix, main="Biological Coefficient of Variation")
})

# MDS plot
save_png("edgeR_MDS.png", width=12, height=8, expr={
  plotMDS(analysis_matrix, main="MDS Plot")
})

cpm.matrix <- cpm(analysis_matrix,normalized.lib.sizes=TRUE)
colnames(cpm.matrix) <- names
t.cpm.matrix <- t(cpm.matrix)
sampleTree <- hclust(dist(t.cpm.matrix), method = "average");

# Sample clustering dendrogram
save_png("sampleClustering.png", width=12, height=8, expr={
  par(cex = 0.6)
  par(mar = c(0,4,2,0))
  plot(
    hclust(dist(t(cpm.matrix)), method = "average"),
    main = "Sample clustering to detect outliers",
    sub="", xlab="", cex.lab = 1.5,
    cex.axis = 1.5, cex.main = 2
  )
})

# Densities plots
save_png("Densities_input.png", width=12, height=8, expr={
  plotDensities(log(matrix_input$counts), legend = "topright", main="Density - Raw Counts")
})
save_png("Densities_low_expression_filter.png", width=12, height=8, expr={
  plotDensities(log(rnaseqmatrix), legend = "topright", main="Density - Filtered Counts")
})
save_png("Densities_normalization.png", width=12, height=8, expr={
  plotDensities(log(cpm.matrix), legend = "topright", main="Density - Normalized CPM")
})
save_png("Densities_log_cpm_fitted_norm.png", width=12, height=8, expr={
  plotDensities(log(cpm(fit$fitted.values, normalized.lib.sizes=TRUE)), legend = "topright", main="Density - Fitted Normalized CPM")
})

# Histogram plots
save_png("Log10_histogram_normalized.png", width=12, height=8, expr={
  hist(log(cpm.matrix+1,10), col=gray.colors(19, start = 0.9, end = 0.3), main="Histogram log10(CPM+1)", xlab="log10(CPM+1)")
})
save_png("Log2_histogram_normalized.png", width=12, height=8, expr={
  hist(log(cpm.matrix+1,2), col=gray.colors(19, start = 0.9, end = 0.3), main="Histogram log2(CPM+1)", xlab="log2(CPM+1)")
})
save_png("histogram_normalized.png", width=12, height=8, expr={
  hist(cpm.matrix, col=gray.colors(19, start = 0.9, end = 0.3), main="Histogram CPM", xlab="CPM")
})

# Heatmap (pheatmap) - fonte maior, quadrados menores para harmonizar visual
heatmap_width <- max(12, min(2 + 0.4 * ncol(cpm.matrix)))
heatmap_height <- max(8, min(2 + 0.3 * ncol(cpm.matrix)))
save_png("sampleClusteringHeatmap.png", width=heatmap_width, height=heatmap_height, expr={
  pheatmap(
    cor(cpm.matrix, method="spearman", use="pairwise.complete.obs"),
    fontsize=14, # fonte maior e harmoniosa
    angle_col=45,
    legend=T,
    main="Sample Correlation Heatmap",
    cellwidth=18,  # quadrados menores
    cellheight=18
  )
})

# Não gera gráficos de expressão gênica individuais
