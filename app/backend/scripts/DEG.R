args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("Os caminhos dos diretórios preprocess e DEG devem ser passados como argumentos para o script R.")
}
preprocess_dir <- args[1]
deg_dir <- args[2]
setwd(preprocess_dir)

# Abrir arquivo de log para escrita
log_file <- file("DEG_R.log", open = "wt")
logmsg <- function(msg) {
  timestamp <- format(Sys.time(), "%Y-%m-%d %H:%M:%S")
  cat(sprintf("[%s] %s\n", timestamp, msg))
  writeLines(sprintf("[%s] %s", timestamp, msg), log_file)
  flush(log_file)
}

# Redirecionar saída padrão e de erro para o arquivo de log
sink(log_file, append = TRUE, type = "output")
sink(log_file, append = TRUE, type = "message")

logmsg("Iniciando DEG.R")

if (!requireNamespace("openxlsx", quietly = TRUE)) {
  install.packages("openxlsx", repos = "http://cran.us.r-project.org")
}
library(openxlsx)
library(edgeR)
library(httr)
library(gplots)

logmsg("Lendo Targets.txt")
targets <- readTargets(fileEncoding="latin1")
names <- targets$description

logmsg("Lendo matriz de contagem")
matrix_input <- readDGE(targets, comment.char="!")
MetaTags <- grep("^__", rownames(matrix_input))
matrix_input <- matrix_input[-MetaTags,]

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

selected_contrasts_file <- file.path(getwd(), "selected_contrasts.txt")
selected_contrast_ids <- NULL
if (file.exists(selected_contrasts_file)) {
  selected_contrast_ids <- as.integer(readLines(selected_contrasts_file))
}

logmsg("Obtendo contrastes do Targets.txt")
# Ordena os grupos alfabeticamente para garantir consistência dos contrastes
contrasts <- sort(unique(as.character(targets$group)))

# Buscar apenas os contrastes selecionados pelo usuário
all_contrasts <- list()
if (!is.null(selected_contrast_ids)) {
  # Lê o arquivo de contrastes definidos no banco (SampleStage)
  contrast_db_file <- file.path(getwd(), "contrasts_db.txt")
  if (file.exists(contrast_db_file)) {
    contrast_db <- read.table(contrast_db_file, header=TRUE, sep="\t", stringsAsFactors=FALSE)
    selected_contrasts <- contrast_db[contrast_db$id %in% selected_contrast_ids, ]
    for (i in seq_len(nrow(selected_contrasts))) {
      left <- selected_contrasts$name[i]
      if (grepl("\\*", left)) {
        all_contrasts[[length(all_contrasts)+1]] <- left
      }
    }
  } else {
    stop("Arquivo contrasts_db.txt não encontrado.")
  }
} else {
  # fallback: processa todos os contrastes possíveis
  contrast_pairs <- combn(contrasts, 2, simplify=FALSE)
}

# Função para truncar e garantir unicidade dos nomes das abas
make_sheet_name <- function(name, used_names) {
  # Remove caracteres não permitidos e limita a 31 caracteres
  clean_name <- gsub("[\\[\\]\\*\\?/]", "_", name)
  if (nchar(clean_name) > 31) {
    clean_name <- substr(clean_name, 1, 31)
  }
  # Garante unicidade
  orig_name <- clean_name
  i <- 1
  while (clean_name %in% used_names) {
    suffix <- paste0("_", i)
    max_len <- 31 - nchar(suffix)
    clean_name <- paste0(substr(orig_name, 1, max_len), suffix)
    i <- i + 1
  }
  return(clean_name)
}

wb <- createWorkbook()
used_sheet_names <- character(0)

