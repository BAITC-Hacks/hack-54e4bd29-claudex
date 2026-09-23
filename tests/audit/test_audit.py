"""Тесты инструментов Data Audit.

Проверяются свойства, от которых зависит достоверность отчёта: источник
не изменяется, метрики считаются по всем частям выгрузки сразу, чувствительные
значения наружу не выходят, дорогие проверки честно отмечаются пропущенными.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_pipeline.audit import cli
from data_pipeline.audit.excel_profiler import profile_workbook
from data_pipeline.audit.fingerprint import duplicate_groups, fingerprint_files, hash_file
from data_pipeline.audit.inventory import build_inventory
from data_pipeline.audit.joinability import JoinRole, assess, collect_key_values
from data_pipeline.audit.privacy import (
    RiskLevel,
    Sensitivity,
    classify,
    is_value_safe_to_publish,
)
from data_pipeline.audit.profiler import profile_table
from data_pipeline.audit.quality import check_table
from data_pipeline.audit.target_analysis import (
    TableEvidence,
    assess_candidates,
    recommend,
)
from data_pipeline.audit.temporal import analyze_table


def _referrals(source_root: Path) -> list[Path]:
    return [source_root / "Направления" / "Направления.csv"]


def _parts(source_root: Path) -> list[Path]:
    return sorted((source_root / "Большая выгрузка").glob("*.csv"))


def _profile(paths: list[Path], name: str = "Набор"):
    size = sum(p.stat().st_size for p in paths)
    return profile_table(name, name, paths, size)


# --- Опись ------------------------------------------------------------------


def test_inventory_counts_every_file(source_root: Path) -> None:
    inventory = build_inventory(source_root)
    on_disk = [p for p in source_root.rglob("*") if p.is_file()]
    assert inventory.total_files == len(on_disk)
    assert inventory.total_size_bytes == sum(p.stat().st_size for p in on_disk)


def test_inventory_reads_provider_description(source_root: Path) -> None:
    inventory = build_inventory(source_root)
    referrals = next(d for d in inventory.datasets if d.name == "Направления")
    assert referrals.description is not None
    assert "госпитализац" in referrals.description


def test_inventory_recognises_parts(source_root: Path) -> None:
    inventory = build_inventory(source_root)
    parts = [f for f in inventory.files if f.part_total is not None]
    assert {f.part_index for f in parts} == {1, 2}
    assert all(f.part_total == 2 for f in parts)


def test_inventory_reports_missing_part(tmp_path: Path) -> None:
    """Неполная выгрузка должна быть видна до чтения содержимого."""
    root = tmp_path / "src"
    (root / "Набор").mkdir(parents=True)
    (root / "Набор" / "Набор_part_002_of_003.csv").write_text("a\n1\n", encoding="utf-8")
    inventory = build_inventory(root)
    notes = inventory.datasets[0].notes
    assert any("отсутствуют номера 1, 3" in note for note in notes)


# --- Отпечатки --------------------------------------------------------------


def test_fingerprint_is_stable_and_detects_identical_content(tmp_path: Path) -> None:
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    first.write_text("x\n1\n", encoding="utf-8")
    second.write_text("x\n1\n", encoding="utf-8")
    assert hash_file(first) == hash_file(second)
    groups = duplicate_groups(fingerprint_files(tmp_path, ["a.csv", "b.csv"]))
    assert list(groups.values()) == [["a.csv", "b.csv"]]


def test_fingerprint_changes_with_content(tmp_path: Path) -> None:
    path = tmp_path / "a.csv"
    path.write_text("x\n1\n", encoding="utf-8")
    before = hash_file(path)
    path.write_text("x\n2\n", encoding="utf-8")
    assert hash_file(path) != before


# --- Профилирование ---------------------------------------------------------


def test_profiling_does_not_modify_source(source_root: Path) -> None:
    """Главное правило аудита проверяется тестом, а не только намерением."""
    before = {
        p: (p.stat().st_size, hash_file(p)) for p in source_root.rglob("*") if p.is_file()
    }
    _profile(_referrals(source_root))
    after = {
        p: (p.stat().st_size, hash_file(p)) for p in source_root.rglob("*") if p.is_file()
    }
    assert before == after


def test_parts_are_profiled_as_one_table(source_root: Path) -> None:
    paths = _parts(source_root)
    assert len(paths) == 2
    profile = _profile(paths)
    assert profile.row_count == 240


def test_detects_datetime_and_numeric_columns(source_root: Path) -> None:
    profile = _profile(_referrals(source_root))
    types = {c.column_name: c.inferred_type for c in profile.columns}
    assert types["registration_dt"] == "datetime"
    assert types["hospitalization_dt"] == "datetime"
    assert types["amount"] == "integer"
    assert types["bed_profile"] == "string"


def test_null_statistics_are_reported(tmp_path: Path) -> None:
    path = tmp_path / "n.csv"
    path.write_text("a,b\n1,\n2,\n3,x\n", encoding="utf-8")
    profile = _profile([path])
    b = next(c for c in profile.columns if c.column_name == "b")
    assert b.null_count == 2
    assert b.null_percentage == pytest.approx(66.6667, abs=0.01)
    assert b.nullable is True


def test_sensitive_string_values_are_withheld(source_root: Path) -> None:
    """Значения столбца с кодом случая в профиль не попадают."""
    profile = _profile(_referrals(source_root))
    column = next(c for c in profile.columns if c.column_name == "hospitalization_code")
    assert column.value_sample_withheld is True
    assert column.min_value is None
    assert column.max_value is None


def test_reference_column_values_are_published(source_root: Path) -> None:
    profile = _profile(_referrals(source_root))
    column = next(c for c in profile.columns if c.column_name == "region_in")
    assert column.value_sample_withheld is False
    assert column.min_value is not None


def test_large_table_switches_to_approximate_metrics(
    source_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Порог объёма переключает режим, а не роняет прогон."""
    monkeypatch.setattr("data_pipeline.audit.profiler.EXACT_METRICS_LIMIT_BYTES", 10)
    profile = _profile(_referrals(source_root))
    assert profile.exact_metrics is False
    assert all(c.unique_is_approximate for c in profile.columns)
    assert any("SKIPPED_DUE_TO_RESOURCE_LIMIT" in s for s in profile.skipped_metrics)


