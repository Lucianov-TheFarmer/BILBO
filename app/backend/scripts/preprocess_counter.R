if (!requireNamespace("httr", quietly = TRUE)) {
  install.packages("httr", repos = "http://cran.us.r-project.org")
}
library(httr)

Sys.sleep(3)
msg <- paste("Script R rodou com sucesso!")

# Envia mensagem para o backend emitir via WebSocket para o frontend
httr::POST(
  url = "http://localhost:8000/ws/",
  body = list(message = msg),
  encode = "form"
)