if (length(all_contrasts) > 0) {
  for (contrast_str in all_contrasts) {
    # Parse group names
    left_right <- strsplit(contrast_str, "\\*")[[1]]
    group1 <- sub("\\(.*", "", left_right[1])
    group2 <- sub("\\(.*", "", left_right[2])
    group1 <- trimws(group1)
    group2 <- trimws(group2)
    logmsg(sprintf("Processando contraste: %s vs %s", group1, group2))
    contrast_vector <- rep(0, length(contrasts))  # <-- Adicione esta linha antes de logar e usar
    contrast_vector[which(contrasts == group1)] <- 1
    contrast_vector[which(contrasts == group2)] <- -1
    logmsg(sprintf("Parâmetro contrast_vector: %s", paste(contrast_vector, collapse = ",")))
    logmsg(sprintf("Executando: lrt <- glmLRT(fit, contrast=contrast_vector)"))
    lrt <- glmLRT(fit, contrast=contrast_vector)
    logmsg("Executando: tt <- topTags(lrt, n=NULL)")
    tt <- topTags(lrt, n=NULL)
    logmsg("Executando: keep_sig <- tt$table$FDR <= 0.05 & abs(tt$table$logFC) >= 1")
    keep_sig <- tt$table$FDR <= 0.05 & abs(tt$table$logFC) >= 1
    logmsg("Executando: sig_genes <- tt$table[keep_sig, ]")
    sig_genes <- tt$table[keep_sig, ]
    sheet_name <- make_sheet_name(paste0(group1, "_vs_", group2), used_sheet_names)
    used_sheet_names <- c(used_sheet_names, sheet_name)
    addWorksheet(wb, sheet_name)
    writeData(wb, sheet_name, sig_genes, rowNames=TRUE)
    logmsg(sprintf("Contraste %s: %d genes DEG encontrados", sheet_name, nrow(sig_genes)))
  }
} else {
  for (pair in contrast_pairs) {
    group1 <- pair[1]
    group2 <- pair[2]
    logmsg(sprintf("Processando contraste: %s vs %s", group1, group2))
    contrast_vector <- rep(0, length(contrasts))
    contrast_vector[which(contrasts == group1)] <- 1
    contrast_vector[which(contrasts == group2)] <- -1
    logmsg(sprintf("Parâmetro contrast_vector: %s", paste(contrast_vector, collapse = ",")))
    logmsg(sprintf("Executando: lrt <- glmLRT(fit, contrast=contrast_vector)"))
    lrt <- glmLRT(fit, contrast=contrast_vector)
    logmsg("Executando: tt <- topTags(lrt, n=NULL)")
    tt <- topTags(lrt, n=NULL)
    logmsg("Executando: keep_sig <- tt$table$FDR <= 0.05 & abs(tt$table$logFC) >= 1")
    keep_sig <- tt$table$FDR <= 0.05 & abs(tt$table$logFC) >= 1
    logmsg("Executando: sig_genes <- tt$table[keep_sig, ]")
    sig_genes <- tt$table[keep_sig, ]
    # Use a função para garantir nome válido
    sheet_name <- make_sheet_name(paste0(group1, "_vs_", group2), used_sheet_names)
    used_sheet_names <- c(used_sheet_names, sheet_name)
    addWorksheet(wb, sheet_name)
    writeData(wb, sheet_name, sig_genes, rowNames=TRUE)
    logmsg(sprintf("Contraste %s: %d genes DEG encontrados", sheet_name, nrow(sig_genes)))
  }
}

# Salvar o arquivo DEG.xlsx no diretório DEG
saveWorkbook(wb, file.path(deg_dir, "DEG.xlsx"), overwrite=TRUE)
logmsg("Arquivo DEG.xlsx salvo com sucesso.")

# Agora criar uma segunda planilha com TODOS os genes (DEG_full.xlsx)
logmsg("Criando DEG_full.xlsx com todos os genes")
wb_full <- createWorkbook()
used_sheet_names_full <- character(0)

if (length(all_contrasts) > 0) {
  for (contrast_str in all_contrasts) {
    # Parse group names
    left_right <- strsplit(contrast_str, "\\*")[[1]]
    group1 <- sub("\\(.*", "", left_right[1])
    group2 <- sub("\\(.*", "", left_right[2])
    group1 <- trimws(group1)
    group2 <- trimws(group2)
    logmsg(sprintf("Processando contraste FULL: %s vs %s", group1, group2))
    contrast_vector <- rep(0, length(contrasts))
    contrast_vector[which(contrasts == group1)] <- 1
    contrast_vector[which(contrasts == group2)] <- -1
    lrt <- glmLRT(fit, contrast=contrast_vector)
    tt <- topTags(lrt, n=NULL)
    # SEM FILTRO - todos os genes
    all_genes <- tt$table
    sheet_name <- make_sheet_name(paste0(group1, "_vs_", group2), used_sheet_names_full)
    used_sheet_names_full <- c(used_sheet_names_full, sheet_name)
    addWorksheet(wb_full, sheet_name)
    writeData(wb_full, sheet_name, all_genes, rowNames=TRUE)
    logmsg(sprintf("Contraste FULL %s: %d genes totais", sheet_name, nrow(all_genes)))
  }
} else {
  for (pair in contrast_pairs) {
    group1 <- pair[1]
    group2 <- pair[2]
    logmsg(sprintf("Processando contraste FULL: %s vs %s", group1, group2))
    contrast_vector <- rep(0, length(contrasts))
    contrast_vector[which(contrasts == group1)] <- 1
    contrast_vector[which(contrasts == group2)] <- -1
    lrt <- glmLRT(fit, contrast=contrast_vector)
    tt <- topTags(lrt, n=NULL)
    # SEM FILTRO - todos os genes
    all_genes <- tt$table
    sheet_name <- make_sheet_name(paste0(group1, "_vs_", group2), used_sheet_names_full)
    used_sheet_names_full <- c(used_sheet_names_full, sheet_name)
    addWorksheet(wb_full, sheet_name)
    writeData(wb_full, sheet_name, all_genes, rowNames=TRUE)
    logmsg(sprintf("Contraste FULL %s: %d genes totais", sheet_name, nrow(all_genes)))
  }
}

# Salvar o arquivo DEG_full.xlsx no diretório DEG
saveWorkbook(wb_full, file.path(deg_dir, "DEG_full.xlsx"), overwrite=TRUE)
logmsg("Arquivo DEG_full.xlsx salvo com sucesso.")

# Fechar o arquivo de log e restaurar saída padrão
sink(type = "output")
sink(type = "message")
close(log_file)
