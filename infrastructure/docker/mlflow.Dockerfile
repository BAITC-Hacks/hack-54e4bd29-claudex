# MLflow с драйверами PostgreSQL и S3. Собственный минимальный runtime
# исключает EOL Debian из upstream image и проходит тот же image scan, что API.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/* \
    && pip install \
        mlflow==3.16.1 \
        GitPython==3.1.59 \
        cryptography==50.0.0 \
        boto3==1.35.* \
        psycopg2-binary==2.9.* \
    && useradd --system --uid 1001 --create-home mlflow

USER mlflow

EXPOSE 5000
