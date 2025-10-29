#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)

if(length(args) < 3) {
  stop("Uso: Rscript heatmap.R <contrasts_file> <deg_xlsx_path> <output_png_path> [<title>]")
}

contrasts_file <- args[1]
deg_xlsx_path <- args[2]
output_png_path <- args[3]
if(length(args) >= 4) title <- args[4] else title <- basename(contrasts_file)

# Dependências
libs <- c("readxl", "ComplexHeatmap", "grid", "graphics")
missing <- libs[!sapply(libs, requireNamespace, quietly = TRUE)]
if(length(missing) > 0) {
  stop(paste0("Pacotes R faltando: ", paste(missing, collapse=", "), ". Instale-os no container."))
}

library(readxl)
library(ComplexHeatmap)
library(grid)

# deg_xlsx_path = "/users/1/DEG/DEG_full copy.xlsx"

# Lê lista de contrastes
if(!file.exists(contrasts_file)) stop(paste("Arquivo de contrastes não encontrado:", contrasts_file))
contrasts <- readLines(contrasts_file)
contrasts <- contrasts[contrasts != ""]
if(length(contrasts) == 0) stop("Nenhum contraste encontrado no arquivo de contrastes")

# Lê planilhas e monta matriz
sheets <- excel_sheets(deg_xlsx_path)
mat_list <- list()
used <- c()
for(cname in contrasts) {
  if(!(cname %in% sheets)) {
    message(paste("Aviso: contraste", cname, "não encontrado em", deg_xlsx_path))
    next
  }
  df <- readxl::read_excel(deg_xlsx_path, sheet = cname)
  # protocolo padronizado por posição: primeira coluna = gene, segunda coluna = logFC
  col_names <- names(df)
  if(length(col_names) < 2) {
    message(paste("Erro: a aba", cname, "não tem pelo menos 2 colunas. Colunas encontradas:", paste(col_names, collapse=", ")))
    print(utils::head(df, 10))
    stop(paste("Erro: contraste", cname, "não tem duas colunas (gene, logFC)."))
  }

  gene_col <- col_names[1]
  logfc_col <- col_names[2]
  message(paste("Usando colunas por posição -> gene (col 1):", gene_col, "; logFC (col 2):", logfc_col))

  tmp <- data.frame(gene = as.character(df[[1]]),
                    logFC = as.numeric(df[[2]]),
                    stringsAsFactors = FALSE)
  names(tmp)[2] <- cname
  mat_list[[cname]] <- tmp
  used <- c(used, cname)
}

if(length(mat_list) == 0) stop("Nenhum contraste válido para gerar heatmap")

# Merge por gene
merged <- Reduce(function(x,y) merge(x,y,by='gene',all=TRUE), mat_list)
rownames(merged) <- merged$gene
merged$gene <- NULL
mat <- as.matrix(merged)
mat[is.na(mat)] <- 0

# Clustering de linhas (genes)
hc <- hclust(dist(t(mat)))

# hr <- NULL
# if(nrow(mat) > 1) {
#   # normalizar por gene se necessário? atualmente usamos valores brutos
#   # calcula linkage
#   d <- dist(mat)
#   hr <- hclust(d, method = "ward.D2")
#   # reorder matrix according to clustering
#   ord <- hr$order
#   mat <- mat[ord, , drop=FALSE]
# }

# # Ajusta tamanho do PNG
ncols <- max(1, ncol(mat))
nrows <- max(1, nrow(mat))
width_px <- max(800, ncols * 150)
height_px <- max(600, min(3000, nrows * 6))

# # Gera heatmap usando ComplexHeatmap
png(filename = output_png_path, width = width_px, height = height_px, res = 150)

Heatmap(mat,
              show_row_names = FALSE,
              cluster_columns = hc,
              column_names_gp = grid::gpar(fontsize = 8),
              column_title_rot = 90,
              name = "Log2FC",
              use_raster = TRUE)

# tryCatch({
#   draw(ht, heatmap_legend_side = "right")
# }, error = function(e) {
#   dev.off()
#   stop(e)
# })

dev.off()
cat(paste("Heatmap salvo em:", output_png_path, "\n"))

