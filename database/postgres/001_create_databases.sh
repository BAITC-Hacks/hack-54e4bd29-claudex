#!/bin/bash
# Создание дополнительных баз при первой инициализации PostgreSQL.
#
# MLflow хранит метаданные экспериментов отдельно от операционной базы
# MedSignal: это разные жизненные циклы и разные права доступа.
set -euo pipefail

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${MLFLOW_DB_NAME:-mlflow}'
    WHERE NOT EXISTS (
        SELECT FROM pg_database WHERE datname = '${MLFLOW_DB_NAME:-mlflow}'
    )\gexec
EOSQL

echo "[medsignal] Дополнительные базы созданы"
