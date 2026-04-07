FROM continuumio/miniconda3

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    vim \
    git \
    jq \
    unzip \
    p7zip-full \
    unrar-free \
    tmux \
    htop \
    libgtk-3-0 \
    libgdk-pixbuf-xlib-2.0-0 \
    libglib2.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-tools \
    gstreamer1.0-x \
    && rm -rf /var/lib/apt/lists/*

RUN wget https://ftp-trace.ncbi.nlm.nih.gov/sra/sdk/3.1.1/sratoolkit.3.1.1-ubuntu64.tar.gz -O /tmp/sratoolkit.tar.gz \
    && tar -xzf /tmp/sratoolkit.tar.gz -C /tmp \
    && rm /tmp/sratoolkit.tar.gz \
    && mv /tmp/sratoolkit.* /usr/local/sratoolkit

ENV PATH="/usr/local/sratoolkit/bin:$PATH"

COPY config/environment.yml /app/config/environment.yml
RUN conda env create -f /app/config/environment.yml && conda clean -afy

SHELL ["conda", "run", "--no-capture-output", "-n", "bioinfo", "/bin/bash", "-c"]

COPY requirements/base.txt /app/requirements/base.txt
RUN pip install --no-cache-dir -r /app/requirements/base.txt

RUN Rscript -e "options(repos='https://cloud.r-project.org'); pkgs <- c('ggplot2','pheatmap','gplots','openxlsx','reshape2','httr','zip','Rcpp'); install.packages(pkgs)" && \
    Rscript -e "if (!require('BiocManager', quietly = TRUE)) install.packages('BiocManager', repos='https://cloud.r-project.org')" && \
    Rscript -e "BiocManager::install(c('edgeR','limma','ComplexHeatmap'), ask=FALSE, update=FALSE)"

COPY app /app

ENV PATH=/opt/conda/envs/bioinfo/bin:/app/backend/scripts:$PATH

EXPOSE 8000

CMD ["conda", "run", "--no-capture-output", "-n", "bioinfo", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
