# ML worker/runner image. The API image intentionally excludes these libraries.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/opt/medsignal/backend:/opt/medsignal

# Apply security updates from the selected Debian snapshot before installing
# Python dependencies. The final image is scanned and recorded by digest.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system --gid 10001 medsignal \
    && useradd --system --uid 10001 --gid medsignal --create-home medsignal

WORKDIR /opt/medsignal

COPY backend/requirements.txt /tmp/backend-requirements.txt
COPY ml/requirements.txt /tmp/ml-requirements.txt
RUN pip install --requirement /tmp/backend-requirements.txt \
    && pip install --requirement /tmp/ml-requirements.txt

COPY --chown=medsignal:medsignal backend/ backend/
COPY --chown=medsignal:medsignal ml/ ml/

WORKDIR /opt/medsignal/backend

USER medsignal

FROM base AS development
USER root
COPY backend/requirements.txt /tmp/requirements.txt
COPY backend/requirements-dev.txt /tmp/backend-dev-requirements.txt
RUN pip install --requirement /tmp/backend-dev-requirements.txt
USER medsignal

FROM base AS production
