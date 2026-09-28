"""Контракты четырёх наборов данных MedSignal Case 1.

Каждый столбец и каждая доля пропусков взяты из отчёта PHASE 3A
(`docs/data/SCHEMA_CATALOG.md`, `data/audit/medsignal_audit_summary.json`).
Здесь нет ни одного поля, которого не подтвердил аудит.

Наборы, не относящиеся к задаче — вакцинации, отказы от вакцинации,
онкологические выгрузки, — в реестре отсутствуют, и загрузить их
невозможно. Реестр является разрешающим списком, а не подсказкой:
«загрузить всё, что лежит в каталоге» — это способ втянуть в систему
104 миллиона записей о вакцинации, не имеющих отношения к очереди
на госпитализацию.
"""

from __future__ import annotations

from data_pipeline.contracts.base import (
    ColumnKind,
    ColumnSpec,
    DatasetContract,
    Nullability,
)

REFERRALS = "REFERRALS"
WAITING = "WAITING"
REFUSALS = "REFUSALS"
TREATED = "TREATED"

SOURCE_IS_BG = "ИС БГ"
SOURCE_ERSB = "ЭРСБ"


def _s(
    name: str,
    kind: ColumnKind,
    nullability: Nullability,
    description: str,
    audit_null_pct: float | None = None,
    conditional_reason: str | None = None,
) -> ColumnSpec:
    return ColumnSpec(
        name=name,
        kind=kind,
        nullability=nullability,
        description=description,
        audit_null_pct=audit_null_pct,
        conditional_reason=conditional_reason,
    )


REFERRALS_CONTRACT = DatasetContract(
    key=REFERRALS,
    title="Направления на плановую госпитализацию в стационары",
    source_system=SOURCE_IS_BG,
    source_directory="Направления на плановую госпитализацию в стационары",
    file_glob="*.csv",
    target_table="fact_referral_events",
    staging_table="stg_fact_referral_events",
    forbidden_in_analytics=frozenset({"hospitalization_code", "diagnosis_name"}),
    audit_row_count=767_130,
    columns=(
        _s(
            "hospitalization_code",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Составной код случая: регион, организация, профиль, номер пациента",
            0.0,
        ),
        _s(
            "referring_mo",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Направляющая организация, полное юридическое наименование",
            0.0,
        ),
        _s(
            "hospital_mo",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Принимающая организация, полное юридическое наименование",
            0.0,
        ),
        _s(
            "icd10_ref_diag_code",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Код направительного диагноза по МКБ-10",
            0.0,
        ),
        _s(
            "diagnosis_name",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Наименование диагноза. В аналитическое хранилище не переносится",
            0.0,
        ),
        _s(
            "bed_profile",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Профиль койки",
            48.53,
        ),
        _s(
            "registration_dt",
            ColumnKind.DATETIME,
            Nullability.REQUIRED,
            "Дата регистрации направления — ось временного ряда",
            0.0,
        ),
        _s(
            "planned_dt",
            ColumnKind.DATETIME,
            Nullability.OPTIONAL,
            "Плановая дата госпитализации",
            4.39,
        ),
        _s(
            "polyclinic_dt",
            ColumnKind.DATETIME,
            Nullability.OPTIONAL,
            "Отметка поликлиники",
            18.30,
        ),
        _s(
            "hospitalization_dt",
            ColumnKind.DATETIME,
            Nullability.CONDITIONAL,
            "Фактическая госпитализация",
            11.48,
            conditional_reason=(
                "Пусто, пока госпитализация не состоялась или направление "
                "завершилось отказом. Это состояние записи, а не дефект"
            ),
        ),
        _s(
            "refusal_dt",
            ColumnKind.DATETIME,
            Nullability.CONDITIONAL,
            "Дата отказа по направлению",
            89.04,
            conditional_reason=(
                "Пусто у направлений, по которым отказа не было. Высокая "
                "доля пропусков здесь ожидаема и дефектом не является"
            ),
        ),
        _s(
            "territorial_type",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Тип территории проживания",
            0.0,
        ),
        _s(
            "referral_purpose",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Цель направления",
            0.0,
        ),
        _s(
            "finance_source",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Источник финансирования",
            0.0,
        ),
        _s(
            "sdu_load_date",
            ColumnKind.DATETIME,
            Nullability.REQUIRED,
            "Отметка выгрузки. Одинакова во всех строках файла",
            0.0,
        ),
    ),
    notes=(
        "Код случая повторяется примерно в 1 969 строках из 767 130. "
        "Это не ключ, и уникальность по нему не требуется",
        "Наименование диагноза остаётся в источнике и в карантине, "
        "в таблицу фактов переносится только код МКБ-10",
    ),
)


