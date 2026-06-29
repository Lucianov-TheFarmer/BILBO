local_library <- file.path(getwd(), ".Rlib")
if (dir.exists(local_library)) {
  .libPaths(c(local_library, .libPaths()))
}

packages <- c("GOSemSim", "GO.db", "AnnotationDbi")
missing <- packages[!vapply(packages, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing) > 0) {
  stop("Pacotes R ausentes: ", paste(missing, collapse = ", "))
}

args <- commandArgs(trailingOnly = TRUE)
input_file <- ifelse(length(args) >= 1, args[[1]], "outputs/features/genes_filtered.csv")
features_dir <- ifelse(length(args) >= 2, args[[2]], "outputs/features")
metrics_file <- ifelse(length(args) >= 3, args[[3]], "outputs/pipeline_metrics.csv")

go_columns <- c(BP = "Uniprot BP", MF = "Uniprot MF", CC = "Uniprot CC")
metric_columns <- c(
  "Dataset size",
  "Number of DEGs",
  "Number of valid GO-annotated genes",
  "GO term validation / update time",
  "Wang similarity matrix time",
  "Hierarchical clustering time",
  "Silhouette pruning time",
  "Semantic medoid selection time",
  "Total clustering time",
  "Representative genes submitted to RAG"
)

update_metrics <- function(values) {
  dir.create(dirname(metrics_file), recursive = TRUE, showWarnings = FALSE)
  if (file.exists(metrics_file) && file.info(metrics_file)$size > 0) {
    metrics <- read.csv(metrics_file, stringsAsFactors = FALSE, check.names = FALSE)
  } else {
    metrics <- as.data.frame(as.list(setNames(rep("", length(metric_columns)), metric_columns)))
  }
  if (nrow(metrics) == 0) {
    metrics <- as.data.frame(as.list(setNames(rep("", length(metric_columns)), metric_columns)))
  }
  missing_columns <- setdiff(metric_columns, names(metrics))
  for (column in missing_columns) {
    metrics[[column]] <- ""
  }
  for (name in names(values)) {
    metrics[[name]][1] <- values[[name]]
  }
  write.csv(metrics[1, metric_columns], metrics_file, row.names = FALSE, na = "")
}

genes <- read.csv(input_file, stringsAsFactors = FALSE, check.names = FALSE)
dir.create(features_dir, recursive = TRUE, showWarnings = FALSE)

extract_go <- function(annotation) {
  annotation <- ifelse(is.na(annotation), "", annotation)
  matches <- gregexpr("GO:\\d+", annotation)
  regmatches(annotation, matches)
}

gene2go <- do.call(rbind, lapply(names(go_columns), function(ontology) {
  terms_by_gene <- extract_go(genes[[go_columns[[ontology]]]])
  rows <- lapply(seq_along(terms_by_gene), function(index) {
    terms <- unique(terms_by_gene[[index]])
    if (length(terms) == 0) {
      return(NULL)
    }
    data.frame(
      gene_id = genes$gene_id[[index]],
      ontology = ontology,
      go_id = terms,
      stringsAsFactors = FALSE
    )
  })
  do.call(rbind, rows)
}))
if (is.null(gene2go)) {
  gene2go <- data.frame(
    gene_id = character(0),
    ontology = character(0),
    go_id = character(0),
    stringsAsFactors = FALSE
  )
} else {
  gene2go <- unique(gene2go)
}

validation_start <- proc.time()[["elapsed"]]
valid_go <- AnnotationDbi::keys(GO.db::GO.db, keytype = "GOID")
invalid_go <- gene2go[!gene2go$go_id %in% valid_go, ]
invalid_file <- file.path(features_dir, "invalid_go_annotations.csv")

if (nrow(invalid_go) > 0) {
  write.csv(invalid_go, invalid_file, row.names = FALSE)
  gene2go <- gene2go[gene2go$go_id %in% valid_go, ]
} else if (file.exists(invalid_file)) {
  file.remove(invalid_file)
}
validation_time <- proc.time()[["elapsed"]] - validation_start

go_similarity <- function(terms_a, terms_b, sem_data) {
  if (length(terms_a) == 0 || length(terms_b) == 0) {
    return(0)
  }
  score <- GOSemSim::mgoSim(
    terms_a,
    terms_b,
    semData = sem_data,
    measure = "Wang",
    combine = "BMA"
  )
  ifelse(is.na(score), 0, score)
}

write_wang_matrix <- function(ontology) {
  ontology_gene2go <- gene2go[gene2go$ontology == ontology, ]
  gene_ids <- genes$gene_id[genes$gene_id %in% unique(ontology_gene2go$gene_id)]
  gene_ids <- unique(as.character(gene_ids))
  by_gene <- split(ontology_gene2go$go_id, ontology_gene2go$gene_id)
  sem_data <- suppressMessages(GOSemSim::godata(ont = ontology, computeIC = FALSE))
  matrix_wang <- matrix(
    0,
    nrow = length(gene_ids),
    ncol = length(gene_ids),
    dimnames = list(gene_ids, gene_ids)
  )
  if (length(gene_ids) > 0) {
    diag(matrix_wang) <- 1
  }

  if (length(gene_ids) > 1) {
    for (i in seq_len(length(gene_ids) - 1)) {
      for (j in seq.int(i + 1, length(gene_ids))) {
        score <- go_similarity(by_gene[[gene_ids[[i]]]], by_gene[[gene_ids[[j]]]], sem_data)
        matrix_wang[i, j] <- score
        matrix_wang[j, i] <- score
      }
    }
  }

  write.csv(matrix_wang, file.path(features_dir, paste0("GO_Wang_", ontology, ".csv")))
}

wang_start <- proc.time()[["elapsed"]]
invisible(lapply(names(go_columns), write_wang_matrix))
wang_time <- proc.time()[["elapsed"]] - wang_start

update_metrics(list(
  "Number of valid GO-annotated genes" = length(unique(gene2go$gene_id)),
  "GO term validation / update time" = validation_time,
  "Wang similarity matrix time" = wang_time
))
