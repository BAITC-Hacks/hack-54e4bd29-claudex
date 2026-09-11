# Конвейер машинного обучения

> Целевая переменная не выбрана до завершения Data Audit ([ADR-0007](../ADR/0007-data-audit-before-ml-target.md)). Диаграмма описывает метод, а не конкретную модель.

## Обучение и приёмка

```mermaid
flowchart TB
    DA["Data Audit<br/>что реально есть в данных"]
    TGT{"Проверяемая цель<br/>реализуема?"}
    STOP["ML-часть не реализуется.<br/>Signal Engine работает<br/>на правилах и статистике"]

    SRC[("Канонические данные<br/>ClickHouse")]
    FIT{"История достаточна<br/>и непрерывна?"}
    SKIP["Организация исключена<br/>причина сохранена"]

    FEAT["Признаки<br/>лаги · окна · календарь · профиль"]
    LEAK["Проверка доступности<br/>признаков во времени"]
    SPLIT["Временное разбиение<br/>расширяющееся окно + разрыв"]

    BASE["Baseline<br/>last value · moving average<br/>seasonal naive"]
    MODEL["ML-модель"]
    EVAL["Оценка на одном<br/>и том же разбиении"]

    GATE{"Модель устойчиво<br/>лучше baseline?"}
    USEBASE["Публикуется baseline"]
    ACC{"Пройдены критерии<br/>приёмки?"}
    REG["MLflow<br/>регистрация версии"]
    PUB["Публикация решением человека"]

    DA --> TGT
    TGT -->|нет| STOP
    TGT -->|да| SRC --> FIT
    FIT -->|нет| SKIP
    FIT -->|да| FEAT --> LEAK --> SPLIT
    SPLIT --> BASE --> EVAL
    SPLIT --> MODEL --> EVAL --> GATE
    GATE -->|нет| USEBASE
    GATE -->|да| ACC
    ACC -->|нет| USEBASE
    ACC -->|да| REG --> PUB

    style STOP fill:#fdecea,stroke:#c0392b
    style PUB fill:#e9f7ef,stroke:#3d8b5f,stroke-width:2px
```

Публикация модели — явное решение человека, а не следствие лучшей метрики. Автоматическая публикация означала бы, что поведение системы меняется без чьего-либо ведома.

## Временное разбиение

```mermaid
flowchart LR
    subgraph F1["Разбиение 1"]
        direction LR
        A1["train"] -->|разрыв = горизонт| B1["test"]
    end
    subgraph F2["Разбиение 2"]
        direction LR
        A2["train"] -->|разрыв| B2["test"]
    end
    subgraph F3["Разбиение 3"]
        direction LR
        A3["train"] -->|разрыв| B3["test"]
    end
    F1 --> F2 --> F3
```

Случайное разбиение запрещено. Разрыв между обучением и проверкой равен горизонту прогноза и исключает перетекание информации. Для панельных данных разбиение выполняется по времени, а не по организациям.

## Инференс и объяснение

```mermaid
sequenceDiagram
    participant BT as Beat
    participant W as Worker
    participant FS as ForecastService
    participant PORT as ForecastPort
    participant ML as ml.inference
    participant MLF as MLflow
    participant CH as ClickHouse
    participant ES as ExplanationService

    BT->>W: ежедневный прогон
    W->>FS: построить прогнозы
    FS->>CH: признаки за окно
    FS->>PORT: predict(...)
    PORT->>ML: вызов реализации
    ML->>MLF: активная версия модели
    ML-->>PORT: значение · неопределённость · вклады
    PORT-->>FS: ForecastResult
    FS->>FS: проверка валидности<br/>сравнение с baseline
    alt невалиден
        FS->>CH: сохранить с признаком невалидности
        Note over FS: исключается из Risk Score<br/>и из ML-источника сигналов
    else валиден
        FS->>ES: вклады признаков
        ES-->>FS: человекочитаемое объяснение
        FS->>CH: сохранить прогноз и объяснение
    end
```

Бизнес-слой обращается к ML только через `ForecastPort` и не импортирует код `ml` ([ADR-0005](../ADR/0005-ml-separation.md)). Сырой вывод SHAP преобразуется `ExplanationService` и в интерфейс не попадает.

## Обязательные атрибуты результата

| Поле | Без него прогноз не отображается |
|---|---|
| `predicted_value`, `horizon` | Да |
| `model_version` | Да |
| `uncertainty` | Да, где применимо |
| `error_metric`, `baseline_error_metric` | Да |
| `generated_at`, `input_period` | Да |
| `explanation`, `assumptions` | Да |
| `is_valid`, `invalidity_reason` | Да |