WAITING_CONTRACT = DatasetContract(
    key=WAITING,
    title="Ожидающие плановую госпитализацию в стационары",
    source_system=SOURCE_IS_BG,
    source_directory="Ожидающие плановую госпитализацию в стационары",
    file_glob="*.csv",
    target_table="fact_waiting_events",
    staging_table="stg_fact_waiting_events",
    forbidden_in_analytics=frozenset(
        {"patient_seq_no", "diagnosis_name", "operation_code", "operation_name"}
    ),
    audit_row_count=765_182,
    columns=(
        _s(
            "region_origin_code",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Код региона происхождения. Числовой код, не наименование",
            0.0,
        ),
        _s(
            "mo_destination_code",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Короткий код организации назначения",
            0.0,
        ),
        _s(
            "profile_code",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Код профиля койки",
            0.0,
        ),
        _s(
            "patient_seq_no",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Порядковый номер пациента. В аналитическое хранилище не переносится",
            0.0,
        ),
        _s(
            "icd10_ref_diag_code",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Код направительного диагноза",
            0.0,
        ),
        _s(
            "diagnosis_name",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Наименование диагноза. В аналитическое хранилище не переносится",
            0.0,
        ),
        _s(
            "operation_code",
            ColumnKind.STRING,
            Nullability.CONDITIONAL,
            "Код планируемой операции",
            76.38,
            conditional_reason=(
                "Пусто у записей без планируемого вмешательства. Владелец "
                "данных не подтверждал обязательность поля, поэтому пропуск "
                "не является основанием для отклонения строки"
            ),
        ),
        _s(
            "operation_name",
            ColumnKind.STRING,
            Nullability.CONDITIONAL,
            "Наименование операции",
            76.38,
            conditional_reason="Пусто там же, где пуст код операции",
        ),
        _s(
            "registration_dt",
            ColumnKind.DATETIME,
            Nullability.REQUIRED,
            "Дата постановки в очередь",
            0.0,
        ),
        _s(
            "planned_dt",
            ColumnKind.DATETIME,
            Nullability.OPTIONAL,
            "Плановая дата госпитализации",
            4.39,
        ),
        _s(
            "sdu_load_date",
            ColumnKind.DATETIME,
            Nullability.REQUIRED,
            "Отметка выгрузки. Служит датой среза очереди",
            0.0,
        ),
    ),
    notes=(
        "Выгрузка представляет один срез очереди, а не историю срезов: "
        "отметка загрузки одна на весь файл",
        "Коды организации из этой выгрузки не пересекаются с наименованиями "
        "из выгрузки направлений. Сопоставление отсутствует",
    ),
)


REFUSALS_CONTRACT = DatasetContract(
    key=REFUSALS,
    title="Отказы в плановой госпитализации (приёмный покой)",
    source_system=SOURCE_IS_BG,
    source_directory="Отказы в плановой госпитализации (приёмный покой)",
    file_glob="*.csv",
    target_table="fact_refusal_events",
    staging_table="stg_fact_refusal_events",
    forbidden_in_analytics=frozenset({"icd_name"}),
    audit_row_count=1_508_732,
    columns=(
        _s(
            "region_in",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Регион обращения, наименование",
            0.0,
        ),
        _s(
            "org_in",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Организация обращения, полное наименование",
            0.0,
        ),
        _s(
            "resident",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Тип территории проживания",
            0.17,
        ),
        _s(
            "insured",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Статус застрахованности",
            0.0,
        ),
        _s(
            "benefit_cat",
            ColumnKind.STRING,
            Nullability.CONDITIONAL,
            "Категория льготника",
            23.92,
            conditional_reason="Пусто у пациентов без льготной категории",
        ),
        _s(
            "refuse_dt",
            ColumnKind.DATETIME,
            Nullability.REQUIRED,
            "Дата отказа — ось временного ряда",
            0.0,
        ),
        _s(
            "attach_region",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Регион прикрепления",
            1.24,
        ),
        _s(
            "attach_org",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Организация прикрепления",
            1.20,
        ),
        _s(
            "icd10",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Код диагноза по МКБ-10",
            0.0017,
        ),
        _s(
            "icd_name",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Наименование диагноза. В аналитическое хранилище не переносится",
            0.0,
        ),
        _s(
            "amount",
            ColumnKind.DECIMAL,
            Nullability.CONDITIONAL,
            "Предъявленная сумма к оплате",
            24.41,
            conditional_reason="Пусто у обращений без предъявленной суммы",
        ),
        _s(
            "finance_src",
            ColumnKind.STRING,
            Nullability.OPTIONAL,
            "Источник финансирования",
            0.12,
        ),
        _s(
            "sdu_load_date",
            ColumnKind.DATETIME,
            Nullability.REQUIRED,
            "Отметка выгрузки",
            0.0,
        ),
    ),
    notes=(
        "Прямого идентификатора пациента в выгрузке нет, и он не создаётся: "
        "для доли отказов нужен счёт событий, а не различение людей",
        "Регион прикрепления содержит 23 различных значения против 20 "
        "у региона обращения. Расхождение не устраняется автоматически",
    ),
)


