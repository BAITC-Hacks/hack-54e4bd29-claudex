# MLflow с драйверами, необходимыми для PostgreSQL и S3-совместимого хранилища.
# Официальный образ их не содержит, а установка при каждом старте замедляет
# запуск окружения и делает его зависимым от доступности индекса пакетов.

FROM ghcr.io/mlflow/mlflow:v2.19.0

RUN pip install --no-cache-dir \
    boto3==1.35.* \
    psycopg2-binary==2.9.* \
    && useradd --system --uid 1001 --create-home mlflow

USER mlflow

EXPOSE 5000
