# MedSignal — исполнитель загрузки данных.
#
# Отдельный образ, а не расширение backend. Причина: конвейеру нужны
# polars и pyarrow, которые в образе API не нужны и только увеличивают
# поверхность атаки сервиса, смотрящего наружу. Обратное тоже верно —
# исполнителю загрузки не нужен uvicorn.
#
# Образ собирает и приложение, и конвейер: загрузка управляется бизнес-
# слоем (жизненный цикл импорта, аудит, отчёт о качестве), а разбор файлов
# выполняет библиотека конвейера.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/opt/medsignal/backend:/opt/medsignal

WORKDIR /opt/medsignal

RUN groupadd --system --gid 1001 medsignal \
    && useradd --system --uid 1001 --gid medsignal --create-home medsignal

COPY backend/requirements.txt backend/requirements.txt
COPY data_pipeline/requirements.txt data_pipeline/requirements.txt
RUN pip install --requirement backend/requirements.txt \
    && pip install --requirement data_pipeline/requirements.txt

COPY --chown=medsignal:medsignal backend/ backend/
COPY --chown=medsignal:medsignal data_pipeline/ data_pipeline/
# Схемы аналитического хранилища. Версионированные файлы едут в образ,
# чтобы применённая схема соответствовала установленному коду.
COPY --chown=medsignal:medsignal database/ database/

# Каталог, куда монтируется источник. Права на запись сюда не выдаются:
# монтирование выполняется с флагом ro, и попытка изменить выгрузку
# отказывается на уровне ядра, а не на уровне намерения разработчика.
RUN mkdir -p /data/source && chown medsignal:medsignal /data/source

USER medsignal

ENTRYPOINT ["python", "-m", "app.cli.data"]
CMD ["--help"]

# Явный target нужен production overlay и one-shot мигратору ClickHouse.
# Он не добавляет пакетов и наследует непривилегированного пользователя.
FROM base AS production
