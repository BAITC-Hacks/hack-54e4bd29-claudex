"""Сборка отчётов аудита.

Отчёты рассчитаны на читателя, который не будет открывать ни код, ни
исходные выгрузки. Поэтому каждый вывод сопровождается тем, на чём он
основан, а пропущенные проверки названы явно.

Значения из источника в отчёты не попадают. Исключение сделано только для
административных справочников — регионов и организаций, — и только там,
где их публикация не сужает круг лиц.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from data_pipeline.audit.privacy import Sensitivity

SYNTHETIC_FREE_NOTE = (
    "Отчёт построен по исходным выгрузкам и не содержит ни одного значения "
    "из них, кроме административных справочников."
)


@dataclass(slots=True)
class AuditContext:
    audit_version: str
    source_root: str
    inventory: Any
    profiles: list[Any]
    workbooks: list[Any]
    temporal: list[Any]
    quality: list[Any]
    privacy: list[dict[str, Any]]
    classifications: list[Any]
    key_values: list[Any]
    join_assessments: list[Any]
    join_matrix: dict[str, dict[str, str]]
    candidates: list[Any]
    recommended_target: str | None
    recommendation_reason: str
    duplicate_content_groups: dict[str, list[str]] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


def _gb(value: int) -> str:
    return f"{value / 1e9:.2f} ГБ"


def _mb(value: int) -> str:
    return f"{value / 1e6:.1f} МБ"


def _num(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:,}".replace(",", " ")


def _table(header: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "|" + "|".join("---" for _ in header) + "|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _short_labels(ctx: AuditContext) -> dict[str, str]:
    """Короткие обозначения выгрузок.

    Наименования каталогов достигают семидесяти символов. Матрица, где
    заголовком столбца служит пара таких наименований, нечитаема, поэтому
    в таблицах используются обозначения, а расшифровка выносится рядом.
    """
    names = sorted({d.name for d in ctx.inventory.datasets})
    return {name: f"D{index}" for index, name in enumerate(names, start=1)}


def _legend(labels: dict[str, str]) -> str:
    return _table(
        ["Обозначение", "Выгрузка"],
        [[code, name] for name, code in sorted(labels.items(), key=lambda i: i[1])],
    )


def _matrix_block(ctx: AuditContext) -> str:
    """Матрица связуемости: строки — пары выгрузок, столбцы — роли ключей."""
    if not ctx.join_assessments:
        return "Общих ключей между выгрузками не обнаружено."

    labels = _short_labels(ctx)
    roles = sorted({a.role for a in ctx.join_assessments})
    best: dict[tuple[str, str], str] = {}
    rank = {"STRONG JOIN": 0, "POSSIBLE JOIN": 1, "WEAK JOIN": 2, "NO JOIN": 3}

    for item in ctx.join_assessments:
        pair = (
            labels.get(item.left_dataset, item.left_dataset),
            labels.get(item.right_dataset, item.right_dataset),
        )
        key = (f"{pair[0]} ↔ {pair[1]}", item.role)
        current = best.get(key)
        # Между двумя выгрузками может найтись несколько столбцов одной роли.
        # В матрицу выносится лучший вариант: наличие связи важнее того,
        # что какой-то другой столбец её не даёт.
        if current is None or rank[item.strength] < rank[current]:
            best[key] = item.strength

    pairs = sorted({pair for pair, _ in best})
    rows = [[pair, *[best.get((pair, role), "—") for role in roles]] for pair in pairs]
    return "\n".join(
        [
            _table(["Пара выгрузок", *roles], rows),
            "",
            "Обозначения:",
            "",
            _legend(labels),
        ]
    )


def _write(path: Path, title: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n{body.rstrip()}\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Отдельные документы
# ---------------------------------------------------------------------------


def _inventory_doc(ctx: AuditContext) -> str:
    inv = ctx.inventory
    parts = [
        f"Источник: `{ctx.source_root}` — открывается только на чтение.",
        "",
        _table(
            ["Показатель", "Значение"],
            [
                ["Файлов", _num(inv.total_files)],
                ["Общий объём", _gb(inv.total_size_bytes)],
                ["Каталогов-выгрузок", _num(len(inv.datasets))],
            ],
        ),
        "",
        "## Расширения",
        "",
        _table(
            ["Расширение", "Файлов"],
            [[ext, _num(count)] for ext, count in inv.extensions.items()],
        ),
        "",
        "## Выгрузки",
        "",
        _table(
            ["Выгрузка", "Файлов", "Объём", "Табличных", "Excel", "Прочих"],
            [
                [
                    d.name,
                    _num(d.file_count),
                    _gb(d.size_bytes),
                    _num(len(d.tabular_files)),
                    _num(len(d.excel_files)),
                    _num(len(d.other_files)),
                ]
                for d in inv.datasets
            ],
        ),
    ]

    notes = [(d.name, note) for d in inv.datasets for note in d.notes]
    if notes:
        parts += [
            "",
            "## Замечания по комплектности",
            "",
            _table(["Выгрузка", "Замечание"], notes),
        ]

    if ctx.duplicate_content_groups:
        parts += [
            "",
            "## Файлы с одинаковым содержимым",
            "",
            _table(
                ["SHA-256 (первые 16)", "Файлы"],
                [
                    [digest[:16], "<br>".join(paths)]
                    for digest, paths in ctx.duplicate_content_groups.items()
                ],
            ),
        ]

    parts += [
        "",
        "## Описания поставщика",
        "",
    ]
    for dataset in inv.datasets:
        if dataset.description:
            parts += [f"### {dataset.name}", "", dataset.description, ""]

    return "\n".join(parts)


def _schema_doc(ctx: AuditContext) -> str:
    parts = [SYNTHETIC_FREE_NOTE, ""]

    for profile in ctx.profiles:
        parts += [
            f"## {profile.dataset}",
            "",
            f"Таблица `{profile.table}`, файлов: {len(profile.files)}, "
            f"объём {_mb(profile.size_bytes)}.",
            "",
            _table(
                ["Показатель", "Значение"],
                [
                    ["Строк", _num(profile.row_count)],
                    ["Столбцов", _num(profile.column_count)],
                    [
                        "Метрики",
                        "точные" if profile.exact_metrics else "приблизительные",
                    ],
                    ["Время прохода", f"{profile.elapsed_seconds:.1f} с"],
                ],
            ),
            "",
        ]

        rows = []
        for column in profile.columns:
            if column.inferred_type in {"datetime", "date"}:
                extent = f"{column.min_date or '—'} … {column.max_date or '—'}"
            elif column.min_value is not None or column.max_value is not None:
                extent = f"{column.min_value or '—'} … {column.max_value or '—'}"
            elif column.value_sample_withheld:
                extent = "значения не публикуются"
            else:
                extent = "—"
            rows.append(
                [
                    f"`{column.column_name}`",
                    column.inferred_type,
                    "да" if column.nullable else "нет",
                    _num(column.null_count),
                    f"{column.null_percentage:.2f}%",
                    ("≈" if column.unique_is_approximate else "")
                    + _num(column.unique_count),
                    extent,
                ]
            )
        parts += [
            _table(
                [
                    "Столбец",
                    "Тип",
                    "Пусто допускается",
                    "Пустых",
                    "Доля пустых",
                    "Уникальных",
                    "Диапазон",
                ],
                rows,
            ),
            "",
        ]

        numeric = [
            c
            for c in profile.columns
            if c.inferred_type in {"integer", "float"} and c.mean is not None
        ]
        if numeric:
            parts += [
                "Числовые столбцы:",
                "",
                _table(
                    ["Столбец", "Среднее", "Медиана", "5-й перцентиль", "95-й"],
                    [
                        [
                            f"`{c.column_name}`",
                            f"{c.mean:,.2f}".replace(",", " "),
                            f"{c.median:,.2f}".replace(",", " ")
                            if c.median is not None
                            else "—",
                            f"{c.p05:,.2f}".replace(",", " ")
                            if c.p05 is not None
                            else "—",
                            f"{c.p95:,.2f}".replace(",", " ")
                            if c.p95 is not None
                            else "—",
                        ]
                        for c in numeric
                    ],
                ),
                "",
            ]

        if profile.skipped_metrics:
            parts += ["Пропущенные метрики:", ""]
            parts += [f"- {item}" for item in profile.skipped_metrics]
            parts += [""]

    if ctx.workbooks:
        parts += ["## Книги Excel", ""]
        for book in ctx.workbooks:
            parts += [
                f"### {book.dataset} — `{book.file}`",
                "",
                f"Листов: {book.sheet_count}, объём {_mb(book.size_bytes)}.",
                "",
                _table(
                    [
                        "Лист",
                        "Строк",
                        "Столбцов",
                        "Строка заголовка",
                        "Пустых сверху",
                        "Объединённых",
                        "Формул",
                        "Похоже на справочник",
                    ],
                    [
                        [
                            s.sheet_name,
                            _num(s.used_rows),
                            _num(s.used_columns),
                            _num(s.header_row_index),
                            _num(s.leading_empty_rows),
                            _num(s.merged_ranges),
                            _num(s.formula_cells),
                            "да" if s.looks_like_reference else "нет",
                        ]
                        for s in book.sheets
                    ],
                ),
                "",
            ]
            for sheet in book.sheets:
                if sheet.headers:
                    parts += [
                        f"Заголовки листа «{sheet.sheet_name}»:",
                        "",
                        _table(
                            ["№", "Заголовок"],
                            [
                                [str(index), f"`{header}`" if header else "«пусто»"]
                                for index, header in enumerate(sheet.headers, start=1)
                            ],
                        ),
                        "",
                    ]
                if sheet.notes:
                    parts += [f"Лист `{sheet.sheet_name}`:", ""]
                    parts += [f"- {note}" for note in sheet.notes]
                    parts += [""]
            for note in book.notes:
                parts += [f"- {note}"]
            parts += [""]

    return "\n".join(parts)


def _quality_doc(ctx: AuditContext) -> str:
    parts = [
        "Аудит фиксирует найденное и ничего не исправляет. Решение о том, "
        "что здесь ошибка выгрузки, а что свойство предметной области, "
        "принимает владелец данных.",
        "",
    ]

    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    all_findings = [f for q in ctx.quality for f in q.findings]
    counts: dict[str, int] = {}
    for finding in all_findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1

    parts += [
        "## Сводка",
        "",
        _table(
            ["Уровень", "Замечаний"],
            [
                [level, _num(counts.get(level, 0))]
                for level in ("CRITICAL", "WARNING", "INFO")
            ],
        ),
        "",
    ]

    for quality in ctx.quality:
        parts += [
            f"## {quality.dataset}",
            "",
            f"Строк: {_num(quality.row_count)}. Полных дубликатов: "
            + (
                _num(quality.duplicate_rows)
                if quality.duplicate_rows is not None
                else quality.duplicate_rows_status
            )
            + ".",
            "",
        ]
        if quality.findings:
            rows = sorted(
                quality.findings, key=lambda f: severity_order.get(f.severity, 9)
            )
            parts += [
                _table(
                    ["Уровень", "Проверка", "Столбец", "Строк", "Описание"],
                    [
                        [
                            f.severity,
                            f.check,
                            f"`{f.column}`" if f.column else "—",
                            _num(f.affected_rows),
                            f.detail,
                        ]
                        for f in rows
                    ],
                ),
                "",
            ]
        else:
            parts += ["Замечаний не обнаружено.", ""]

        if quality.skipped_checks:
            parts += ["Пропущенные проверки:", ""]
            parts += [f"- {item}" for item in quality.skipped_checks]
            parts += [""]

    return "\n".join(parts)


def _time_doc(ctx: AuditContext) -> str:
    parts = [
        "Возможность прогноза определяется не наличием даты, а регулярностью "
        "наблюдений. Ниже — покрытие по каждому столбцу с датой.",
        "",
    ]

    for temporal in ctx.temporal:
        parts += [
            f"## {temporal.dataset}",
            "",
            "Основной столбец времени: "
            + (
                f"`{temporal.primary_date_column}`"
                if temporal.primary_date_column
                else "не определён"
            )
            + ". Временной ряд построить "
            + ("можно" if temporal.time_series_possible else "нельзя")
            + ".",
            "",
        ]
        if temporal.columns:
            parts += [
                _table(
                    [
                        "Столбец",
                        "Роль",
                        "Непустых",
                        "С",
                        "По",
                        "Дней истории",
                        "Различных дней",
                        "Месяцев",
                        "Детализация",
                        "Пропущено месяцев",
                        "Ранее окна",
                        "Позже сегодня",
                    ],
                    [
                        [
                            f"`{c.column_name}`",
                            c.role,
                            _num(c.non_null_count),
                            c.min_date or "—",
                            c.max_date or "—",
                            _num(c.history_days),
                            _num(c.distinct_days),
                            _num(c.distinct_months),
                            c.granularity,
                            _num(len(c.missing_months)),
                            _num(c.implausible_past_count),
                            _num(c.after_today_count),
                        ]
                        for c in temporal.columns
                    ],
                ),
                "",
            ]
            anomalies = [
                (c.column_name, note) for c in temporal.columns for note in c.notes
            ]
            if anomalies:
                parts += [
                    "Аномалии дат:",
                    "",
                    _table(["Столбец", "Замечание"], anomalies),
                    "",
                ]
            gaps = [
                (c.column_name, ", ".join(c.missing_months))
                for c in temporal.columns
                if c.missing_months
            ]
            if gaps:
                parts += [
                    "Пропущенные месяцы:",
                    "",
                    _table(["Столбец", "Месяцы"], gaps),
                    "",
                ]
        for note in temporal.notes:
            parts += [f"- {note}"]
        parts += [""]

    return "\n".join(parts)


def _region_doc(ctx: AuditContext) -> str:
    parts = [
        "Регион — обязательный разрез анализа и административный справочник, "
        "поэтому значения в этом документе публикуются.",
        "",
    ]
    rows = []
    for kv in ctx.key_values:
        if kv.role != "region":
            continue
        rows.append([kv.dataset, f"`{kv.column}`", _num(kv.distinct_count)])
    if rows:
        parts += [
            _table(["Выгрузка", "Столбец", "Различных значений"], rows),
            "",
        ]
    else:
        parts += ["Столбцов с регионом не обнаружено.", ""]

    parts += [
        "## Пригодность к единому справочнику",
        "",
    ]
    region_keys = [kv for kv in ctx.key_values if kv.role == "region"]
    if len(region_keys) >= 2:
        base = max(region_keys, key=lambda k: k.distinct_count)
        for other in region_keys:
            if other is base:
                continue
            overlap = len(base.values & other.values)
            parts += [
                f"- `{other.dataset}.{other.column}` пересекается с "
                f"`{base.dataset}.{base.column}` на {overlap} из "
                f"{other.distinct_count} значений"
            ]
        parts += [""]
    else:
        parts += [
            "Сравнивать нечего: столбец региона найден менее чем в двух выгрузках.",
            "",
        ]
    return "\n".join(parts)


def _hospital_doc(ctx: AuditContext) -> str:
    parts = [
        "Медицинская организация — юридическое лицо, а не человек, поэтому "
        "счётчики по ней публикуются. Сами наименования в отчёт не выносятся: "
        "в редких сочетаниях с диагнозом и датой они сужают круг лиц.",
        "",
    ]
    rows = [
        [kv.dataset, f"`{kv.column}`", _num(kv.distinct_count)]
        for kv in ctx.key_values
        if kv.role == "hospital"
    ]
    if rows:
        parts += [
            _table(["Выгрузка", "Столбец", "Различных значений"], rows),
            "",
        ]
    else:
        parts += ["Столбцов с организацией не обнаружено.", ""]

    hospital_joins = [a for a in ctx.join_assessments if a.role == "hospital"]
    if hospital_joins:
        parts += [
            "## Совпадение идентификаторов между выгрузками",
            "",
            _table(
                ["Слева", "Справа", "Пересечение", "Покрытие слева", "Оценка"],
                [
                    [
                        f"{a.left_dataset}.`{a.left_column}`",
                        f"{a.right_dataset}.`{a.right_column}`",
                        _num(a.overlap),
                        f"{a.left_coverage_pct:.1f}%",
                        a.strength,
                    ]
                    for a in hospital_joins
                ],
            ),
            "",
        ]
    return "\n".join(parts)


def _join_doc(ctx: AuditContext) -> str:
    parts = [
        "Оценка построена на фактическом пересечении множеств значений. "
        "Совпадение имён столбцов не учитывается: оно ничего не доказывает. "
        "Нечёткое сопоставление наименований не выполнялось.",
        "",
        "## Матрица",
        "",
        _matrix_block(ctx),
        "",
        "## Подробно",
        "",
    ]
    if ctx.join_assessments:
        parts += [
            _table(
                [
                    "Ключ",
                    "Слева",
                    "Справа",
                    "Слева значений",
                    "Справа значений",
                    "Пересечение",
                    "Оценка",
                    "Обоснование",
                ],
                [
                    [
                        a.role,
                        f"{a.left_dataset}.`{a.left_column}`",
                        f"{a.right_dataset}.`{a.right_column}`",
                        _num(a.left_distinct),
                        _num(a.right_distinct),
                        _num(a.overlap),
                        a.strength,
                        a.rationale,
                    ]
                    for a in sorted(ctx.join_assessments, key=lambda x: x.role)
                ],
            ),
            "",
        ]
    return "\n".join(parts)


def _privacy_doc(ctx: AuditContext) -> str:
    parts = [
        "Классификация выполнена по именам столбцов и форме значений. "
        "Ни одно значение из источника в этот документ не попадает.",
        "",
    ]

    order = {
        Sensitivity.HIGHLY_SENSITIVE.value: 0,
        Sensitivity.PERSONAL.value: 1,
        Sensitivity.SENSITIVE.value: 2,
        Sensitivity.OPERATIONAL.value: 3,
        Sensitivity.PUBLIC_REFERENCE.value: 4,
    }
    rows = sorted(
        ctx.privacy,
        key=lambda r: (order.get(str(r["sensitivity"]), 9), str(r["dataset"])),
    )

    critical = [r for r in rows if r["risk_level"] in {"CRITICAL", "HIGH"}]
    parts += [
        "## Столбцы повышенного риска",
        "",
    ]
    if critical:
        parts += [
            _table(
                [
                    "Выгрузка",
                    "column_name",
                    "detected_type",
                    "non_null_count",
                    "unique_count",
                    "risk_level",
                    "Обращение",
                ],
                [
                    [
                        r["dataset"],
                        f"`{r['column_name']}`",
                        r["detected_type"],
                        _num(r["non_null_count"]),
                        ("≈" if r["unique_is_approximate"] else "")
                        + _num(r["unique_count"]),
                        r["risk_level"],
                        r["handling"],
                    ]
                    for r in critical
                ],
            ),
            "",
        ]
    else:
        parts += [
            "Прямых идентификаторов личности в составе столбцов не обнаружено.",
            "",
        ]

    parts += [
        "## Полная классификация",
        "",
    ]
    parts += [
        _table(
            [
                "Выгрузка",
                "Столбец",
                "Тип",
                "Категория",
                "Риск",
                "Обращение",
                "Обоснование",
            ],
            [
                [
                    r["dataset"],
                    f"`{r['column_name']}`",
                    r["detected_type"],
                    r["sensitivity"],
                    r["risk_level"],
                    r["handling"],
                    r["rationale"],
                ]
                for r in rows
            ],
        ),
        "",
    ]
    return "\n".join(parts)


def _target_doc(ctx: AuditContext) -> str:
    parts = [
        "Целевая переменная не выбиралась заранее. Ниже — проверка того, "
        "какие величины вообще вычислимы из фактически найденных столбцов.",
        "",
        _table(
            ["Кандидат", "Доступность", "Прогнозируемость", "Причина"],
            [[c.name, c.status, c.feasibility, c.reason] for c in ctx.candidates],
        ),
        "",
    ]

    for candidate in ctx.candidates:
        parts += [
            f"## {candidate.name}",
            "",
            candidate.definition,
            "",
            f"**Доступность:** {candidate.status}",
            "",
            f"**Причина:** {candidate.reason}",
            "",
            f"**Прогнозируемость:** {candidate.feasibility} — "
            f"{candidate.feasibility_reason}",
            "",
            _table(
                ["Требуемая роль", "Что нужно", "Обязательна", "Найдена", "Где"],
                [
                    [
                        r.role,
                        r.description,
                        "да" if r.required else "нет",
                        "да" if r.satisfied else "нет",
                        ", ".join(r.found_in) if r.found_in else "—",
                    ]
                    for r in candidate.requirements
                ],
            ),
            "",
        ]

    parts += [
        "## Рекомендация",
        "",
        (
            f"**{ctx.recommended_target}** — {ctx.recommendation_reason}"
            if ctx.recommended_target
            else ctx.recommendation_reason
        ),
        "",
    ]
    return "\n".join(parts)


def _feature_doc(ctx: AuditContext) -> str:
    """Каталог признаков с разделением по моменту доступности.

    Разделение важнее полноты каталога. Признак, значение которого
    становится известно позже момента прогноза, при обучении даёт высокую
    точность и полностью бесполезен в эксплуатации.
    """
    known: list[Sequence[str]] = []
    leaking: list[Sequence[str]] = []

    # Столбец, заполняемый в момент наступления события, известен на момент
    # прогноза. Столбец, заполняемый при завершении случая, — нет.
    future_markers = (
        "hospitalization_dt",
        "refusal_dt",
        "refuse_dt",
        "polyclinic_dt",
        "death_date",
        "take_of_date",
        "discharged",
        "deaths_total",
        "bed_days",
        "amount",
        "treated_",
    )

    for profile in ctx.profiles:
        for column in profile.columns:
            name = column.column_name
            lowered = name.lower()
            row = [
                profile.dataset,
                f"`{name}`",
                column.inferred_type,
                f"{column.null_percentage:.1f}%",
            ]
            if lowered == "sdu_load_date":
                known.append([*row, "отметка выгрузки: признак свежести данных"])
            elif any(marker in lowered for marker in future_markers):
                leaking.append(
                    [
                        *row,
                        "заполняется после исхода случая: на момент прогноза "
                        "неизвестен",
                    ]
                )
            else:
                known.append([*row, "заполняется в момент регистрации события"])

    return "\n".join(
        [
            "Каталог построен только из фактически существующих столбцов. "
            "Разделение по моменту доступности обязательно: признак, "
            "значение которого появляется позже точки прогноза, при обучении "
            "даст завышенную точность и окажется бесполезен в эксплуатации.",
            "",
            "## Известны на момент прогноза",
            "",
            _table(["Выгрузка", "Столбец", "Тип", "Доля пустых", "Комментарий"], known),
            "",
            "## Риск утечки будущей информации",
            "",
            _table(["Выгрузка", "Столбец", "Тип", "Доля пустых", "Почему"], leaking),
            "",
            "## Производные признаки, допустимые к расчёту",
            "",
            "- Скользящие агрегаты по организации и профилю за прошедшие "
            "7, 14, 28 дней.",
            "- Отклонение текущего значения от собственной нормы организации.",
            "- Календарные признаки: день недели, месяц, праздничный день.",
            "- Давность последней выгрузки как признак свежести данных.",
            "",
            "Все производные обязаны рассчитываться по окну, закрытому строго "
            "до точки прогноза.",
        ]
    )


def _canonical_doc(ctx: AuditContext) -> str:
    """Предложение канонической модели. Таблицы здесь не создаются."""
    by_dataset = {p.dataset: p for p in ctx.profiles}
    temporal_by_dataset = {t.dataset: t for t in ctx.temporal}

    rows: list[Sequence[str]] = []
    for classification in ctx.classifications:
        profile = by_dataset.get(classification.dataset)
        temporal = temporal_by_dataset.get(classification.dataset)
        if profile is None:
            continue
        rows.append(
            [
                classification.dataset,
                classification.probable_source,
                classification.confidence,
                _num(profile.row_count),
                temporal.primary_date_column if temporal else "—",
            ]
        )

    return "\n".join(
        [
            "Предложение, а не реализация. Ни одна таблица не создаётся.",
            "",
            "## Исходные выгрузки и их роль",
            "",
            _table(
                [
                    "Выгрузка",
                    "Вероятный источник",
                    "Уверенность",
                    "Строк",
                    "Ось времени",
                ],
                rows,
            ),
            "",
            "## Измерения",
            "",
            "### dim_region",
            "",
            "- **Зерно:** один административный регион.",
            "- **Смысл:** территориальный разрез, общий для всех выгрузок.",
            "- **Ключ:** код региона; наименование — атрибут.",
            "- **Проблема:** в части выгрузок регион задан наименованием, "
            "в части — кодом. Требуется сопоставление, подтверждённое "
            "владельцем данных.",
            "",
            "### dim_hospital",
            "",
            "- **Зерно:** одна медицинская организация.",
            "- **Смысл:** основной объект наблюдения MedSignal.",
            "- **Ключ:** устойчивый код организации.",
            "- **Проблема:** устойчивый код присутствует не везде. Часть "
            "выгрузок идентифицирует организацию полным юридическим "
            "наименованием, которое меняется при переименовании и не может "
            "служить ключом.",
            "",
            "## Факты",
            "",
            "### fact_referrals",
            "",
            "- **Зерно:** одно направление на плановую госпитализацию.",
            "- **Источник:** выгрузка направлений.",
            "- **Время:** дата регистрации направления.",
            "- **Измерения:** организация направляющая и принимающая, профиль "
            "койки, диагноз, источник финансирования, территориальный тип.",
            "- **Меры:** число направлений; срок до плановой даты.",
            "",
            "### fact_queue_snapshot",
            "",
            "- **Зерно:** состояние очереди на организацию, профиль и дату.",
            "- **Источник:** выгрузка ожидающих госпитализацию.",
            "- **Время:** дата среза, восстанавливаемая из дат регистрации.",
            "- **Меры:** размер очереди, средний срок ожидания.",
            "- **Проблема:** выгрузка представляет собой один срез, а не "
            "историю срезов. Восстановление истории требует допущения о том, "
            "что запись остаётся в очереди до плановой даты.",
            "",
            "### fact_refusals",
            "",
            "- **Зерно:** один случай отказа в приёмном покое.",
            "- **Источник:** выгрузка отказов.",
            "- **Время:** дата отказа.",
            "- **Измерения:** регион и организация обращения, регион и "
            "организация прикрепления, диагноз, льготная категория.",
            "- **Меры:** число отказов, предъявленная сумма.",
            "",
            "### fact_treated_cases",
            "",
            "- **Зерно:** организация за отчётный период.",
            "- **Источник:** выгрузка пролеченных случаев.",
            "- **Меры:** выбывшие, дети, по бюджету, платно, умершие, "
            "койко-дни, сумма к оплате.",
            "- **Проблема:** отчётный период в выгрузке не указан. Без него "
            "таблица остаётся одним срезом и в ряд не превращается.",
            "",
            "### fact_vaccination_activity",
            "",
            "- **Зерно:** один факт вакцинации.",
            "- **Источник:** выгрузка фактов вакцинации.",
            "- **Время:** дата проведения.",
            "- **Измерения:** организация, регион, план вакцинации, возрастная "
            "группа.",
            "- **Меры:** число вакцинаций.",
            "- **Замечание:** к риску перегрузки стационаров отношения не "
            "имеет; полезна как показатель активности первичного звена.",
            "",
            "## Что остаётся нерешённым",
            "",
            "- Единый устойчивый ключ организации между выгрузками.",
            "- Отчётный период у агрегированных выгрузок.",
            "- История срезов очереди вместо одного среза.",
        ]
    )


def _clickhouse_doc(ctx: AuditContext) -> str:
    largest = max((p.row_count for p in ctx.profiles), default=0)
    return "\n".join(
        [
            "Предложение архитектуры. Ни один CREATE TABLE не выполняется.",
            "",
            f"Наибольшая выгрузка содержит {_num(largest)} строк, что определяет "
            "выбор в пользу колоночного хранения для аналитических разрезов. "
            "Состояние бизнес-операций остаётся в PostgreSQL (ADR-0010): "
            "ClickHouse хранит наблюдения, а не решения.",
            "",
            "## fact_referrals",
            "",
            _table(
                ["Параметр", "Предложение"],
                [
                    ["Зерно", "одно направление"],
                    ["Движок", "MergeTree"],
                    ["PARTITION BY", "toYYYYMM(registration_date)"],
                    [
                        "ORDER BY",
                        "(region_code, hospital_code, bed_profile_code, "
                        "registration_date)",
                    ],
                    ["Хранение", "36 месяцев на детальном уровне"],
                    [
                        "Типичный запрос",
                        "динамика числа направлений по организации и профилю",
                    ],
                ],
            ),
            "",
            "## fact_refusals",
            "",
            _table(
                ["Параметр", "Предложение"],
                [
                    ["Зерно", "один отказ"],
                    ["Движок", "MergeTree"],
                    ["PARTITION BY", "toYYYYMM(refusal_date)"],
                    ["ORDER BY", "(region_code, hospital_code, refusal_date)"],
                    ["Хранение", "36 месяцев"],
                    ["Типичный запрос", "доля отказов по организации за период"],
                ],
            ),
            "",
            "## fact_queue_snapshot",
            "",
            _table(
                ["Параметр", "Предложение"],
                [
                    ["Зерно", "организация, профиль, дата среза"],
                    [
                        "Движок",
                        "ReplacingMergeTree(loaded_at) — повторная выгрузка "
                        "того же среза заменяет предыдущую",
                    ],
                    ["PARTITION BY", "toYYYYMM(snapshot_date)"],
                    [
                        "ORDER BY",
                        "(region_code, hospital_code, bed_profile_code, "
                        "snapshot_date)",
                    ],
                    ["Хранение", "бессрочно: объём мал"],
                    ["Типичный запрос", "рост очереди за 14 дней к предыдущим 14"],
                ],
            ),
            "",
            "## fact_vaccination_activity",
            "",
            _table(
                ["Параметр", "Предложение"],
                [
                    ["Зерно", "один факт вакцинации"],
                    ["Движок", "MergeTree"],
                    ["PARTITION BY", "toYYYYMM(vaccination_date)"],
                    [
                        "ORDER BY",
                        "(region_code, hospital_code, vaccination_plan_code, "
                        "vaccination_date)",
                    ],
                    [
                        "Хранение",
                        "12 месяцев на детальном уровне, далее — суточный агрегат",
                    ],
                    ["Типичный запрос", "охват по возрастным группам и регионам"],
                ],
            ),
            "",
            "## Общие решения",
            "",
            "- Возраст хранится возрастной группой, а не точным числом лет: "
            "точный возраст вместе с организацией и датой сужает круг лиц.",
            "- Идентификатор пациента в ClickHouse не переносится ни в каком "
            "виде. Детализация ниже уровня организации и профиля не нужна "
            "для задачи прогноза нагрузки.",
            "- Каждая таблица несёт столбец источника выгрузки и её отпечаток: "
            "без этого невозможно объяснить расхождение между витриной "
            "и источником.",
            "- Агрегированные витрины строятся материализованными "
            "представлениями поверх фактов, а не отдельным процессом записи.",
        ]
    )


def _main_doc(ctx: AuditContext) -> str:
    inv = ctx.inventory
    critical_privacy = [r for r in ctx.privacy if r["risk_level"] in {"CRITICAL", "HIGH"}]
    critical_quality = [
        f for q in ctx.quality for f in q.findings if f.severity == "CRITICAL"
    ]
    region_counts = {
        kv.dataset: kv.distinct_count for kv in ctx.key_values if kv.role == "region"
    }
    hospital_counts = {
        f"{kv.dataset}.{kv.column}": kv.distinct_count
        for kv in ctx.key_values
        if kv.role == "hospital"
    }

    gaps = _critical_gaps(ctx)
    questions = _owner_questions(ctx)

    series_tables = [t for t in ctx.temporal if t.time_series_possible]
    depths = [
        c.distinct_months or 0
        for t in series_tables
        for c in t.columns
        if c.column_name == t.primary_date_column
    ]
    shortest = min(depths) if depths else 0
    clusters = _hospital_clusters(ctx)

    parts = [
        "## Executive Summary",
        "",
        f"Исследовано {inv.total_files} файлов общим объёмом "
        f"{_gb(inv.total_size_bytes)} в {len(inv.datasets)} выгрузках. "
        "Исходный каталог не изменялся.",
        "",
        "Ключевые выводы:",
        "",
        f"- Временной ряд строится из {len(series_tables)} выгрузок из "
        f"{len(ctx.profiles)}. Самая короткая история среди них — "
        f"{shortest} мес.",
        f"- Выгрузки распадаются на {len(clusters)} группы по идентификатору "
        "медицинской организации; между группами общих значений нет."
        if len(clusters) > 1
        else "- Идентификатор медицинской организации связывает все выгрузки.",
        f"- Столбцов повышенного риска приватности: {len(critical_privacy)}. "
        "Прямых идентификаторов личности — ИИН, ФИО, телефона, адреса — "
        "среди них нет.",
        f"- Критических замечаний по качеству: {len(critical_quality)}.",
        "- Рекомендация по целевой переменной: "
        + (ctx.recommended_target or "отложена, см. раздел Recommended Target"),
        "",
        "## Dataset Inventory",
        "",
        _table(
            ["Выгрузка", "Файлов", "Объём", "Строк"],
            [
                [
                    d.name,
                    _num(d.file_count),
                    _gb(d.size_bytes),
                    _num(sum(p.row_count for p in ctx.profiles if p.dataset == d.name)),
                ]
                for d in inv.datasets
            ],
        ),
        "",
        "## Sources Found",
        "",
        _table(
            ["Выгрузка", "probable_source", "confidence", "Признаки"],
            [
                [
                    c.dataset,
                    c.probable_source,
                    c.confidence,
                    "; ".join(c.evidence[:2]),
                ]
                for c in ctx.classifications
            ],
        ),
        "",
        "## Data Volumes",
        "",
        _table(
            ["Таблица", "Формат", "Строк", "Столбцов", "Объём", "Метрики"],
            [
                [
                    p.dataset,
                    "CSV",
                    _num(p.row_count),
                    _num(p.column_count),
                    _mb(p.size_bytes),
                    "точные" if p.exact_metrics else "приблизительные",
                ]
                for p in ctx.profiles
            ]
            # Книги Excel профилируются отдельно и в перечень таблиц не
            # попадают. Без этих строк сводка объёмов умалчивает о двух
            # выгрузках из восьми.
            + [
                [
                    f"{w.dataset} / лист «{s.sheet_name}»",
                    "Excel",
                    _num(max(s.used_rows - (s.header_row_index or 0), 0)),
                    _num(s.used_columns),
                    _mb(w.size_bytes),
                    "точные",
                ]
                for w in ctx.workbooks
                for s in w.sheets
            ],
        ),
        "",
        "## Date Coverage",
        "",
        _table(
            ["Выгрузка", "Ось времени", "С", "По", "Месяцев", "Детализация", "Ряд"],
            [_date_row(t) for t in ctx.temporal],
        ),
        "",
        "## Regions",
        "",
        _table(
            ["Выгрузка", "Различных регионов"],
            [[name, _num(count)] for name, count in sorted(region_counts.items())],
        )
        if region_counts
        else "Столбец региона найден не во всех выгрузках.",
        "",
        "## Hospitals",
        "",
        _table(
            ["Выгрузка и столбец", "Различных организаций"],
            [[name, _num(count)] for name, count in sorted(hospital_counts.items())],
        )
        if hospital_counts
        else "Столбец организации не найден.",
        "",
        "## Data Quality",
        "",
        _table(
            ["Выгрузка", "Строк", "Критических", "Предупреждений", "Дубликатов строк"],
            [
                [
                    q.dataset,
                    _num(q.row_count),
                    _num(sum(1 for f in q.findings if f.severity == "CRITICAL")),
                    _num(sum(1 for f in q.findings if f.severity == "WARNING")),
                    _num(q.duplicate_rows)
                    if q.duplicate_rows is not None
                    else q.duplicate_rows_status,
                ]
                for q in ctx.quality
            ],
        ),
        "",
        "Подробности — в DATA_QUALITY_REPORT.md.",
        "",
        "## Privacy Findings",
        "",
    ]

    if critical_privacy:
        parts += [
            _table(
                ["Выгрузка", "column_name", "detected_type", "risk_level", "Обращение"],
                [
                    [
                        r["dataset"],
                        f"`{r['column_name']}`",
                        r["detected_type"],
                        r["risk_level"],
                        r["handling"],
                    ]
                    for r in critical_privacy
                ],
            ),
            "",
        ]
    else:
        parts += [
            "Столбцов с ИИН, ФИО, телефоном, адресом или электронной почтой "
            "не обнаружено. Это не означает отсутствия персональных данных: "
            "сочетание организации, даты и диагноза остаётся "
            "квазиидентификатором.",
            "",
        ]

    parts += [
        "## Dataset Joinability",
        "",
        _matrix_block(ctx),
        "",
        "## Forecasting Feasibility",
        "",
        _table(
            ["Кандидат", "Доступность", "Прогнозируемость", "Обоснование"],
            [
                [c.name, c.status, c.feasibility, c.feasibility_reason]
                for c in ctx.candidates
            ],
        ),
        "",
        "## Target Candidates",
        "",
        _table(
            ["Кандидат", "Статус", "Причина"],
            [[c.name, c.status, c.reason] for c in ctx.candidates],
        ),
        "",
        "## Recommended Target",
        "",
        (
            f"**{ctx.recommended_target}**\n\n{ctx.recommendation_reason}"
            if ctx.recommended_target
            else "**RECOMMENDATION DEFERRED**\n\n"
            + ctx.recommendation_reason.removeprefix(
                "RECOMMENDATION DEFERRED: "
            ).capitalize()
        ),
        "",
        "## Potential Features",
        "",
        "Каталог признаков с разделением по моменту доступности — "
        "в FEATURE_CANDIDATES.md.",
        "",
        "## Leakage Risks",
        "",
        "- Дата фактической госпитализации и дата отказа становятся известны "
        "после точки прогноза. Использовать их как признак нельзя.",
        "- Показатели пролеченных случаев, койко-дней и сумм к оплате "
        "фиксируются при закрытии случая и относятся к будущему по отношению "
        "к моменту прогноза.",
        "- Отметка выгрузки одинакова во всех строках файла и отражает момент "
        "получения данных, а не момент события. Как признак события она "
        "бессмысленна, как признак свежести данных — допустима.",
        "",
        "## Canonical Model Proposal",
        "",
        "Предложение — в CANONICAL_DATA_MODEL_PROPOSAL.md. Таблицы не созданы.",
        "",
        "## ClickHouse Proposal",
        "",
        "Предложение — в CLICKHOUSE_DESIGN_PROPOSAL.md. CREATE TABLE " "не выполнялся.",
        "",
        "## Critical Data Gaps",
        "",
    ]
    parts += [f"{index}. {gap}" for index, gap in enumerate(gaps, start=1)]
    parts += [
        "",
        "## Questions for Dataset Owner",
        "",
    ]
    parts += [f"{index}. {q}" for index, q in enumerate(questions, start=1)]
    parts += [
        "",
        "## Recommendation for Phase 3B",
        "",
    ]
    parts += [f"- {item}" for item in _phase3b_recommendations(ctx)]
    parts += [
        "",
        "---",
        "",
        f"Версия аудита {ctx.audit_version}. Время прогона "
        f"{ctx.elapsed_seconds:.0f} с. Источник открывался только на чтение. "
        + SYNTHETIC_FREE_NOTE,
    ]
    return "\n".join(parts)


def _date_row(temporal: Any) -> list[str]:
    primary = next(
        (c for c in temporal.columns if c.column_name == temporal.primary_date_column),
        None,
    )
    return [
        temporal.dataset,
        f"`{temporal.primary_date_column}`" if temporal.primary_date_column else "—",
        primary.min_date if primary and primary.min_date else "—",
        primary.max_date if primary and primary.max_date else "—",
        _num(primary.distinct_months) if primary else "—",
        primary.granularity if primary else "—",
        "да" if temporal.time_series_possible else "нет",
    ]


def _hospital_clusters(ctx: AuditContext) -> list[set[str]]:
    """Группы выгрузок, связуемые по идентификатору организации.

    Строится граф: вершина — выгрузка с ключом организации, ребро — ненулевое
    пересечение значений. Несколько компонент связности означают, что общего
    идентификатора между ними нет, даже если внутри каждой связь надёжна.
    """
    datasets = {kv.dataset for kv in ctx.key_values if kv.role == "hospital"}
    if not datasets:
        return []

    parent = {name: name for name in datasets}

    def find(name: str) -> str:
        while parent[name] != name:
            parent[name] = parent[parent[name]]
            name = parent[name]
        return name

    for item in ctx.join_assessments:
        if item.role != "hospital" or item.strength == "NO JOIN":
            continue
        left, right = find(item.left_dataset), find(item.right_dataset)
        if left != right:
            parent[left] = right

    clusters: dict[str, set[str]] = {}
    for name in datasets:
        clusters.setdefault(find(name), set()).add(name)
    return sorted(clusters.values(), key=lambda c: (-len(c), sorted(c)[0]))


def _critical_gaps(ctx: AuditContext) -> list[str]:
    gaps: list[str] = []

    clusters = _hospital_clusters(ctx)
    if len(clusters) > 1:
        described = ". ".join(
            f"Группа {index}: " + ", ".join(sorted(cluster))
            for index, cluster in enumerate(clusters, start=1)
        )
        gaps.append(
            "Выгрузки распадаются на несвязанные группы по идентификатору "
            "медицинской организации. Внутри группы связь есть, между "
            "группами пересечение значений нулевое: одни выгрузки "
            "идентифицируют организацию полным юридическим наименованием, "
            "другие — коротким кодом. Без официального сопоставления "
            f"объединить их нельзя. {described}."
        )

    no_series = [t.dataset for t in ctx.temporal if not t.time_series_possible]
    if no_series:
        gaps.append(
            "Выгрузки без пригодной оси времени: "
            + ", ".join(sorted(set(no_series)))
            + ". Из них временной ряд не строится."
        )

    short = [
        t.dataset
        for t in ctx.temporal
        for c in t.columns
        if c.column_name == t.primary_date_column
        and (c.distinct_months or 0) < 24
        and (c.distinct_months or 0) > 0
    ]
    if short:
        gaps.append(
            "История короче двух лет в выгрузках: "
            + ", ".join(sorted(set(short)))
            + ". Годовая сезонность наблюдается менее двух раз, и отделить "
            "её от тренда невозможно."
        )

    if any(f.check == "IMPOSSIBLE VALUES" for q in ctx.quality for f in q.findings):
        gaps.append(
            "Обнаружены значения, невозможные по смыслу поля. До выяснения "
            "их происхождения обучение на этих столбцах даст смещённую модель."
        )

    dirty_dates = [
        (t.dataset, c)
        for t in ctx.temporal
        for c in t.columns
        if c.implausible_past_count or c.after_today_count
    ]
    if dirty_dates:
        described = "; ".join(
            f"{dataset} / {c.column_name}: до правдоподобного окна "
            f"{_num(c.implausible_past_count)}, "
            f"позже сегодняшнего дня {_num(c.after_today_count)}"
            for dataset, c in dirty_dates
        )
        gaps.append(
            "Даты выходят за правдоподобные границы. Часть записей датирована "
            "задолго до начала наблюдений, часть — будущим. Для плановой даты "
            "будущее нормально, для даты состоявшегося события — нет, и "
            "различить это можно только с владельцем данных. " + described + "."
        )

    capacity = any(
        "bed_capacity" in c.column_name or "koyka" in c.column_name
        for p in ctx.profiles
        for c in p.columns
    )
    if not capacity:
        gaps.append(
            "Коечный фонд организации в выгрузках отсутствует. Без знаменателя "
            "перегрузка не определяется: одно и то же число ожидающих значит "
            "разное для организаций разного размера."
        )

    gaps.append(
        "Наблюдаемая метка перегрузки отсутствует. Ни одна выгрузка не "
        "содержит признака, по которому можно было бы обучать классификатор "
        "риска напрямую."
    )
    return gaps


def _owner_questions(ctx: AuditContext) -> list[str]:
    questions = [
        "Существует ли справочник медицинских организаций с устойчивым кодом, "
        "и можно ли получить его отдельной выгрузкой? Без него связать "
        "выгрузки по организации невозможно.",
        "Как соотносятся короткий код организации в одних выгрузках и полное "
        "юридическое наименование в других? Существует ли официальное "
        "сопоставление?",
        "Доступен ли коечный фонд по организациям и профилям? Без него "
        "загрузка стационара не вычисляется.",
        "Возможна ли история срезов очереди, а не один срез на момент "
        "выгрузки? Текущая форма не позволяет восстановить, как очередь "
        "менялась.",
        "Какой отчётный период относится к агрегированной выгрузке "
        "пролеченных случаев? В файле указана только отметка загрузки.",
        "С какой периодичностью планируется поставка данных в эксплуатации? "
        "От этого зависит и горизонт прогноза, и порог сигнала об устаревании.",
    ]

    if any(c.future_count for t in ctx.temporal for c in t.columns):
        questions.append(
            "Даты в будущем за пределами планового горизонта — дефект "
            "выгрузки или допустимое состояние записи?"
        )
    if any(f.check == "IMPOSSIBLE VALUES" for q in ctx.quality for f in q.findings):
        questions.append(
            "Отрицательные значения в полях, где они невозможны по смыслу, — "
            "это способ кодирования отсутствия данных или дефект выгрузки?"
        )
    if any(f.check == "DUPLICATE KEYS" for q in ctx.quality for f in q.findings):
        questions.append(
            "Повторяющиеся значения в поле, объявленном идентификатором, — "
            "это версии одной записи или разные записи?"
        )
    return questions


def _phase3b_recommendations(ctx: AuditContext) -> list[str]:
    items = [
        "Начать с контрактов загрузки на те выгрузки, где ось времени "
        "определена и история достаточна. Остальные принимать только после "
        "ответов владельца данных.",
        "Идемпотентность импорта строить на SHA-256 файла: отпечатки уже "
        "посчитаны и лежат в data/audit/file_fingerprints.json.",
        "Псевдонимизацию выполнять до записи в аналитическое хранилище, "
        "а не после. Составной код случая госпитализации содержит порядковый "
        "номер пациента и должен заменяться суррогатным ключом на входе.",
        "Не переносить в ClickHouse ни один столбец с уровнем риска "
        "CRITICAL или HIGH в исходном виде.",
        "Валидацию строить четырьмя уровнями: структура файла, типы, "
        "справочные значения, бизнес-правила. Замечания этого аудита дают "
        "готовый перечень правил третьего и четвёртого уровня.",
        "Отчёт о качестве загрузки формировать на каждый импорт и хранить "
        "вместе с ним: расхождение витрины с источником иначе необъяснимо.",
    ]
    if ctx.recommended_target is None:
        items.append(
            "Целевую переменную не фиксировать до ответов владельца данных. "
            "Контракты загрузки от неё не зависят и могут быть построены раньше."
        )
    return items


# ---------------------------------------------------------------------------
# Машиночитаемая сводка
# ---------------------------------------------------------------------------


def build_summary(ctx: AuditContext) -> dict[str, Any]:
    """Компактный итог для передачи архитектору без исходных выгрузок."""
    temporal_by_dataset = {t.dataset: t for t in ctx.temporal}
    quality_by_dataset = {q.dataset: q for q in ctx.quality}
    classification_by_dataset = {c.dataset: c for c in ctx.classifications}

    datasets: list[dict[str, Any]] = []
    for profile in ctx.profiles:
        temporal = temporal_by_dataset.get(profile.dataset)
        quality = quality_by_dataset.get(profile.dataset)
        classification = classification_by_dataset.get(profile.dataset)
        privacy_rows = [
            r
            for r in ctx.privacy
            if r["dataset"] == profile.dataset and r["table"] == profile.table
        ]
        primary = (
            next(
                (
                    c
                    for c in temporal.columns
                    if c.column_name == temporal.primary_date_column
                ),
                None,
            )
            if temporal
            else None
        )

        datasets.append(
            {
                "name": profile.dataset,
                "table": profile.table,
                "source": (
                    classification.probable_source if classification else "UNKNOWN"
                ),
                "source_confidence": (
                    classification.confidence if classification else "LOW"
                ),
                "files": len(profile.files),
                "size_bytes": profile.size_bytes,
                "rows": profile.row_count,
                "columns": [
                    {
                        "name": c.column_name,
                        "type": c.inferred_type,
                        "null_pct": c.null_percentage,
                        "unique": c.unique_count,
                        "unique_approx": c.unique_is_approximate,
                    }
                    for c in profile.columns
                ],
                "date_range": {
                    "column": temporal.primary_date_column if temporal else None,
                    "min": primary.min_date if primary else None,
                    "max": primary.max_date if primary else None,
                    "months": primary.distinct_months if primary else 0,
                    "granularity": primary.granularity if primary else "unknown",
                    "missing_months": primary.missing_months if primary else [],
                    "time_series_possible": bool(
                        temporal and temporal.time_series_possible
                    ),
                },
                "regions": {
                    kv.column: kv.distinct_count
                    for kv in ctx.key_values
                    if kv.dataset == profile.dataset and kv.role == "region"
                },
                "hospitals": {
                    kv.column: kv.distinct_count
                    for kv in ctx.key_values
                    if kv.dataset == profile.dataset and kv.role == "hospital"
                },
                "quality": {
                    "critical": sum(
                        1 for f in quality.findings if f.severity == "CRITICAL"
                    )
                    if quality
                    else 0,
                    "warning": sum(1 for f in quality.findings if f.severity == "WARNING")
                    if quality
                    else 0,
                    "duplicate_rows": quality.duplicate_rows if quality else None,
                    "duplicate_rows_status": quality.duplicate_rows_status
                    if quality
                    else None,
                    "skipped_checks": quality.skipped_checks if quality else [],
                    "findings": [
                        {
                            "check": f.check,
                            "severity": f.severity,
                            "column": f.column,
                            "detail": f.detail,
                            "affected_rows": f.affected_rows,
                        }
                        for f in (quality.findings if quality else [])
                    ],
                },
                "privacy": {
                    "highest_risk": max(
                        (r["risk_level"] for r in privacy_rows),
                        key=lambda level: [
                            "NONE",
                            "LOW",
                            "MEDIUM",
                            "HIGH",
                            "CRITICAL",
                        ].index(str(level)),
                        default="NONE",
                    ),
                    "columns_requiring_action": [
                        {
                            "column_name": r["column_name"],
                            "detected_type": r["detected_type"],
                            "risk_level": r["risk_level"],
                            "handling": r["handling"],
                        }
                        for r in privacy_rows
                        if r["handling"] != "KEEP"
                    ],
                },
                "join_keys": sorted(
                    {kv.column for kv in ctx.key_values if kv.dataset == profile.dataset}
                ),
            }
        )

    return {
        "audit_version": ctx.audit_version,
        "generated_from": "локальный каталог выгрузок; сами данные не передаются",
        "total_files": ctx.inventory.total_files,
        "total_size_bytes": ctx.inventory.total_size_bytes,
        "datasets": datasets,
        "target_candidates": [c.to_dict() for c in ctx.candidates],
        "recommended_target": ctx.recommended_target,
        "recommendation_reason": ctx.recommendation_reason,
        "joinability": {
            "matrix": ctx.join_matrix,
            "assessments": [a.to_dict() for a in ctx.join_assessments],
        },
        "critical_gaps": _critical_gaps(ctx),
        "questions_for_dataset_owner": _owner_questions(ctx),
        "phase3b_recommendations": _phase3b_recommendations(ctx),
        "excel_workbooks": [w.to_dict() for w in ctx.workbooks],
    }


# ---------------------------------------------------------------------------


DOCUMENTS: tuple[tuple[str, str, str], ...] = (
    ("DATA_INVENTORY.md", "MedSignal — опись исходных выгрузок", "_inventory_doc"),
    ("SCHEMA_CATALOG.md", "MedSignal — каталог схем", "_schema_doc"),
    ("DATA_QUALITY_REPORT.md", "MedSignal — качество данных", "_quality_doc"),
    ("TIME_COVERAGE.md", "MedSignal — временное покрытие", "_time_doc"),
    ("REGION_MAPPING_ANALYSIS.md", "MedSignal — анализ регионов", "_region_doc"),
    (
        "HOSPITAL_MAPPING_ANALYSIS.md",
        "MedSignal — анализ медицинских организаций",
        "_hospital_doc",
    ),
    ("JOINABILITY_REPORT.md", "MedSignal — связуемость выгрузок", "_join_doc"),
    (
        "TARGET_FEASIBILITY.md",
        "MedSignal — кандидаты на целевую переменную",
        "_target_doc",
    ),
    ("FEATURE_CANDIDATES.md", "MedSignal — каталог признаков", "_feature_doc"),
    ("PRIVACY_AUDIT.md", "MedSignal — аудит приватности", "_privacy_doc"),
    (
        "CANONICAL_DATA_MODEL_PROPOSAL.md",
        "MedSignal — предложение канонической модели",
        "_canonical_doc",
    ),
    (
        "CLICKHOUSE_DESIGN_PROPOSAL.md",
        "MedSignal — предложение архитектуры ClickHouse",
        "_clickhouse_doc",
    ),
    ("DATA_AUDIT_REPORT.md", "MedSignal Data Audit", "_main_doc"),
)


def write_documents(ctx: AuditContext, docs_dir: Path) -> list[Path]:
    written: list[Path] = []
    for file_name, title, builder_name in DOCUMENTS:
        builder = globals()[builder_name]
        path = docs_dir / file_name
        _write(path, title, builder(ctx))
        written.append(path)
    return written