TREATED_CONTRACT = DatasetContract(
    key=TREATED,
    title="Количество пролеченных случаев в разрезе МО",
    source_system=SOURCE_ERSB,
    source_directory="Количество пролеченных случаев в разрезе МО",
    file_glob="*.csv",
    target_table="fact_treated_snapshot",
    staging_table="stg_fact_treated_snapshot",
    audit_row_count=2_196,
    columns=(
        _s(
            "medicine_organization",
            ColumnKind.STRING,
            Nullability.REQUIRED,
            "Организация, полное юридическое наименование",
            0.0,
        ),
        _s(
            "discharged_total",
            ColumnKind.INTEGER,
            Nullability.REQUIRED,
            "Всего выбыло больных",
            0.0,
        ),
        _s(
            "discharged_children",
            ColumnKind.INTEGER,
            Nullability.REQUIRED,
            "В том числе дети до 18 лет",
            0.0,
        ),
        _s(
            "treated_budget",
            ColumnKind.INTEGER,
            Nullability.REQUIRED,
            "Пролечено по бюджету",
            0.0,
        ),
        _s(
            "treated_paid",
            ColumnKind.INTEGER,
            Nullability.REQUIRED,
            "Пролечено платно",
            0.0,
        ),
        _s(
            "discharged_within_day",
            ColumnKind.INTEGER,
            Nullability.REQUIRED,
            "Выбыло в течение суток",
            0.0,
        ),
        _s(
            "deaths_total",
            ColumnKind.INTEGER,
            Nullability.REQUIRED,
            "Всего умерло",
            0.0,
        ),
        _s(
            "bed_days",
            ColumnKind.INTEGER,
            Nullability.REQUIRED,
            "Сумма проведённых койко-дней",
            0.0,
        ),
        _s(
            "amount_to_pay",
            ColumnKind.DECIMAL,
            Nullability.REQUIRED,
            "Сумма к оплате",
            0.0,
        ),
        _s(
            "sdu_load_date",
            ColumnKind.DATETIME,
            Nullability.REQUIRED,
            "Момент выгрузки. НЕ отчётный период",
            0.0,
        ),
    ),
    notes=(
        "Отчётный период в выгрузке отсутствует. Показатели относятся "
        "к неизвестному интервалу, и как временной ряд набор непригоден",
        "Идентификатором организации служит наименование. Устойчивого "
        "кода в выгрузке нет",
    ),
)


CONTRACTS: dict[str, DatasetContract] = {
    contract.key: contract
    for contract in (
        REFERRALS_CONTRACT,
        WAITING_CONTRACT,
        REFUSALS_CONTRACT,
        TREATED_CONTRACT,
    )
}

ALLOWED_DATASETS: frozenset[str] = frozenset(CONTRACTS)


def get_contract(key: str) -> DatasetContract:
    """Контракт по ключу набора.

    Неизвестный ключ — ошибка, а не повод угадать. Разрешающий список
    защищает от загрузки наборов, не относящихся к задаче.
    """
    try:
        return CONTRACTS[key]
    except KeyError:
        allowed = ", ".join(sorted(ALLOWED_DATASETS))
        raise KeyError(
            f"Набор данных {key!r} не входит в разрешающий список MedSignal. "
            f"Разрешены: {allowed}"
        ) from None
