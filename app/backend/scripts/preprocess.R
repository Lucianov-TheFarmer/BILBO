# Ajuste para rodar no diretório correto e ignorar gráficos de expressão gênica individuais

args <- commandArgs(trailingOnly = TRUE)
if (length(args) == 0) {
  stop("user_id deve ser passado como argumento para o script R.")
}
user_id <- args[1]
setwd(file.path("..", "users", user_id, "preprocess"))

if (!requireNamespace("httr", quietly = TRUE)) {
  install.packages("httr", repos = "http://cran.us.r-project.org")
}
library(httr)
library(edgeR)
library(ggplot2)
library(pheatmap)
library(gplots)

# Lê o arquivo Targets.txt
targets <- readTargets(fileEncoding="latin1")
names <- targets$description

matrix_input <- readDGE(targets, comment.char="!")

MetaTags <- grep("^__", rownames(matrix_input))
matrix_input <- matrix_input[-MetaTags,]

reads_before <- sum(matrix_input$counts)

rnaseqmatrix <- matrix_input$counts
rnaseqmatrix <- rnaseqmatrix[rowMeans(rnaseqmatrix) >= 10, ]
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

# Mensagem para o frontend
msg <- paste("Pré-processamento finalizado!")
httr::POST(
  url = "http://localhost:8000/ws/",
  body = list(message = msg),
  encode = "form"
)
