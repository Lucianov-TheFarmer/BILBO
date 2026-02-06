# Use a imagem base com Anaconda instalada
FROM continuumio/miniconda3

# Defina o diretório de trabalho
WORKDIR /app

# Atualize e configure o ambiente base
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    wget \
    vim \
    git \
    jq \
    unzip

# Instalar dependências necessárias para o Flet
RUN apt-get install -y \
    libgtk-3-0 \
    #libgdk-pixbuf-xlib-2.0-0 \
    libglib2.0-0 \
    gstreamer1.0-plugins-base \
    gstreamer1.0-tools \
    gstreamer1.0-x

# Baixe e instale o SRA Toolkit
RUN wget https://ftp-trace.ncbi.nlm.nih.gov/sra/sdk/3.1.1/sratoolkit.3.1.1-ubuntu64.tar.gz -O sratoolkit.tar.gz && \
    tar -xzf sratoolkit.tar.gz && \
    rm sratoolkit.tar.gz && \
    mv sratoolkit.* /usr/local/sratoolkit

# Adicione o SRA Toolkit ao PATH
ENV PATH="/usr/local/sratoolkit/bin:$PATH"

# Crie o ambiente Conda para ferramentas de bioinformática
COPY config/environment.yml /app/config/environment.yml
RUN conda env create -f /app/config/environment.yml

# Ative o ambiente Conda
SHELL ["conda", "run", "-n", "bioinfo", "/bin/bash", "-c"]

# Instale FastAPI e Uvicorn
RUN pip install fastapi==0.115.11 uvicorn==0.34.0 flet==0.28.2 sqlalchemy==2.0.39 \
    psycopg2-binary==2.9.10 python-jose==3.4.0 passlib==1.7.4 python-multipart==0.0.20 \
    requests==2.32.3 websockets==15.0.1 venny4py seaborn ollama unidecode adjustText umap-learn \

RUN apt-get -y install tmux htop

RUN pip3 install RSeQC==5.0.4 openpyxl==3.1.3 pandas==2.2.3

# Instalação dos pacotes R: BiocManager, edgeR, ggplot2, pheatmap e gplots (após o ambiente conda estar pronto)
RUN Rscript -e "if (!require('BiocManager', quietly = TRUE)) install.packages('BiocManager', repos='https://cloud.r-project.org')" && \
    Rscript -e "BiocManager::install('edgeR', ask=FALSE, update=FALSE)" && \
    Rscript -e "BiocManager::install('ComplexHeatmap', ask=FALSE, update=FALSE)" && \
    Rscript -e "install.packages('ggplot2', repos='https://cloud.r-project.org')" && \
    Rscript -e "install.packages('pheatmap', repos='https://cloud.r-project.org')" && \
    Rscript -e "install.packages('gplots', repos='https://cloud.r-project.org')"

# Copie os scripts para o contêiner
COPY app /app

ENV PATH=/opt/conda/envs/bioinfo/bin:/app/backend/scripts:$PATH

# Exponha a porta que será usada pelo backend (se for necessário)
EXPOSE 8000

# Comando padrão para manter o contêiner em execução
CMD ["conda", "run", "--no-capture-output", "-n", "bioinfo", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
