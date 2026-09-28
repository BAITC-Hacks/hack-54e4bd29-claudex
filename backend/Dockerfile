# MedSignal backend.
# Один образ обслуживает API и воркер: это гарантирует, что бизнес-правила
# в синхронном и фоновом пути идентичны (ADR-0004).

# --- Базовый слой -----------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Обновления безопасности ОС; production healthcheck использует Python stdlib.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

# Непривилегированный пользователь. Контейнер не работает от root.
RUN groupadd --system --gid 1001 medsignal \
    && useradd --system --uid 1001 --gid medsignal --create-home medsignal

# --- Зависимости ------------------------------------------------------------
FROM base AS deps

COPY requirements.txt ./
RUN pip install --requirement requirements.txt

# --- Окружение разработки и тестов ------------------------------------------
FROM deps AS development

# Local Compose проверяет этот слой своей curl-командой.
RUN apt-get update \
    && apt-get install --no-install-recommends -y curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-dev.txt ./
RUN pip install --requirement requirements-dev.txt

COPY --chown=medsignal:medsignal . .

USER medsignal
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# --- Окружение эксплуатации -------------------------------------------------
FROM deps AS production

COPY --chown=medsignal:medsignal . .

USER medsignal
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3).close()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
