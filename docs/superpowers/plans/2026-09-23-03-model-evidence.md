# MedSignal Model Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Измерить полезность прогнозов и предупреждений на независимых данных и получить воспроизводимое решение о допуске, включая отказ.

**Architecture:** Чистые функции ML и отдельный evaluation protocol. Training/inference используют подтверждённые агрегаты; model admission policy живёт отдельно от обучаемого estimator. Local replay остаётся исследовательским режимом до R1/R2.

**Tech Stack:** Existing scikit-learn HistGradientBoostingRegressor, NumPy, pytest,
existing MLflow/artifact infrastructure при интеграции.

**Spec:** ../specs/2026-09-23-pilot-consolidation-design.md

## Global Constraints

Не обещать заранее precision/recall. Не подбирать модель/пороги на final test.
Нет новых медицинских features без Data Audit и availability-at-prediction-time.
Данные Q1 2025 уже просмотрены: это development evidence, не новый независимый test.
Existing 20/35/50 thresholds меняются только новой утверждённой policy.
STALE/freshness и structural validity — отдельные свойства.
Модель прогнозирует количество записей о направлениях; не пациентов и не койки.

## Review Focus

1. Horizon label пересекает validation boundary — M1 исключает пример.
2. Missing delivery выглядит как zero demand — M1 не подменяет UNKNOWN нулём.
3. Одна серия предупреждает каждый день — M2 считает episodes и объём работы.
4. Нет реальных positives или нет alerts — M2 возвращает undefined metric, не 100%.
5. Новая версия модели просмотрела test при tuning — M2/M3 требуют новый sealed period.

## File map

| Файл | Назначение |
|---|---|
| ml/monitoring.py | Compatibility entry point существующего эксперимента |
| ml/monitoring_contracts.py — новый | Aggregate series, split, metric/result types |
| ml/evaluation/monitoring.py — новый | Walk-forward scoring и episode metrics |
| ml/evaluation/admission.py — новый | Pure release-policy decision |
| ml/configs/monitoring_evaluation.json — новый | Frozen protocol, не секреты |
| tests/monitoring/test_temporal_protocol.py — новый | Полнота и отсутствие leakage |
| tests/monitoring/test_alert_metrics.py — новый | Episode precision/recall/volume |
| tests/monitoring/test_admission.py — новый | Negative release gates |
| docs/ml/MONITORING_EVALUATION_PROTOCOL.md — новый | Формулы и владелец acceptance policy |
| docs/ml/MONITORING_EVALUATION_REPORT.md — новый | Реальный результат, ограничения |

## Task M1: Temporal protocol и корректный вход

**Files:** create monitoring_contracts.py, evaluation/monitoring.py,
configs/monitoring_evaluation.json, tests/monitoring/test_temporal_protocol.py;
modify monitoring.py, tests/monitoring/test_monitoring.py.

**Interfaces:** consumes D1 confirmed_complete_through и approved daily aggregates;
produces daily series with separate observed/unknown coverage and frozen SplitSpec.
Нейтральные dataclasses не импортируют app, SQLAlchemy или FastAPI.

~~~python
from dataclasses import dataclass
from datetime import date, timedelta

@dataclass(frozen=True)
class DailyObservation:
    day: date
    value: int | None
    delivery_complete: bool

@dataclass(frozen=True)
class SplitSpec:
    train_end: date
    validation_end: date
    test_end: date
    horizon_days: int = 7

def label_within_training(origin: date, split: SplitSpec) -> bool:
    return origin + timedelta(days=split.horizon_days) <= split.train_end
~~~

- [ ] Write boundary tests:

~~~python
def test_training_origin_cannot_use_validation_outcome():
    from datetime import date
    from ml.monitoring_contracts import SplitSpec, label_within_training
    split = SplitSpec(date(2025, 3, 3), date(2025, 3, 17), date(2025, 3, 31))
    assert label_within_training(date(2025, 2, 24), split)
    assert not label_within_training(date(2025, 2, 25), split)
~~~

- [ ] Run python -m pytest tests/monitoring/test_temporal_protocol.py -q; expected FAIL.
- [ ] Extract only the touched temporal functions from monitoring.py, keeping its
  train/predict interfaces available to existing pilot. Implement SplitSpec ordering,
  label-boundary validation and explicit coverage mask.
- [ ] Replace hardcoded exactly-three-files assumption in the new experiment path
  with manifest-based approved aggregates. Keep legacy reproduction path clearly
  versioned so prior Q1 report remains reproducible.
- [ ] No-record day becomes zero only when supplier completeness establishes zero
  within reporting population. Add paired tests: confirmed zero accepted; absent
  incomplete day → INSUFFICIENT_DATA, no forecast substituted.
- [ ] Test future mutation invariance: changing values after origin cannot alter
  features, mapping/eligibility at that origin or earlier predictions. Organization
  eligibility uses training-only data; changing future labels cannot enroll a hospital.
- [ ] Freeze manifest hashes, split dates, timezone, feature schema, mapping version,
  code commit, estimator parameters/random seed and dependency versions in protocol.
- [ ] Run tests/monitoring and ml/tests; commit: feat: add leakage-safe monitoring evaluation protocol.

