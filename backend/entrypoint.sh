#!/bin/sh
# Aplica as migrations pendentes antes de subir a API.
#
# Fica no entrypoint, e nao no pipeline de deploy, para que qualquer ambiente
# que suba esta imagem chegue ao schema correto sozinho. O `set -e` derruba o
# container se a migration falhar: e melhor o healthcheck acusar do que a API
# atender com o banco em schema divergente (foi assim que o RF21 quebrou em
# producao, com log_auditoria.registro_id ainda em UUID).
set -e

echo "Applying database migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
