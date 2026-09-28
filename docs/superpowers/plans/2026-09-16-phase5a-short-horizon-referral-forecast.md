# Phase 5A Short-Horizon Referral Forecast Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an auditable seven-day global referral-flow forecast that compares three baselines with one simple ML model and exposes only persisted, scope-safe results.

**Architecture:** Pure forecasting computations live in `ml/`; backend business ports orchestrate ClickHouse history, ML evaluation, PostgreSQL persistence and MLflow adapters. Training is background/CLI, while the API only retrieves append-only forecasts.

**Tech Stack:** Python 3.12, scikit-learn, NumPy, MLflow, FastAPI, SQLAlchemy/Alembic, ClickHouse, Celery, Next.js, TanStack Query, ECharts, Zod.

**Spec:** `docs/superpowers/specs/2026-09-16-phase5a-short-horizon-referral-forecast-design.md`

## Global Constraints

- Forecast only daily planned-hospitalization referral volume for seven days.
- Current Phase 5A scope is GLOBAL because authoritative referral-region mapping is absent.
- Do not use random train/test split or future target values in features.
- Do not claim annual seasonality, overload, bed availability or patient-level prediction.
- ML is selected only when MAE and WAPE each improve by at least 2% over the strongest baseline.
- Forecasts are append-only and carry model and import provenance.
- Only global-scope users may read the Phase 5A global forecast.

---

### Task 1: Pure forecasting dataset and metrics

**Files:**
- Create: `ml/contracts.py`, `ml/dataset.py`, `ml/metrics.py`, `ml/validation.py`
- Test: `ml/tests/test_dataset.py`, `ml/tests/test_metrics.py`, `ml/tests/test_validation.py`

**Interfaces:** Produces dense daily series, `referrals_daily_v1` feature rows, chronological folds and metric functions used by every candidate.

- [ ] Write tests for aggregation, missing dates, lags, rolling windows, leakage, deterministic folds and WAPE zero denominator.
- [ ] Run the tests and confirm failure because the modules do not exist.
- [ ] Implement the smallest deterministic contracts and functions that pass.
- [ ] Run the focused tests and refactor while green.

### Task 2: Baselines, ML candidate and selection gate

**Files:**
- Create: `ml/baselines.py`, `ml/model.py`, `ml/evaluation.py`, `ml/selection.py`
- Test: `ml/tests/test_baselines.py`, `ml/tests/test_evaluation.py`, `ml/tests/test_selection.py`

**Interfaces:** Produces candidate evaluation with per-fold and overall MAE/WAPE/RMSE, selected candidate and seven-day recursive forecast.

- [ ] Write failing tests for all baselines, equal folds, ML win, baseline win and near-equal baseline preference.
- [ ] Implement naive-1, naive-7, moving-average-7 and one `HistGradientBoostingRegressor`.
- [ ] Implement the 2% dual-primary-metric gate and deterministic tie-breakers.
- [ ] Run all `ml/tests`.

### Task 3: Forecast persistence and repositories

**Files:**
- Create: `backend/alembic/versions/0004_ml_foundation.py`, `backend/app/models/model_version.py`, `backend/app/models/forecast_point.py`
- Modify: `backend/app/models/analytics.py`, `backend/app/models/enums.py`, `backend/app/business/ports.py`, `backend/app/repositories/analytics.py`, `backend/app/repositories/unit_of_work.py`
- Test: `backend/tests/unit/test_forecast_repository.py`

**Interfaces:** Produces append-only model versions, forecast headers and ordered forecast points with scope/model/watermark metadata.

- [ ] Write repository tests for append-only versioning and metadata.
- [ ] Add migration and models without editing accepted migrations.
- [ ] Extend the UoW port and SQLAlchemy implementation.
- [ ] Verify upgrade/downgrade on a clean test database.

### Task 4: Business contracts, adapters and training orchestration

**Files:**
- Create: `backend/app/business/forecasting/contracts.py`, `ports.py`, `service.py`, `backend/app/repositories/clickhouse_forecasting.py`, `backend/app/repositories/forecast_metadata.py`, `backend/app/adapters/forecasting.py`
- Test: `backend/tests/unit/test_forecast_service.py`, `test_clickhouse_forecasting_repository.py`

**Interfaces:** `ForecastTrainingService.run_referral_forecast()` and `ForecastQueryService.latest_referral_forecast(context)`.

- [ ] Write failing tests for global-scope access, missing forecast, watermark propagation and atomic persistence.
- [ ] Implement ClickHouse daily aggregation and completed-import watermark lookup.
- [ ] Adapt the pure ML engine behind the business port and persist the selected result.
- [ ] Ensure backend business code imports neither scikit-learn nor MLflow.

### Task 5: MLflow, worker and commands

**Files:**
- Create: `ml/tracking.py`, `ml/cli.py`, `ml/requirements.txt`, `infrastructure/ml/Dockerfile`
- Modify: `backend/app/workers/tasks.py`, `docker-compose.yml`, `Makefile`, `.env.example`
- Test: `ml/tests/test_tracking.py`, `backend/tests/unit/test_forecast_task.py`

**Interfaces:** `python -m ml.cli train-referrals` and Celery task `medsignal.train_referral_forecast`.

- [ ] Write tests with a local MLflow file store/fake tracker before implementation.
- [ ] Track parameters, fold/overall metrics, watermark and selected artifact.
- [ ] Add ML-only image so API dependencies remain small.
- [ ] Add reproducible Make targets for train and forecast generation.

### Task 6: Forecast API and security

**Files:**
- Create: `backend/app/api/v1/forecasts.py`, `backend/app/schemas/forecasting.py`
- Modify: `backend/app/api/deps.py`, `backend/app/api/v1/router.py`, `backend/app/composition.py`
- Test: `backend/tests/integration/test_forecast_api.py`

**Interfaces:** `GET /api/v1/forecasts/referrals/latest`.

- [ ] Write failing API tests for success, 401, non-global 404, missing result and stale-data metadata.
- [ ] Implement strict Pydantic response contracts and route wiring.
- [ ] Verify no SQL/ML library reaches the route.

### Task 7: Minimal Situation Center forecast panel

**Files:**
- Create: `frontend/src/features/forecasting/{api,hooks,types}.ts`, `frontend/src/features/forecasting/components/referral-forecast-card.tsx`
- Modify: `frontend/src/app/dashboard/page.tsx`
- Test: `frontend/src/features/forecasting/components/referral-forecast-card.test.tsx`

**Interfaces:** Zod-validated forecast response and an accessible chart/table card.

- [ ] Write failing loading/success/unavailable/error/limitation tests.
- [ ] Add API schema, query hook and dashboard card.
- [ ] Verify the UI never uses overload, confidence or recommendation language.

### Task 8: Documentation, architecture and real-data verification

**Files:**
- Create: `docs/ADR/0016-experimental-short-horizon-referral-forecast.md`, `docs/ml/REFERRAL_FORECASTING.md`, `docs/ml/MODEL_EVALUATION.md`
- Modify: `README.md`, `docs/ML_ARCHITECTURE.md`, `docs/API.md`, `docs/DATABASE.md`, `docs/ADR/README.md`, `.importlinter`

**Interfaces:** Reproduction commands and evidence for target, folds, metrics, selection, MLflow and limitations.

- [ ] Document why GLOBAL is the only defensible current scope and preserve the long-term prohibition.
- [ ] Run backend, ML, pipeline, architecture and frontend checks.
- [ ] Run training against current ClickHouse, record real comparison without patient-level data, and verify persisted/API output.
- [ ] Run the production frontend build and report exact results and blockers.

