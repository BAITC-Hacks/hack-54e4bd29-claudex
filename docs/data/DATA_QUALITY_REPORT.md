# MedSignal — качество данных

Аудит фиксирует найденное и ничего не исправляет. Решение о том, что здесь ошибка выгрузки, а что свойство предметной области, принимает владелец данных.

## Сводка

| Уровень | Замечаний |
|---|---|
| CRITICAL | 6 |
| WARNING | 21 |
| INFO | 6 |

## Количество пролеченных случаев в разрезе МО

Строк: 2 196. Полных дубликатов: 0.

| Уровень | Проверка | Столбец | Строк | Описание |
|---|---|---|---|---|
| WARNING | WHITESPACE ISSUES | `medicine_organization` | 35 | значения содержат ведущие или завершающие пробелы |
| INFO | CONSTANT COLUMN | `sdu_load_date` | — | во всех строках одно и то же значение |

## Направления на плановую госпитализацию в стационары

Строк: 767 130. Полных дубликатов: 0.

| Уровень | Проверка | Столбец | Строк | Описание |
|---|---|---|---|---|
| CRITICAL | MISSING VALUES | `refusal_dt` | 683 049 | пусто в 89.0% строк |
| CRITICAL | DUPLICATE KEYS | `hospitalization_code` | 1 969 | значение ключа повторяется: уникальных 765161 при 767130 непустых строках |
| WARNING | WHITESPACE ISSUES | `referring_mo` | 2 462 | значения содержат ведущие или завершающие пробелы |
| WARNING | WHITESPACE ISSUES | `hospital_mo` | 6 783 | значения содержат ведущие или завершающие пробелы |
| WARNING | WHITESPACE ISSUES | `diagnosis_name` | 23 437 | значения содержат ведущие или завершающие пробелы |
| WARNING | MISSING VALUES | `bed_profile` | 372 316 | пусто в 48.5% строк |
| WARNING | WHITESPACE ISSUES | `bed_profile` | 4 598 | значения содержат ведущие или завершающие пробелы |
| WARNING | MISSING VALUES | `polyclinic_dt` | 140 405 | пусто в 18.3% строк |
| WARNING | MISSING VALUES | `hospitalization_dt` | 88 042 | пусто в 11.5% строк |
| INFO | CONSTANT COLUMN | `sdu_load_date` | — | во всех строках одно и то же значение |

## Ожидающие плановую госпитализацию в стационары

Строк: 765 182. Полных дубликатов: 0.

| Уровень | Проверка | Столбец | Строк | Описание |
|---|---|---|---|---|
| CRITICAL | MISSING VALUES | `operation_code` | 584 408 | пусто в 76.4% строк |
| CRITICAL | MISSING VALUES | `operation_name` | 584 408 | пусто в 76.4% строк |
| WARNING | WHITESPACE ISSUES | `diagnosis_name` | 23 437 | значения содержат ведущие или завершающие пробелы |
| WARNING | WHITESPACE ISSUES | `operation_name` | 60 | значения содержат ведущие или завершающие пробелы |
| INFO | CONSTANT COLUMN | `sdu_load_date` | — | во всех строках одно и то же значение |

## Отказы в плановой госпитализации (приёмный покой)

Строк: 1 508 732. Полных дубликатов: 0.

| Уровень | Проверка | Столбец | Строк | Описание |
|---|---|---|---|---|
| WARNING | WHITESPACE ISSUES | `org_in` | 2 901 | значения содержат ведущие или завершающие пробелы |
| WARNING | MISSING VALUES | `benefit_cat` | 360 942 | пусто в 23.9% строк |
| WARNING | WHITESPACE ISSUES | `benefit_cat` | 249 | значения содержат ведущие или завершающие пробелы |
| WARNING | WHITESPACE ISSUES | `attach_org` | 1 728 | значения содержат ведущие или завершающие пробелы |
| WARNING | WHITESPACE ISSUES | `icd_name` | 10 471 | значения содержат ведущие или завершающие пробелы |
| WARNING | MISSING VALUES | `amount` | 368 272 | пусто в 24.4% строк |
| INFO | CONSTANT COLUMN | `sdu_load_date` | — | во всех строках одно и то же значение |

## Отказы от вакцинации и противопоказания

Строк: 66 709. Полных дубликатов: 0.

| Уровень | Проверка | Столбец | Строк | Описание |
|---|---|---|---|---|
| CRITICAL | MISSING VALUES | `contraindication` | 52 842 | пусто в 79.2% строк |
| WARNING | WHITESPACE ISSUES | `vaccination_plan_code` | 1 639 | значения содержат ведущие или завершающие пробелы |
| INFO | CONSTANT COLUMN | `sdu_load_date` | — | во всех строках одно и то же значение |

## Факты проведённых вакцинаций с возможностью представления в разрезе возрастов

Строк: 104 441 465. Полных дубликатов: SKIPPED_DUE_TO_RESOURCE_LIMIT.

| Уровень | Проверка | Столбец | Строк | Описание |
|---|---|---|---|---|
| CRITICAL | IMPOSSIBLE VALUES | `age` | — | минимум -999 при семантике, не допускающей отрицательных |
| WARNING | TYPE INCONSISTENCIES | `vaccination_date` | — | неразобранных дат: 155 |
| WARNING | WHITESPACE ISSUES | `vaccination_plan` | 5 638 191 | значения содержат ведущие или завершающие пробелы |
| WARNING | MISSING VALUES | `medicine_organization_code` | 21 207 670 | пусто в 20.3% строк |
| WARNING | WHITESPACE ISSUES | `medicine_organization_code` | 174 | значения содержат ведущие или завершающие пробелы |
| INFO | CONSTANT COLUMN | `sdu_load_date` | — | во всех строках одно и то же значение |

Пропущенные проверки:

- DUPLICATES: SKIPPED_DUE_TO_RESOURCE_LIMIT (объём 15.0 ГБ превышает бюджет памяти для поиска полных дубликатов)
- DUPLICATE KEYS / id: SKIPPED_DUE_TO_RESOURCE_LIMIT (сравнение опирается на приблизительный подсчёт уникальных)
- INCONSISTENT CATEGORY SPELLING: SKIPPED_DUE_TO_RESOURCE_LIMIT (объём выгрузки превышает бюджет проверки)
