# Usa uma imagem oficial do Python otimizada e leve
FROM python:3.11-slim

# Define o diretório de trabalho dentro do container
WORKDIR /app

# Define variáveis de ambiente para otimizar o Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Copia o ficheiro de dependências
COPY requirements.txt .

# Instala as bibliotecas do Python sem armazenar cache desnecessário
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copia o restante do código da aplicação (como o app.py)
COPY . .

# Expõe a porta padrão que o Streamlit utiliza
EXPOSE 8501

# Cria um ficheiro de configuração (opcional) para o Streamlit rodar de forma headless e sem avisos no terminal
RUN mkdir -p ~/.streamlit \
    && echo "[server]\nheadless = true\nport = 8501\nenableCORS = false\n" > ~/.streamlit/config.toml

# Comando para iniciar a aplicação Web
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]