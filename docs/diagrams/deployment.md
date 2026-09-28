# Топология развёртывания

## Локальное окружение

```mermaid
flowchart TB
    DEV["Разработчик<br/>localhost"]

    subgraph compose["Docker Compose"]
        NX["nginx :80"]
        FE["frontend"]
        API["backend"]
        WK["worker"]
        BT["beat"]
        PG[("postgres")]
        CH[("clickhouse")]
        RD[("redis")]
        S3[("minio :9001 консоль")]
        MLF["mlflow :5000"]
    end

    subgraph profile["Профиль monitoring"]
        PR["prometheus"]
        GR["grafana :3001"]
    end

    DEV --> NX --> FE & API
    API --> PG & CH & RD & S3
    BT --> RD --> WK
    WK --> PG & CH & S3 & MLF
    API -.-> PR
    WK -.-> PR
    PR --> GR
```

В локальном окружении часть портов публикуется для удобства диагностики. Конфигурация production эти публикации не наследует — это отдельный набор файлов, а не переключатель режима.

## Целевая production-топология

```mermaid
flowchart TB
    USERS["Пользователи"]

    subgraph perimeter["Периметр"]
        LB["Load Balancer / WAF<br/>TLS · фильтрация · rate limit"]
    end

    subgraph tier1["Прикладной уровень — масштабируется"]
        FE1["frontend"]
        FE2["frontend"]
        API1["backend"]
        API2["backend"]
        API3["backend"]
    end

    subgraph tier2["Уровень обработки — масштабируется по очередям"]
        WD["worker: default"]
        WI["worker: ingestion"]
        WM["worker: ml"]
        WS["worker: simulation"]
        BT["beat — один экземпляр"]
    end

    subgraph tier3["Уровень данных — приватная сеть, портов наружу нет"]
        PGM[("PostgreSQL<br/>основной")]
        PGR[("PostgreSQL<br/>реплика чтения")]
        CH[("ClickHouse")]
        RD[("Redis")]
        OS[("Объектное хранилище")]
        MLF["MLflow"]
    end

    USERS -->|HTTPS| LB
    LB --> FE1 & FE2
    LB --> API1 & API2 & API3

    API1 & API2 & API3 --> PGM
    API1 & API2 & API3 -.->|тяжёлое чтение| PGR
    API1 & API2 & API3 --> CH & RD

    BT --> RD
    RD --> WD & WI & WM & WS
    WD & WI & WM & WS --> PGM & CH & OS
    WM --> MLF --> OS
    PGM --> PGR

    style tier3 fill:#fdecea,stroke:#c0392b
```

## Правила топологии

| Правило | Причина |
|---|---|
| Публичен только балансировщик | Минимальная поверхность атаки |
| Уровень данных без публикации портов | Хранилища недоступны из Internet |
| `beat` в одном экземпляре | Иначе регулярные задачи дублируются |
| Воркеры разделены по очередям | Обучение модели не блокирует импорт и быстрые задачи |
| Миграции — отдельный шаг перед выкаткой | Исключает гонку между экземплярами |
| Приложение stateless | Экземпляры добавляются без координации |
| Ограничения ресурсов заданы | Один компонент не потребляет всё |
| Секреты из внешнего хранилища | Не файл на диске |

## Совместимость с Kubernetes

Переход не требует изменения прикладного кода:

| Compose | Kubernetes |
|---|---|
| `frontend`, `backend` | Deployment + Service + Ingress |
| `worker` | Deployment по очередям, отдельные ресурсы |
| `beat` | Deployment с одной репликой либо CronJob |
| `postgres`, `clickhouse`, `redis` | StatefulSet или управляемые сервисы |
| `minio` | Управляемое объектное хранилище |
| `nginx` | Ingress Controller |
| `.env` | Secret и ConfigMap |
| Проверки Compose | Liveness и Readiness Probe |

То, что переход не затрагивает код, — проверка корректности архитектурных границ, а не удобство инфраструктуры.
