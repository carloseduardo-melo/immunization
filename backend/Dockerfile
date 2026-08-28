# Usa uma imagem oficial do Python otimizada e leve
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Define variáveis de ambiente para otimizar o Python
# PYTHONDONTWRITEBYTECODE: Impede o Python de gravar ficheiros .pyc no disco
# PYTHONUNBUFFERED: Garante que os logs do Python são enviados diretamente para o terminal (útil para o Docker)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Instala as dependências do sistema necessárias para o psycopg2 (PostgreSQL) e compilação
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        libffi-dev \
        libssl-dev \
        pkg-config \
        rustc \
        cargo \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copia apenas o ficheiro de dependências inicialmente para aproveitar o cache das camadas do Docker
COPY requirements.txt .

# Instala as bibliotecas do Python sem armazenar cache desnecessário
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# Copia o restante do código da aplicação para dentro do container
COPY . .

# Expõe a porta que o FastAPI vai utilizar
EXPOSE 8000

# Garante o bit de execucao: o repositorio e clonado tambem no Windows, que nao
# preserva permissoes de ficheiro.
RUN chmod +x /app/entrypoint.sh

# O entrypoint aplica as migrations do Alembic e so depois passa o processo
# para o Uvicorn (ver backend/entrypoint.sh).
ENTRYPOINT ["/app/entrypoint.sh"]