**Приёмка:** training labels не пересекают validation, unknown supply не становится
спросом 0, и повторный эксперимент имеет идентичный dataset/protocol fingerprint.

## Task M2: Episode quality, uncertainty и release gate

**Files:** create evaluation/admission.py, tests/monitoring/test_alert_metrics.py,
tests/monitoring/test_admission.py; modify evaluation/monitoring.py,
configs/monitoring_evaluation.json; create docs/ml/MONITORING_EVALUATION_PROTOCOL.md.

**Interfaces:** episode identity = approved organization + seven-day non-overlapping
evaluation window. Reference period и growth-label policy зафиксированы до test.
Для daily replay дополнительно report consecutive-alert clusters; не смешивать
число дней-alerts с числом независимых weekly episodes.

~~~python
from dataclasses import dataclass

@dataclass(frozen=True)
class AlertCounts:
    tp: int
    fp: int
    fn: int
    tn: int

def precision(counts: AlertCounts) -> float | None:
    return counts.tp / (counts.tp + counts.fp) if counts.tp + counts.fp else None

def recall(counts: AlertCounts) -> float | None:
    return counts.tp / (counts.tp + counts.fn) if counts.tp + counts.fn else None
~~~

Admission inputs: approved policy version/sign-off, independent-period flag,
coverage evidence, counts, forecast metrics, baseline metrics, alerts per org-week
and sample support. Output status exactly one of POLICY_NOT_APPROVED,
INSUFFICIENT_DATA, FAIL, PASS; return structured reason_codes and policy snapshot.
Function signature:
evaluate_admission(report: dict[str, object], policy: dict[str, object]) -> dict[str, object].
Input keys validated at boundary; malformed report/policy raises ValueError.

- [ ] Add tests: AlertCounts(6,8,142,0) → precision 6/14, recall 6/148.
  No positives → recall None; no predictions → precision None. Zero actual WAPE
  remains None and cannot be counted as zero error.
- [ ] Add minimum release-gate test:

~~~python
def test_no_approved_policy_cannot_promote_a_model():
    from ml.evaluation.admission import evaluate_admission
    result = evaluate_admission(
        {"independent_test": False, "coverage_complete": False},
        {"approved": False, "version": "draft-v1"},
    )
    assert result["status"] == "POLICY_NOT_APPROVED"
    assert result["reason_codes"] == ["OWNER_ACCEPTANCE_REQUIRED"]
~~~

- [ ] Implement metrics and admission in that order. Policy approval precedes numerical
  comparison; new holdout and sufficient support precede PASS. Approved policies must
  supply min_precision, min_recall, max_false_alerts_per_org_week, min_positive_episodes,
  min_organizations, min_evaluation_windows and max_forecast_error_vs_baseline.
  These are required, not defaulted to favorable values.
- [ ] Add tests for invalid bounds, low support, missing policy fields, false
  independence claim and failed single threshold. All conditions are conjunctive.
- [ ] Report uncertainty with bootstrap resampling by time blocks and organization
  clusters, fixed seed. If too few independent blocks, interval is unavailable with
  reason. Don't treat 1674 correlated organization/dates as 1674 independent trials.
- [ ] Record thresholds 20/35/50 as existing policy and 72h/168h as freshness policy;
  proposal to change them uses a new version selected on validation only.
- [ ] Run python -m pytest tests/monitoring -q; commit: feat: gate model admission on independent alert evidence.

**Приёмка:** относительное улучшение MAE само по себе не даёт PASS; отчёт показывает
пропуски, false alarms, нагрузку на координатора и ограничения оценки.

## Task M3: Контролируемый эксперимент и решение

**Files:** modify ml/monitoring.py only for parameterized experiments already described;
create docs/ml/MONITORING_EVALUATION_REPORT.md;
artifacts written only to ignored local/object-storage location.

**Interfaces:** consumes frozen protocol M1, metrics/admission M2, owner-approved D1
delivery and D2 mapping. Produces model manifest, report, admission decision and hash.

- [ ] Проверить availability новых непросмотренных данных. Если их нет, записать
  INSUFFICIENT_DATA; технические fixtures не выдавать за improvement доказательство.
- [ ] На train/validation сравнить weekly-naive, moving-average и существующий
  HistGradientBoosting. Не добавлять новую библиотеку ради числа кандидатов.
  Анализ ошибок: большие/малые организации, holidays только при verified calendar,
  резкие обрывы и supply completeness.
- [ ] Согласовать численные критерии с процессным владельцем и заморозить выбранную
  model/policy до открытия test. Не использовать test для выбора baseline.
- [ ] Выполнить единственный final evaluation выбранной конфигурации; сохранить
  все поля протокола, per-window metrics и причины admission. Следующая итерация
  после просмотра результатов требует нового test или маркировки exploratory.
- [ ] Сверить reproducibility повторным inference по сохранённому trusted artifact,
  не повторным подбором модели. Сохранять источники только как aggregate hashes/
  periods/counts без patient records.
- [ ] Commit report: docs: record independent monitoring evaluation decision.

**Приёмка:** PASS либо честный FAIL/INSUFFICIENT_DATA. При отрицательном результате
основной продукт остаётся descriptive analytics + rule-based quality/freshness;
research replay не становится operational forecast.
