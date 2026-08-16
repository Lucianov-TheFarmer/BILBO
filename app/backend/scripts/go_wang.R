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

# BILBO_WANG_PARALLEL_BEGIN

wang_cpu_fraction <- suppressWarnings(
  as.numeric(Sys.getenv("BILBO_WANG_CPU_FRACTION", "0.50"))
)

if (
  is.na(wang_cpu_fraction) ||
  !is.finite(wang_cpu_fraction) ||
  wang_cpu_fraction <= 0
) {
  wang_cpu_fraction <- 0.50
}

wang_cpu_fraction <- min(wang_cpu_fraction, 1.0)

physical_cores <- suppressWarnings(
  parallel::detectCores(logical = FALSE)
)

if (is.na(physical_cores) || physical_cores < 1) {
  physical_cores <- suppressWarnings(
    parallel::detectCores(logical = TRUE)
  )
}

if (is.na(physical_cores) || physical_cores < 1) {
  physical_cores <- 1L
}

wang_workers <- max(
  1L,
  as.integer(floor(physical_cores * wang_cpu_fraction))
)

cat(
  sprintf(
    paste0(
      "Wang: %d nucleos fisicos detectados; ",
      "usando %d processos (%.0f%%).
"
    ),
    physical_cores,
    wang_workers,
    wang_cpu_fraction * 100
  )
)
flush.console()

write_wang_matrix <- function(ontology) {
  ontology_gene2go <- gene2go[
    gene2go$ontology == ontology,
  ]

  gene_ids <- genes$gene_id[
    genes$gene_id %in% unique(ontology_gene2go$gene_id)
  ]

  gene_ids <- unique(as.character(gene_ids))
  by_gene <- split(
    ontology_gene2go$go_id,
    ontology_gene2go$gene_id
  )

  sem_data <- suppressMessages(
    GOSemSim::godata(
      ont = ontology,
      computeIC = FALSE
    )
  )

  gene_count <- length(gene_ids)

  matrix_wang <- matrix(
    0,
    nrow = gene_count,
    ncol = gene_count,
    dimnames = list(gene_ids, gene_ids)
  )

  if (gene_count > 0) {
    diag(matrix_wang) <- 1
  }

  if (gene_count > 1) {
    row_indexes <- seq_len(gene_count - 1L)
    ontology_workers <- min(
      wang_workers,
      length(row_indexes)
    )

    comparison_count <- gene_count * (gene_count - 1) / 2

    cat(
      sprintf(
        "Wang %s: %d genes, %.0f comparacoes, %d processos.
",
        ontology,
        gene_count,
        comparison_count,
        ontology_workers
      )
    )
    flush.console()

    calculate_row <- function(i) {
      column_indexes <- seq.int(
        i + 1L,
        gene_count
      )

      scores <- vapply(
        column_indexes,
        function(j) {
          go_similarity(
            by_gene[[gene_ids[[i]]]],
            by_gene[[gene_ids[[j]]]],
            sem_data
          )
        },
        numeric(1)
      )

      list(
        row = i,
        columns = column_indexes,
        scores = scores
      )
    }

    if (
      ontology_workers > 1 &&
      identical(.Platform$OS.type, "unix")
    ) {
      row_results <- parallel::mclapply(
        row_indexes,
        calculate_row,
        mc.cores = ontology_workers,
        mc.preschedule = TRUE
      )
    } else {
      row_results <- lapply(
        row_indexes,
        calculate_row
      )
    }

    for (result in row_results) {
      matrix_wang[
        result$row,
        result$columns
      ] <- result$scores

      matrix_wang[
        result$columns,
        result$row
      ] <- result$scores
    }
  } else {
    cat(
      sprintf(
        "Wang %s: nenhum par de genes para comparar.
",
        ontology
      )
    )
    flush.console()
  }

  write.csv(
    matrix_wang,
    file.path(
      features_dir,
      paste0("GO_Wang_", ontology, ".csv")
    )
  )

  cat(
    sprintf(
      "Wang %s: matriz concluida.
",
      ontology
    )
  )
  flush.console()
}

# BILBO_WANG_PARALLEL_END

wang_start <- proc.time()[["elapsed"]]
invisible(lapply(names(go_columns), write_wang_matrix))
wang_time <- proc.time()[["elapsed"]] - wang_start

update_metrics(list(
  "Number of valid GO-annotated genes" = length(unique(gene2go$gene_id)),
  "GO term validation / update time" = validation_time,
  "Wang similarity matrix time" = wang_time
))