# --- Качество ---------------------------------------------------------------


def test_duplicate_rows_are_found(source_root: Path) -> None:
    paths = _referrals(source_root)
    quality = check_table(_profile(paths), paths)
    assert quality.duplicate_rows == 1


def test_impossible_negative_value_is_critical(source_root: Path) -> None:
    paths = _referrals(source_root)
    quality = check_table(_profile(paths), paths)
    findings = [f for f in quality.findings if f.check == "IMPOSSIBLE VALUES"]
    assert [f.column for f in findings] == ["amount"]
    assert findings[0].severity == "CRITICAL"


def test_inconsistent_category_spelling_is_reported(source_root: Path) -> None:
    paths = _referrals(source_root)
    quality = check_table(_profile(paths), paths)
    checks = {f.check for f in quality.findings}
    assert "INCONSISTENT CATEGORY SPELLING" in checks


def test_constant_column_is_reported(source_root: Path) -> None:
    paths = _referrals(source_root)
    quality = check_table(_profile(paths), paths)
    constant = [f for f in quality.findings if f.check == "CONSTANT COLUMN"]
    assert [f.column for f in constant] == ["sdu_load_date"]


def test_expensive_checks_are_marked_skipped(
    source_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("data_pipeline.audit.quality.EXPENSIVE_CHECK_LIMIT_BYTES", 10)
    paths = _referrals(source_root)
    quality = check_table(_profile(paths), paths)
    assert quality.duplicate_rows is None
    assert quality.duplicate_rows_status == "SKIPPED_DUE_TO_RESOURCE_LIMIT"
    assert any("SKIPPED_DUE_TO_RESOURCE_LIMIT" in s for s in quality.skipped_checks)


# --- Время ------------------------------------------------------------------


def test_date_coverage_is_measured(source_root: Path) -> None:
    paths = _referrals(source_root)
    profile = _profile(paths)
    date_columns = {
        c.column_name: c.datetime_format
        for c in profile.columns
        if c.inferred_type == "datetime" and c.datetime_format
    }
    result = analyze_table("Набор", "Набор", paths, date_columns)
    assert result.primary_date_column == "registration_dt"
    assert result.time_series_possible is True
    registration = next(c for c in result.columns if c.column_name == "registration_dt")
    assert registration.min_date == "2024-01-01"
    assert registration.distinct_months >= 9


def test_history_depth_follows_primary_axis(source_root: Path) -> None:
    """Глубина истории берётся по оси ряда, а не по самой длинной дате.

    Плановая или фактическая дата уходит вперёд от даты регистрации,
    и максимум по всем столбцам показал бы историю, которой в данных нет.
    """
    paths = _referrals(source_root)
    profile = _profile(paths)
    date_columns = {
        c.column_name: c.datetime_format
        for c in profile.columns
        if c.inferred_type == "datetime" and c.datetime_format
    }
    result = analyze_table("Набор", "Набор", paths, date_columns)
    registration = next(c for c in result.columns if c.column_name == "registration_dt")
    admission = next(c for c in result.columns if c.column_name == "hospitalization_dt")
    assert admission.distinct_months > registration.distinct_months
    assert cli._months_covered(result) == registration.distinct_months


def test_load_timestamp_is_not_chosen_as_axis(source_root: Path) -> None:
    """Отметка выгрузки одинакова во всех строках и осью ряда быть не может."""
    paths = _referrals(source_root)
    profile = _profile(paths)
    date_columns = {
        c.column_name: c.datetime_format
        for c in profile.columns
        if c.inferred_type == "datetime" and c.datetime_format
    }
    result = analyze_table("Набор", "Набор", paths, date_columns)
    assert result.primary_date_column != "sdu_load_date"
    load = next(c for c in result.columns if c.column_name == "sdu_load_date")
    assert load.granularity == "single snapshot"


def test_missing_dates_yield_no_series(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    path.write_text("a\n1\n2\n", encoding="utf-8")
    result = analyze_table("Набор", "Набор", [path], {})
    assert result.time_series_possible is False
    assert result.primary_date_column is None


# --- Приватность ------------------------------------------------------------


@pytest.mark.parametrize(
    ("column", "risk"),
    [
        ("patient_iin", RiskLevel.CRITICAL),
        ("ФИО", RiskLevel.CRITICAL),
        ("phone_number", RiskLevel.CRITICAL),
        ("number_card", RiskLevel.HIGH),
        ("hospitalization_code", RiskLevel.HIGH),
        ("icd10", RiskLevel.MEDIUM),
        ("region_in", RiskLevel.NONE),
    ],
)
def test_sensitive_columns_are_detected(column: str, risk: RiskLevel) -> None:
    assert classify(column).risk_level == risk.value


def test_classification_carries_no_values() -> None:
    """В результате классификации нет места ни одному значению."""
    result = classify("patient_iin", non_null_count=10, unique_count=10)
    payload = result.to_dict()
    assert set(payload) == {
        "column_name",
        "detected_type",
        "sensitivity",
        "risk_level",
        "handling",
        "rationale",
        "non_null_count",
        "unique_count",
        "unique_is_approximate",
    }


def test_only_reference_columns_may_publish_values() -> None:
    assert is_value_safe_to_publish("region_in") is True
    assert is_value_safe_to_publish("hospital_mo") is True
    assert is_value_safe_to_publish("diagnosis_name") is False
    assert is_value_safe_to_publish("patient_iin") is False


def test_diagnosis_is_sensitive_not_personal() -> None:
    assert classify("icd10").sensitivity == Sensitivity.SENSITIVE.value


# --- Связуемость ------------------------------------------------------------


def test_overlapping_keys_give_strong_join(source_root: Path) -> None:
    left = collect_key_values(
        "Направления",
        _referrals(source_root),
        "referring_mo",
        JoinRole.HOSPITAL,
    )
    right = collect_key_values(
        "Большая выгрузка",
        _parts(source_root),
        "medicine_organization_code",
        JoinRole.HOSPITAL,
    )
    result = assess(left, right)
    assert result.overlap == 3
    assert result.strength == "STRONG JOIN"


def test_disjoint_keys_give_no_join(tmp_path: Path) -> None:
    left_path = tmp_path / "l.csv"
    right_path = tmp_path / "r.csv"
    left_path.write_text("org_in\nAAA\nBBB\n", encoding="utf-8")
    right_path.write_text("org_in\nCCC\nDDD\n", encoding="utf-8")
    left = collect_key_values("L", [left_path], "org_in", JoinRole.HOSPITAL)
    right = collect_key_values("R", [right_path], "org_in", JoinRole.HOSPITAL)
    assert assess(left, right).strength == "NO JOIN"


# --- Excel ------------------------------------------------------------------


def test_workbook_sheets_are_described(source_root: Path) -> None:
    path = source_root / "Справочник" / "Справочник.xlsx"
    book = profile_workbook("Справочник", path)
    assert book.sheet_count == 2
    main = next(s for s in book.sheets if s.sheet_name == "Справочник")
    assert main.leading_empty_rows == 1
    assert main.header_row_index == 2
    assert main.headers == ["Код", "Наименование"]
    assert main.looks_like_reference is True


def test_workbook_is_not_modified(source_root: Path) -> None:
    path = source_root / "Справочник" / "Справочник.xlsx"
    before = hash_file(path)
    profile_workbook("Справочник", path)
    assert hash_file(path) == before


# --- Кандидаты на цель ------------------------------------------------------


def _evidence(columns: tuple[str, ...], months: int = 24) -> TableEvidence:
    return TableEvidence(
        dataset="Набор",
        table="Набор",
        columns=columns,
        row_count=1000,
        months_covered=months,
        granularity="event-level",
        time_series_possible=months >= 3,
    )


def test_waiting_time_needs_both_dates_in_one_table() -> None:
    with_both = assess_candidates(
        [_evidence(("registration_dt", "hospitalization_dt", "hospital_mo"))]
    )
    candidate = next(c for c in with_both if c.key == "waiting_time_days")
    assert candidate.status == "AVAILABLE"

    without_end = assess_candidates([_evidence(("registration_dt", "hospital_mo"))])
    candidate = next(c for c in without_end if c.key == "waiting_time_days")
    assert candidate.status == "NOT AVAILABLE"
    assert "queue_end" in candidate.reason


def test_requirement_in_another_table_needs_denominator_alignment() -> None:
    """Величина, требующая join'а, не должна объявляться наблюдаемой."""
    candidates = assess_candidates(
        [
            TableEvidence(
                dataset="Отказы",
                table="Отказы",
                columns=("refuse_dt", "org_in"),
                row_count=100,
                months_covered=24,
                granularity="event-level",
                time_series_possible=True,
            ),
            TableEvidence(
                dataset="Направления",
                table="Направления",
                columns=("registration_dt", "hospital_mo"),
                row_count=100,
                months_covered=24,
                granularity="event-level",
                time_series_possible=True,
            ),
        ]
    )
    candidate = next(c for c in candidates if c.key == "refusal_rate")
    assert candidate.status == "NOT AVAILABLE"
    assert "DENOMINATOR_NOT_ALIGNED" in candidate.reason


def test_history_is_not_borrowed_from_an_unrelated_dataset() -> None:
    """Глубина истории берётся у опорной таблицы, а не у самой длинной.

    Иначе кандидат, опирающийся на срез без периода, унаследует историю
    постороннего набора данных и будет объявлен прогнозируемым.
    """
    candidates = assess_candidates(
        [
            TableEvidence(
                dataset="Пролеченные",
                table="Пролеченные",
                columns=("discharged_total", "medicine_organization"),
                row_count=2000,
                months_covered=0,
                granularity="single snapshot",
                time_series_possible=False,
            ),
            TableEvidence(
                dataset="Вакцинация",
                table="Вакцинация",
                columns=("vaccination_date", "medicine_organization_code"),
                row_count=10_000,
                months_covered=163,
                granularity="event-level",
                time_series_possible=True,
            ),
        ]
    )
    candidate = next(c for c in candidates if c.key == "treated_cases")
    assert candidate.supporting_tables == ["Пролеченные.Пролеченные"]
    assert candidate.feasibility == "NOT FEASIBLE"


def test_missing_ground_truth_blocks_overload_proxy() -> None:
    candidates = assess_candidates(
        [_evidence(("registration_dt", "refuse_dt", "bed_days", "hospital_mo"))]
    )
    candidate = next(c for c in candidates if c.key == "overload_risk_proxy")
    assert candidate.status == "NOT AVAILABLE"


def test_short_history_downgrades_feasibility() -> None:
    candidates = assess_candidates(
        [_evidence(("registration_dt", "hospital_mo"), months=6)]
    )
    candidate = next(c for c in candidates if c.key == "incoming_referrals")
    assert candidate.status == "AVAILABLE"
    assert candidate.feasibility == "WEAK"


def test_recommendation_is_deferred_when_no_candidate_qualifies() -> None:
    candidates = assess_candidates([_evidence(("some_column",), months=1)])
    target, reason = recommend(candidates)
    assert target is None
    assert "DEFERRED" in reason


# --- Прогон целиком ---------------------------------------------------------


def test_cli_produces_all_artifacts(source_root: Path, tmp_path: Path) -> None:
    output = tmp_path / "audit"
    docs = tmp_path / "docs"
    arguments = [
        "--source",
        str(source_root),
        "--output",
        str(output),
        "--docs",
        str(docs),
    ]
    assert cli.main(arguments) == 0

    for name in (
        "inventory.json",
        "inventory.csv",
        "schema_catalog.json",
        "quality_summary.json",
        "temporal_coverage.json",
        "joinability.json",
        "privacy_audit.json",
        "file_fingerprints.json",
        "medsignal_audit_summary.json",
    ):
        assert (output / name).is_file(), name

    for name in (
        "DATA_AUDIT_REPORT.md",
        "SCHEMA_CATALOG.md",
        "DATA_QUALITY_REPORT.md",
        "TARGET_FEASIBILITY.md",
        "JOINABILITY_REPORT.md",
        "PRIVACY_AUDIT.md",
        "CANONICAL_DATA_MODEL_PROPOSAL.md",
        "CLICKHOUSE_DESIGN_PROPOSAL.md",
        "TIME_COVERAGE.md",
        "DATA_INVENTORY.md",
        "REGION_MAPPING_ANALYSIS.md",
        "HOSPITAL_MAPPING_ANALYSIS.md",
        "FEATURE_CANDIDATES.md",
    ):
        assert (docs / name).is_file(), name


def test_cli_leaves_source_untouched(source_root: Path, tmp_path: Path) -> None:
    before = {
        str(p.relative_to(source_root)): hash_file(p)
        for p in source_root.rglob("*")
        if p.is_file()
    }
    cli.main(
        [
            "--source",
            str(source_root),
            "--output",
            str(tmp_path / "a"),
            "--docs",
            str(tmp_path / "d"),
        ]
    )
    after = {
        str(p.relative_to(source_root)): hash_file(p)
        for p in source_root.rglob("*")
        if p.is_file()
    }
    assert before == after


def test_excel_headers_reach_the_privacy_audit(source_root: Path, tmp_path: Path) -> None:
    """Формат хранения не должен выводить выгрузку из-под классификации."""
    output = tmp_path / "audit"
    cli.main(
        [
            "--source",
            str(source_root),
            "--output",
            str(output),
            "--docs",
            str(tmp_path / "d"),
        ]
    )
    rows = json.loads((output / "privacy_audit.json").read_text(encoding="utf-8"))
    from_excel = [r for r in rows["columns"] if r["dataset"] == "Справочник"]
    assert from_excel
    assert {r["column_name"] for r in from_excel} == {"Код", "Наименование"}


def test_disconnected_hospital_clusters_are_reported() -> None:
    """Связь внутри группы не отменяет отсутствия связи между группами."""
    from types import SimpleNamespace

    from data_pipeline.audit import report

    def key(dataset: str) -> SimpleNamespace:
        return SimpleNamespace(dataset=dataset, role="hospital", column="org")

    def edge(left: str, right: str, strength: str) -> SimpleNamespace:
        return SimpleNamespace(
            role="hospital",
            left_dataset=left,
            right_dataset=right,
            strength=strength,
        )

    ctx = report.AuditContext(
        audit_version="test",
        source_root="",
        inventory=SimpleNamespace(
            total_files=0, total_size_bytes=0, datasets=[], files=[]
        ),
        profiles=[],
        workbooks=[],
        temporal=[],
        quality=[],
        privacy=[],
        classifications=[],
        key_values=[key("A"), key("B"), key("C")],
        join_assessments=[
            edge("A", "B", "STRONG JOIN"),
            edge("A", "C", "NO JOIN"),
            edge("B", "C", "NO JOIN"),
        ],
        join_matrix={},
        candidates=[],
        recommended_target=None,
        recommendation_reason="",
    )
    clusters = report._hospital_clusters(ctx)
    assert clusters == [{"A", "B"}, {"C"}]
    assert any("несвязанные группы" in gap for gap in report._critical_gaps(ctx))


def test_summary_is_self_contained(source_root: Path, tmp_path: Path) -> None:
    """Сводка должна быть пригодна к передаче без исходных выгрузок."""
    output = tmp_path / "audit"
    cli.main(
        [
            "--source",
            str(source_root),
            "--output",
            str(output),
            "--docs",
            str(tmp_path / "d"),
        ]
    )
    summary = json.loads(
        (output / "medsignal_audit_summary.json").read_text(encoding="utf-8")
    )
    assert summary["total_files"] > 0
    assert summary["datasets"]
    assert "critical_gaps" in summary
    assert "phase3b_recommendations" in summary
    # Путь к источнику и значения строк в сводку не попадают.
    serialised = json.dumps(summary, ensure_ascii=False)
    assert str(source_root) not in serialised
