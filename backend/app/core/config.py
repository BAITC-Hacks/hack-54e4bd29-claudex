"""Конфигурация приложения.

Все значения приходят из переменных окружения. Секретов в коде нет.

Ключевое свойство: приложение отказывается стартовать с небезопасной
конфигурацией (SECURITY.md, раздел 11). Молча запустившееся приложение
с заглушкой вместо секрета опаснее приложения, которое не запустилось.
"""

from __future__ import annotations

import sys
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import (
    Field,
    ValidationError,
    computed_field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

# Маркер, которым помечены значения из .env.example. Любой секрет,
# содержащий эту подстроку, допустим только в локальной среде.
LOCAL_ONLY_SECRET_MARKER = "local_dev_only"  # noqa: S105 — маркер, а не секрет

# Минимальная длина ключа псевдонимизации. Значение совпадает с порогом
# в data_pipeline.privacy: проверка выполняется и при старте приложения,
# и при создании конвейера, потому что оба пути ведут к записи данных.
MIN_PSEUDONYMIZATION_KEY_LENGTH = 32


class AppEnv(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_local(self) -> bool:
        return self is AppEnv.LOCAL

    @property
    def is_test(self) -> bool:
        return self is AppEnv.LOCAL


CsvString = Annotated[str, Field(description="Значения через запятую")]


def _split_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


class Settings(BaseSettings):
    """Настройки приложения, считываемые из окружения."""

    model_config = SettingsConfigDict(
        env_file=None,  # окружение подаёт Docker Compose; файл не читаем
        case_sensitive=False,
        extra="ignore",
    )

    # --- Приложение ---
    app_env: AppEnv = AppEnv.LOCAL
    app_name: str = "medsignal"
    app_version: str = "0.1.0"
    app_debug: bool = False
    app_secret: str = ""
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # --- Сеть ---
    cors_allowed_origins: CsvString = ""
    trusted_hosts: CsvString = ""
    force_https: bool = False

    # --- PostgreSQL ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "medsignal"
    postgres_user: str = "medsignal"
    postgres_password: str = ""
    postgres_sslmode: str = "prefer"
    postgres_pool_size: int = 10
    postgres_max_overflow: int = 20
    postgres_pool_timeout_s: int = 10
    postgres_statement_timeout_ms: int = 15_000
    postgres_connect_timeout_s: int = 5

    # --- ClickHouse ---
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_db: str = "medsignal_analytics"
    clickhouse_user: str = "medsignal"
    clickhouse_password: str = ""
    clickhouse_secure: bool = False
    clickhouse_connect_timeout_s: int = 5
    clickhouse_max_execution_time_s: int = 30

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db_cache: int = 0
    redis_db_broker: int = 1
    redis_db_result: int = 2
    redis_db_ratelimit: int = 3
    redis_socket_timeout_s: int = 3

    # --- Описательная аналитика (PHASE 4) ---
    analytics_min_cell_size: int = Field(default=10, ge=2, le=1000)
    analytics_cache_ttl_seconds: int = Field(default=60, ge=1, le=3600)
    analytics_max_date_range_days: int = Field(default=366, ge=1, le=3660)

    # --- Experimental short-horizon forecasting (PHASE 5A) ---
    mlflow_tracking_uri: str = "http://mlflow:5000"
    mlflow_experiment_name: str = "medsignal-referral-forecast"
    mlflow_registered_model_name: str = "medsignal-referral-flow"
    forecast_horizon_days: int = Field(default=7, ge=1, le=14)
    forecast_min_train_days: int = Field(default=42, ge=21, le=365)
    forecast_min_relative_improvement: float = Field(default=0.02, ge=0, le=1)

    # --- MinIO ---
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_secure: bool = False
    minio_bucket_imports: str = "medsignal-imports"
    minio_bucket_models: str = "medsignal-models"
    minio_bucket_exports: str = "medsignal-exports"
    minio_bucket_reports: str = "medsignal-reports"
    # Зоны хранения конвейера загрузки (PHASE 3B). Карантин и сырая зона
    # держат данные в исходном виде, поэтому доступ к ним ограничен
    # сильнее остальных бакетов.
    minio_bucket_raw: str = "medsignal-raw"
    minio_bucket_quarantine: str = "medsignal-quarantine"
    minio_bucket_quality: str = "medsignal-quality"
    minio_bucket_artifacts: str = "medsignal-artifacts"

    # --- Конвейер загрузки данных ---
    # Каталог с выгрузками. Открывается только на чтение; в контейнере
    # монтируется с флагом ro, поэтому запись невозможна физически.
    data_source_dir: str = "/data/source"
    # Размер пакета обработки. Определяет расход памяти: файл целиком
    # в память не читается никогда.
    data_batch_size: int = 50_000
    # Секрет псевдонимизации. Обычный SHA-256 от кода случая подбирается
    # перебором, поэтому применяется HMAC с этим ключом.
    data_pseudonymization_key: str = ""

    # --- Celery ---
    celery_task_soft_time_limit_s: int = 600
    celery_task_time_limit_s: int = 900

    # --- Аутентификация (ADR-0009) ---
    # OIDC_ISSUER — публичный издатель, сверяется с claim `iss`.
    # OIDC_INTERNAL_BASE_URL — внутренний адрес для загрузки ключей.
    # Смешение этих адресов ломает проверку токена.
    oidc_issuer: str = ""
    oidc_internal_base_url: str = ""
    oidc_audience: str = "medsignal-api"
    oidc_client_id: str = "medsignal-frontend"
    oidc_algorithms: CsvString = "RS256"
    oidc_jwks_cache_ttl_s: int = 300
    oidc_leeway_s: int = 10
    oidc_realm_roles_claim: str = "realm_access.roles"

    # Подставной адаптер аутентификации. Только для автоматических тестов.
    # Вне локальной среды его включение приводит к отказу старта.
    auth_test_mode: bool = False

    # --- Готовность ---
    readiness_required: CsvString = "postgres,clickhouse,redis"
    readiness_timeout_s: float = 3.0

    # --- Наблюдаемость ---
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"

    # ------------------------------------------------------------------
    # Производные значения
    # ------------------------------------------------------------------

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cors_origins(self) -> tuple[str, ...]:
        return _split_csv(self.cors_allowed_origins)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return _split_csv(self.trusted_hosts)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def jwt_algorithms(self) -> tuple[str, ...]:
        return _split_csv(self.oidc_algorithms)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def required_dependencies(self) -> tuple[str, ...]:
        return _split_csv(self.readiness_required)

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_cache_url(self) -> str:
        return self._redis_url(self.redis_db_cache)

    @property
    def celery_broker_url(self) -> str:
        return self._redis_url(self.redis_db_broker)

    @property
    def celery_result_backend(self) -> str:
        return self._redis_url(self.redis_db_result)

    def _redis_url(self, db: int) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{db}"

    @property
    def oidc_jwks_url(self) -> str:
        base = self.oidc_internal_base_url.rstrip("/")
        return f"{base}/protocol/openid-connect/certs"

    # ------------------------------------------------------------------
    # Валидация
    # ------------------------------------------------------------------

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized = value.upper()
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL должен быть одним из {sorted(allowed)}")
        return normalized

    @model_validator(mode="after")
    def _enforce_safe_configuration(self) -> Settings:
        """Отказ старта при небезопасной конфигурации.

        Проверки применяются только вне локальной среды: локальная разработка
        намеренно использует значения из .env.example.
        """
        problems: list[str] = []

        if self.app_env.is_local:
            self._check_local_completeness(problems)
        else:
            self._check_non_local_safety(problems)

        if problems:
            listing = "\n".join(f"  - {p}" for p in problems)
            raise ValueError(
                "Небезопасная или неполная конфигурация, запуск прерван:\n" + listing
            )
        return self

    def _check_local_completeness(self, problems: list[str]) -> None:
        if not self.app_secret:
            problems.append("APP_SECRET не задан")

    def _check_non_local_safety(self, problems: list[str]) -> None:
        env = self.app_env.value

        if self.app_debug:
            problems.append(f"APP_DEBUG=true недопустим при APP_ENV={env}")

        if self.log_level == "DEBUG":
            problems.append(f"LOG_LEVEL=DEBUG недопустим при APP_ENV={env}")

        if self.auth_test_mode:
            problems.append(
                f"AUTH_TEST_MODE=true недопустим при APP_ENV={env}: "
                "подставная аутентификация существует только для тестов"
            )

        if "*" in self.cors_origins:
            problems.append("CORS_ALLOWED_ORIGINS не может содержать '*'")

        if not self.cors_origins:
            problems.append("CORS_ALLOWED_ORIGINS должен быть задан явным списком")

        if not self.oidc_issuer or not self.oidc_internal_base_url:
            problems.append("OIDC_ISSUER и OIDC_INTERNAL_BASE_URL обязательны")

        if self.oidc_issuer.startswith("http://"):
            problems.append("OIDC_ISSUER должен использовать https")

        for algorithm in self.jwt_algorithms:
            if algorithm.lower() == "none" or algorithm.startswith("HS"):
                problems.append(
                    f"Алгоритм проверки токена {algorithm!r} недопустим: "
                    "разрешены только асимметричные алгоритмы"
                )

        for name, value in self._secret_fields().items():
            if not value:
                problems.append(f"{name} не задан")
            elif LOCAL_ONLY_SECRET_MARKER in value:
                problems.append(
                    f"{name} содержит значение из .env.example "
                    f"и не может использоваться при APP_ENV={env}"
                )

        # Ключ псевдонимизации проверяется отдельно и строже остальных
        # секретов. Он защищает не доступ, а обратимость: короткий ключ
        # позволяет восстановить код случая перебором, и утечка витрины
        # превращается в утечку идентификаторов пациентов.
        if (
            self.data_pseudonymization_key
            and len(self.data_pseudonymization_key) < MIN_PSEUDONYMIZATION_KEY_LENGTH
        ):
            problems.append(
                "DATA_PSEUDONYMIZATION_KEY короче "
                f"{MIN_PSEUDONYMIZATION_KEY_LENGTH} символов"
            )

    def _secret_fields(self) -> dict[str, str]:
        return {
            "APP_SECRET": self.app_secret,
            "POSTGRES_PASSWORD": self.postgres_password,
            "CLICKHOUSE_PASSWORD": self.clickhouse_password,
            "REDIS_PASSWORD": self.redis_password,
            "MINIO_ACCESS_KEY": self.minio_access_key,
            "MINIO_SECRET_KEY": self.minio_secret_key,
            "DATA_PSEUDONYMIZATION_KEY": self.data_pseudonymization_key,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Настройки приложения. Кэшируются на время жизни процесса."""
    return Settings()


def load_settings_or_exit() -> Settings:
    """Загрузка настроек с понятным сообщением вместо трассировки.

    Используется точкой входа: разработчик должен увидеть, что именно
    не так с конфигурацией, а не стену текста от pydantic.
    """
    try:
        return get_settings()
    except ValidationError as exc:  # pragma: no cover - проверяется интеграционно
        # Из обрамления pydantic извлекается только суть: разработчику
        # нужен перечень проблем, а не тип ошибки и ссылка на документацию.
        for error in exc.errors():
            message = str(error.get("msg", "")).removeprefix("Value error, ")
            print(f"[medsignal] {message}", file=sys.stderr)
        raise SystemExit(78) from exc  # EX_CONFIG
    except ValueError as exc:  # pragma: no cover
        print(f"[medsignal] {exc}", file=sys.stderr)
        raise SystemExit(78) from exc
