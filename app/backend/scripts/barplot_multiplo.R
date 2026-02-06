args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 4) {
  cat("Erro: Argumentos insuficientes\n")
  cat("Uso: Rscript barplot_multiplo.R <deg_xlsx_path> <output_dir> <title> <contrast1> <contrast2> ...\n")
  quit(save = "no", status = 1)
}

deg_xlsx_path <- args[1]
output_dir <- args[2]
title <- args[3]
selected_contrasts <- args[4:length(args)]

cat("=== Barplot Múltiplo ===\n")
cat("DEG.xlsx:", deg_xlsx_path, "\n")
cat("Output dir:", output_dir, "\n")
cat("Title:", title, "\n")
cat("Contrasts:", paste(selected_contrasts, collapse = ", "), "\n")

# Verifica se o arquivo DEG.xlsx existe
if (!file.exists(deg_xlsx_path)) {
  cat("Erro: Arquivo DEG.xlsx não encontrado:", deg_xlsx_path, "\n")
  quit(save = "no", status = 1)
}

# Carrega bibliotecas necessárias
suppressMessages({
  if (!require(openxlsx, quietly = TRUE)) {
    install.packages("openxlsx", repos = "http://cran.us.r-project.org")
    library(openxlsx)
  }
  if (!require(ggplot2, quietly = TRUE)) {
    install.packages("ggplot2", repos = "http://cran.us.r-project.org")
    library(ggplot2)
  }
  if (!require(reshape2, quietly = TRUE)) {
    install.packages("reshape2", repos = "http://cran.us.r-project.org")
    library(reshape2)
  }
})

# Lê o arquivo DEG.xlsx
cat("Lendo arquivo DEG.xlsx...\n")
tryCatch({
  wb <- loadWorkbook(deg_xlsx_path)
  sheet_names <- names(wb)
  cat("Abas encontradas:", paste(sheet_names, collapse = ", "), "\n")
}, error = function(e) {
  cat("Erro ao carregar DEG.xlsx:", e$message, "\n")
  quit(save = "no", status = 1)
})

# Função para extrair dados de um contraste
get_contrast_data <- function(sheet_name) {
  cat("Processando aba:", sheet_name, "\n")
  if (sheet_name %in% sheet_names) {
    tryCatch({
      df <- read.xlsx(deg_xlsx_path, sheet = sheet_name)
      cat("  Colunas encontradas:", paste(colnames(df), collapse = ", "), "\n")
      if ("logFC" %in% colnames(df)) {
        up <- sum(df$logFC > 1, na.rm = TRUE)
        down <- sum(df$logFC < -1, na.rm = TRUE)
        cat("  Up-regulated:", up, "Down-regulated:", down, "\n")
        return(data.frame(
          contrast = sheet_name,
          up = up,
          down = down
        ))
      } else {
        cat("  Aviso: Coluna logFC não encontrada na aba", sheet_name, "\n")
      }
    }, error = function(e) {
      cat("  Erro ao ler aba", sheet_name, ":", e$message, "\n")
    })
  } else {
    cat("  Aviso: Aba", sheet_name, "não encontrada no arquivo\n")
  }
  return(data.frame(contrast = sheet_name, up = 0, down = 0))
}

# Coleta dados de todos os contrastes selecionados
cat("Coletando dados dos contrastes...\n")
all_data <- data.frame()
for (contrast in selected_contrasts) {
  contrast_data <- get_contrast_data(contrast)
  all_data <- rbind(all_data, contrast_data)
}

if (nrow(all_data) == 0) {
  cat("Erro: Nenhum dado foi coletado dos contrastes\n")
  quit(save = "no", status = 1)
}

cat("Dados coletados:\n")
print(all_data)

# Converte para formato longo para ggplot2
plot_data <- melt(all_data, id.vars = "contrast", variable.name = "type", value.name = "count")

# Ajusta valores para barras negativas (down-regulated)
plot_data$count[plot_data$type == "down"] <- -plot_data$count[plot_data$type == "down"]

# Define cores
colors <- c("up" = "#1976D2", "down" = "#D32F2F")

# Prepara arquivo de saída
output_file <- file.path(output_dir, paste0("BARPLOT.MULTIPLO - ", title, ".png"))
cat("Gerando gráfico:", output_file, "\n")

# Cria o gráfico
tryCatch({
  png(output_file, width = 12, height = 8, units = "in", res = 200)
  
  # Calcula o valor máximo para definir limites do eixo y
  max_val <- max(abs(plot_data$count), 1)
  
  p <- ggplot(plot_data, aes(x = contrast, y = count, fill = type)) +
    geom_bar(stat = "identity", width = 0.7, color = "black", linewidth = 0.5) +
    scale_fill_manual(values = colors, labels = c("Down-regulated", "Up-regulated")) +
    geom_hline(yintercept = 0, color = "black", linewidth = 1.2) +
    labs(x = "", y = "Number of DEGs") +
    ylim(-max_val * 1.15, max_val * 1.15) +
    theme_minimal(base_size = 16) +
    theme(
      axis.text.x = element_text(angle = 45, hjust = 1, vjust = 1, size = 14),
      axis.text.y = element_text(size = 14),
      axis.title.y = element_text(size = 18),
      legend.title = element_blank(),
      legend.position = "bottom",
      legend.text = element_text(size = 16),
      panel.grid.major.x = element_blank(),
      panel.grid.minor = element_blank(),
      axis.line = element_line(color = "black", linewidth = 0.5)
    ) +
    scale_y_continuous(labels = function(x) abs(x))
  
  # Adiciona valores nas barras
  for (i in 1:nrow(all_data)) {
    up_val <- all_data$up[i]
    down_val <- all_data$down[i]
    
    if (up_val > 0) {
      p <- p + annotate("text", x = i, y = up_val + max_val*0.04, 
                        label = up_val, 
                        hjust = 0.5, vjust = 0, size = 6, color = colors["up"], fontface = "bold")
    }
    
    if (down_val > 0) {
      p <- p + annotate("text", x = i, y = -down_val - max_val*0.04, 
                        label = down_val, 
                        hjust = 0.5, vjust = 1, size = 6, color = colors["down"], fontface = "bold")
    }
  }
  
  print(p)
  dev.off()
  
  # Verifica se o arquivo foi criado
  if (file.exists(output_file)) {
    cat("Barplot múltiplo gerado com sucesso:", output_file, "\n")
  } else {
    cat("Erro: Arquivo não foi gerado\n")
    quit(save = "no", status = 1)
  }
  
}, error = function(e) {
  cat("Erro ao gerar gráfico:", e$message, "\n")
  dev.off()
  quit(save = "no", status = 1)
})
