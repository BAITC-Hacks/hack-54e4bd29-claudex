# Local Synthetic Demo Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make one isolated local MedSignal stack show a coherent, explicitly synthetic Kazakhstan dataset through its real authenticated APIs on the map and the rest of the product.

**Architecture:** A new local-demo profile, separate from the exact-count Phase 8 acceptance fixture, defines 12 canonical regions and fictional organizations. Deterministic source deliveries pass through the existing manifest approval, import, mapping, analytics, and forecast pipeline; the frontend map displays only the resulting API region aggregates. A fresh `phase8-*` project proves the result before any local `:8080` rollover.

**Tech Stack:** Python 3.12, SQLAlchemy/PostgreSQL, ClickHouse, existing data pipeline and Compose launcher, Next.js/React/TypeScript, Vitest, Playwright, Keycloak.

**Spec:** [2026-09-30-local-synthetic-demo-data-design.md](../specs/2026-09-30-local-synthetic-demo-data-design.md)

## Global Constraints

- Local-only: `APP_ENV=local`, frontend build args `NEXT_PUBLIC_APP_ENV=test` and `NEXT_PUBLIC_SYNTHETIC_DEMO=true`; no production selector.
- Use real Keycloak, backend APIs, database, import/mapping, and forecast pipeline; no API/OIDC mocks in browser evidence, no hand-edited forecast/MAE, no paid LLM call.
- Leave `scripts/acceptance/synthetic_dataset.py`, its 2-region counts, `backend/seeds/dev_seed.py`, existing strict verifiers, forecast algorithm, API contracts, storage/auth architecture, and security gates intact.
- Keep the current local project's volumes and history. Only own new `phase8-*` project resources may be stopped; no `down -v`, prune, reset, push, main merge, or deployment.
- Never expose generated realm credentials, tokens, `.env`, patient data, or unredacted runtime output in commits or evidence. All measured values are fictional; actual Kazakhstan geography labels are permitted.
- Historical query period is 2025-01-01 through 2025-03-31. The 7-day forecast is `DAILY_REFERRAL_COUNT` at `GLOBAL` scope, and must retain its limitations about referrals versus beds/discharge/medical advice.
- On Windows, run root and backend Python test trees in separate processes with both repository root and `backend` on session-only `PYTHONPATH`, as in `docs/acceptance/PILOT_CONSOLIDATION_IMPLEMENTATION.md`; do not edit system environment variables.

## Review Focus

1. `APP_ENV` other than `local` or missing explicit profile opt-in must reject the seed/mapping operation before writes (Task 2 tests).
2. Nonempty source directory or a reused delivery ID must fail before any import, preserving existing files (Tasks 1 and 3 tests).
3. A missing, duplicate, or wrong-target source mapping must fail coverage verification rather than silently dropping a region (Tasks 2 and 4 tests).
4. Missing, failed, or suppressed API values must render loading/unavailable/suppressed states, never map-only substitute counts (Task 5 tests).
5. A missing forecast must fail the real browser/API journey rather than silently fall back to a fake card (Task 6 test). A failed `:8080` start also remains an explicit non-promotion gate in Task 6.

## File map and interfaces

| File | Responsibility |
| --- | --- |
| `backend/seeds/local_demo_profile.json` | Single reviewed list of 12 `{code,name}` Kazakhstan regions; derived canonical/source IDs use the same rule in seed and generator. |
| `scripts/local_demo/dataset.py` | Read that list, generate immutable contract-exact `REFERRALS`, `WAITING`, `REFUSALS` CSVs/manifests in a fresh project source directory; return manifest-derived counts. |
| `backend/seeds/local_demo_seed.py` | Local-only canonical regions, fictional hospitals, real test-identity scopes, and evidence-backed synthetic signals. |
| `backend/seeds/local_demo_mappings.py` | Local-only exact source→canonical decisions; check directory and mapping cardinality before publish. |
| `scripts/local_demo/bootstrap.py` | Guard fresh `phase8-*` project and invoke existing seed, approval/import, and mapping interfaces; never address another project. |
| `scripts/local_demo/verify.py` and `scripts/local_demo/verify_forecast_db.py` | Read-only manifest/API/scope and persisted forecast DB reconciliation without Phase 8 fixed totals. |
| `frontend/src/features/map/map-panel.tsx` and `frontend/src/app/command-center/page.tsx` | API-only map, scope selection, provenance, and unavailable states. |
| `frontend/src/features/map/demo-regions.ts` | Delete the independent map-only counts after their consumers are removed. |
| `frontend/e2e/local-demo.spec.ts` | Opt-in real-OIDC end-to-end coherence and persisted human action. |

The ID rule is exact and shared: each profile `code` is `KZ-<SLUG>`; canonical hospital `H-<code>`, referrals/refusals organization source `SYN-ORG-<code>`, waiting destination source `SYN-WAIT-<code>`, waiting region source `SYN-REG-<code>`, refusals region source `SYN-REF-REG-<code>`. Use the same strings in CSVs, canonical seed, and mapping approvals. Profile codes/names: `KZ-ASTANA`/Астана, `KZ-ALMATY`/Алматы, `KZ-SHYMKENT`/Шымкент, `KZ-ATYRAU`/Атырауская область, `KZ-AKTOBE`/Актюбинская область, `KZ-KARAGANDA`/Карагандинская область, `KZ-KOSTANAY`/Костанайская область, `KZ-KYZYLORDA`/Кызылординская область, `KZ-PAVLODAR`/Павлодарская область, `KZ-EAST`/Восточно-Казахстанская область, `KZ-WEST`/Западно-Казахстанская область, `KZ-MANGYSTAU`/Мангистауская область. All 12 names are already recognized by `centerFor` in `frontend/src/features/map/geography.ts`.

---

### Task 1: Deterministic local-demo deliveries

**Files:** Create `backend/seeds/local_demo_profile.json`, `scripts/local_demo/__init__.py`, `scripts/local_demo/dataset.py`, `tests/operations/test_local_demo_dataset.py`. Read `scripts/acceptance/synthetic_dataset.py` and `data_pipeline/contracts.py` for exact column names and manifest shape; do not edit them.

**Interfaces:** `scripts.local_demo.dataset.load_profile() -> tuple[dict[str, str], ...]` reads `backend/seeds/local_demo_profile.json`; `generate(root: Path) -> dict[str, int]`. The backend seed has its own `load_profile()` reading that same JSON beside its module; this avoids a Python import-path dependency between host and container. `root` is the fresh project's `source-empty`; three manifests are named `manifest-REFERRALS.json`, `manifest-WAITING.json`, `manifest-REFUSALS.json`. Each uses the current `get_contract(dataset)` column order, `source_system`, SHA-256 of the written CSV, and actual row count. Source ID rule above is the contract consumed by Task 2.

- [ ] **Step 1: Write the failing tests.** Populate the profile JSON with exactly the 12 entries listed above. Test deterministic bytes/hashes, all IDs, and no overwrite:

  ```python
  def test_local_demo_is_deterministic(tmp_path):
      left, right = tmp_path / "left", tmp_path / "right"
      counts = generate(left)
      assert counts == generate(right)
      assert set(counts) == {"REFERRALS", "WAITING", "REFUSALS"}
      for dataset in counts:
          a = json.loads((left / f"manifest-{dataset}.json").read_text())
          b = json.loads((right / f"manifest-{dataset}.json").read_text())
          assert a == b
          assert a["expected_rows"] == counts[dataset]
          source = left / get_contract(dataset).source_directory / "synthetic-local-demo.csv"
          assert a["file_hashes"] == [hashlib.sha256(source.read_bytes()).hexdigest()]

  def test_local_demo_refuses_existing_files(tmp_path):
      generate(tmp_path)
      with pytest.raises(FileExistsError):
          generate(tmp_path)
  ```

- [ ] **Step 2: Confirm RED.** Run `python -m pytest tests/operations/test_local_demo_dataset.py -q`; expect missing `scripts.local_demo.dataset` and no generated files.
- [ ] **Step 3: Implement the generator.** Use `random.Random(20250927)` and `date(2025, 1, 1)` through `date(2025, 3, 31)` inclusive. For each day generate `18 + (4 if weekday < 5 else 0) + day_index // 21 + rng.randint(-2, 2)` referral rows, distributing row `i` across the 12 profile organizations with `(day_index + i) % 12`. Generate one waiting snapshot on `2025-03-31` with `4 + region_index % 3` rows per organization, and one refusal per region every seventh day. Use fictional case IDs, no person names/IIN; set referral registration date to its day, waiting registration/planned date to the historical snapshot, refusal date to its day, and `sdu_load_date` to `2025-04-01 03:00:00`. Manifest `DELTA` periods cover the actual referral/refusal dates; waiting is `SNAPSHOT` at `2025-03-31`. Reuse only the contract-default field shape from `_row` and replace *all* profile-specific identities/dates:

  ```python
  rng = random.Random(20250927)
  profile = load_profile()
  for day_index in range(90):
      day = date(2025, 1, 1) + timedelta(days=day_index)
      daily_count = 18 + (4 if day.weekday() < 5 else 0) + day_index // 21 + rng.randint(-2, 2)
      for offset in range(daily_count):
          region = profile[(day_index + offset) % len(profile)]
          row = _row("REFERRALS", day_index * 100 + offset)
          row.update(hospital_mo=f"SYN-ORG-{region['code']}",
                     referring_mo=f"SYN-ORG-{profile[(day_index + offset + 1) % len(profile)]['code']}",
                     registration_dt=f"{day.isoformat()} 09:00:00",
                     polyclinic_dt=f"{day.isoformat()} 09:00:00",
                     planned_dt=f"{(day + timedelta(days=3)).isoformat()} 09:00:00",
                     hospitalization_dt="",
                     refusal_dt="",
                     sdu_load_date="2025-04-01 03:00:00")
  ```

  Waiting sets `region_origin_code=f"SYN-REG-{code}"` and `mo_destination_code=f"SYN-WAIT-{code}"`; refusals set `region_in=f"SYN-REF-REG-{code}"` and `org_in=f"SYN-ORG-{code}"`. Set other dates within their declared historical period, and write exactly `contract.column_names` with `csv.DictWriter`. Refuse pre-existing output (`open("x")`); do not modify the strict fixture.
- [ ] **Step 4: Confirm GREEN and contract coverage.** Run `python -m pytest tests/operations/test_local_demo_dataset.py tests/operations/test_synthetic_acceptance_data.py tests/operations/test_forecast_demo_fixture.py -q`; compare two generated trees' file hashes and assert each source code belongs to one profile entry. `git diff --check` must pass.
- [ ] **Step 5: Commit.** `git add backend/seeds/local_demo_profile.json scripts/local_demo tests/operations/test_local_demo_dataset.py && git commit -m "feat(demo): generate coherent local synthetic deliveries"`.

### Task 2: Canonical directory, scopes, signals, and exact mappings

**Files:** Create `backend/seeds/local_demo_seed.py`, `backend/seeds/local_demo_mappings.py`, `backend/tests/unit/test_local_demo_seed.py`, `backend/tests/unit/test_local_demo_mappings.py`. Read-only reference: `backend/seeds/dev_seed.py`, `scripts/acceptance/publish_synthetic_mappings.py`.

**Interfaces:** `seed() -> None`, `publish() -> str`, both callable only inside backend container with `APP_ENV=local` and `LOCAL_SYNTHETIC_DEMO=1`. `local_demo_seed.load_profile() -> tuple[dict[str, str], ...]` reads the same JSON file beside the module; mappings import this backend loader. `publish` creates 60 exact decisions: 3 organization identity spaces (`REFERRALS:RECEIVING`, `WAITING:DESTINATION`, `REFUSALS:INCOMING`) and 2 region spaces (`WAITING:REGION`, `REFUSALS:REGION`) × 12. Canonical directory is exactly 12 regions and 12 fictional hospitals, with `[синтетические данные]` in names. Test realm subjects from `dev_seed.py` retain global admin/analyst and receive one new region-scoped and one hospital-scoped target from this profile.

- [ ] **Step 1: Write failing pure guards and coverage tests.** Extract `require_local_demo(settings_env: AppEnv, enabled: str | None) -> None` and `mapping_specs(profile: tuple[dict[str, str], ...]) -> tuple[tuple[str, str, str, str], ...]` so tests do not need a DB:

  ```python
  @pytest.mark.parametrize("env,flag", [(AppEnv.PRODUCTION, "1"), (AppEnv.LOCAL, None)])
  def test_seed_refuses_unsafe_environment(env, flag):
      with pytest.raises(RuntimeError):
          require_local_demo(env, flag)

  def test_every_source_has_one_mapping():
      specs = mapping_specs(load_profile())
      assert len(specs) == 60
      assert len({(kind, space, key) for kind, space, key, _ in specs}) == 60
      assert {target for _, _, _, target in specs if target.startswith("KZ-")} == {
          item["code"] for item in load_profile()
      }
  ```

- [ ] **Step 2: Confirm RED.** Run `python -m pytest backend/tests/unit/test_local_demo_seed.py backend/tests/unit/test_local_demo_mappings.py -q`; expect imports to fail.
- [ ] **Step 3: Implement seed with a single transaction.** Reuse `_ensure_user`, `UserDataScope`, `Region`, `Hospital`, `Signal`, and `SignalExplanation` patterns in `dev_seed.py`; refuse a nonempty directory rather than merging profiles. The guard and canonical construction start as follows:

  ```python
  def require_local_demo(settings_env: AppEnv, enabled: str | None) -> None:
      if settings_env is not AppEnv.LOCAL or enabled != "1":
          raise RuntimeError("Local synthetic demo requires explicit local opt-in")

  for item in load_profile():
      region = Region(id=uuid.uuid4(), code=item["code"],
                      name=f"{item['name']} [синтетические данные]")
      hospital = Hospital(id=uuid.uuid4(), code=f"H-{item['code']}",
                          name=f"Условная клиника {item['name']} [синтетические данные]",
                          region_id=region.id)
      session.add_all((region, hospital))
  ```

  Use existing realm subject IDs, but bind region and hospital scopes to the first local-demo region/hospital. Seed at least two `NEW` signals on distinct hospitals with `SignalType.DATA_STALE`, `source="SYNTHETIC_LOCAL_DEMO"`, `data_current=False`, `evidence={"synthetic": True, "confirmed_complete_through": "2025-03-31"}`, and a `SignalExplanation` saying only that the demo source is historical. Do not reuse `dev_seed.py`'s unsupported percentages or imply these signals were produced by the forecast.
- [ ] **Step 4: Implement mapping publication using existing `MappingService`.** Build the expected alias set explicitly, then reject directory/alias mismatches before publication:

  ```python
  for item in load_profile():
      code = item["code"]
      yield ("ORGANIZATION", "IS_BG:REFERRALS:RECEIVING", f"SYN-ORG-{code}", f"H-{code}")
      yield ("ORGANIZATION", "IS_BG:WAITING:DESTINATION", f"SYN-WAIT-{code}", f"H-{code}")
      yield ("ORGANIZATION", "IS_BG:REFUSALS:INCOMING", f"SYN-ORG-{code}", f"H-{code}")
      yield ("REGION", "IS_BG:WAITING:REGION", f"SYN-REG-{code}", code)
      yield ("REGION", "IS_BG:REFUSALS:REGION", f"SYN-REF-REG-{code}", code)
  ```

  Check exact directory sets, synthetic name marks, 60 unique source aliases, and missing/wrong targets. Register and approve with the same `MappingService` methods and `ИС БГ` source system as the strict mapping script; publish only after all checks pass. Keep the explicit opt-in out of the runtime `.env` and pass it only to the seed/mapping commands.
- [ ] **Step 5: Confirm GREEN and guard regressions.** Run `python -m pytest backend/tests/unit/test_local_demo_seed.py backend/tests/unit/test_local_demo_mappings.py backend/tests/unit/test_synthetic_mapping_guard.py -q`; `git diff --check` must pass.
- [ ] **Step 6: Commit.** `git add backend/seeds/local_demo_seed.py backend/seeds/local_demo_mappings.py backend/tests/unit/test_local_demo_seed.py backend/tests/unit/test_local_demo_mappings.py && git commit -m "feat(demo): seed scoped Kazakhstan directory and mappings"`.

### Task 3: Fresh-project bootstrap through the existing pipeline

**Files:** Create `scripts/local_demo/bootstrap.py`, `tests/operations/test_local_demo_bootstrap.py`. Do not edit `scripts/operations/prepare_acceptance.py` or `scripts/acceptance/bootstrap_synthetic.py`.

**Interfaces:** `bootstrap(project: str) -> dict[str, int]` accepts only a READY project under `tmp/acceptance/<project>` with its exact matching `manifest.json`, local `.env`, and empty `source-empty`. It calls Task 1 `generate`, `docker compose` through `_compose_command`, Task 2 seed/mapping modules, and the existing `pipeline approve-manifest` then `pipeline import` for each dataset. The return counts come from Task 1 manifests, not Phase 8 constants.

- [ ] **Step 1: Write failing refusal and command tests.** Mock `subprocess.run` and point `ARTIFACTS` at a temporary root; verify both the fresh-source guard and that no command addresses the old project:

  ```python
  def test_bootstrap_refuses_dirty_source(tmp_path, monkeypatch):
      project = "phase8-local-demo-test1"
      project_dir = tmp_path / project
      (project_dir / "source-empty").mkdir(parents=True)
      (project_dir / "manifest.json").write_text(json.dumps({
          "project": project, "dataset": "synthetic-only", "status": "READY"
      }))
      (project_dir / ".env").write_text("APP_ENV=local\n")
      (project_dir / "realm.json").write_text("{}")
      monkeypatch.setattr(bootstrap_module, "ARTIFACTS", tmp_path)
      (project_dir / "source-empty" / "existing.csv").write_text("keep", encoding="utf-8")
      with pytest.raises(ValueError, match="empty"):
          bootstrap(project)
      assert (project_dir / "source-empty" / "existing.csv").read_text() == "keep"

  def test_bootstrap_command_scope(tmp_path, monkeypatch):
      project = "phase8-local-demo-test1"
      monkeypatch.setattr(bootstrap_module, "ARTIFACTS", tmp_path)
      commands = command_plan(project, tmp_path / project)
      assert all("phase8-local-main-20260929a" not in argv for argv in commands)
      assert all(project in argv for argv in commands)
  ```

- [ ] **Step 2: Confirm RED.** Run `python -m pytest tests/operations/test_local_demo_bootstrap.py -q`; expect missing `bootstrap` module.
- [ ] **Step 3: Implement the narrow orchestration.** Add `command_plan(project: str, output: Path) -> tuple[tuple[str, ...], ...]` using `_compose_command`, so every command is scoped to the one validated project. Mirror fixed-argv/captured-output behavior of `bootstrap_synthetic.py`, but require the exact manifest `project`, `dataset="synthetic-only"`, and `status="READY"`; parse `.env` only to verify `APP_ENV=local`, never print its contents. The command construction uses fixed strings and an already validated project:

  ```python
  compose = tuple(_compose_command(project, output))
  seed = compose + ("exec", "-T", "-e", "LOCAL_SYNTHETIC_DEMO=1", "backend",
                    "python", "-m", "seeds.local_demo_seed")
  manifest = "/data/source/manifest-REFERRALS.json"
  approve = compose + ("run", "--rm", "pipeline", "approve-manifest",
                       "--manifest", manifest, "--actor", "local-demo-owner",
                       "--evidence-ref", "local-demo-profile-v1")
  publish = compose + ("run", "--rm", "pipeline", "import",
                       "--dataset", "REFERRALS", "--manifest", manifest)
  ```

  Apply the same approve/import argv pattern to `WAITING` and `REFUSALS`, then `exec -T -e LOCAL_SYNTHETIC_DEMO=1 backend python -m seeds.local_demo_mappings`. Refuse a duplicate delivery before any import. Capture and sanitize errors; never dump Compose stderr or realm contents.
- [ ] **Step 4: Confirm GREEN.** Run `python -m pytest tests/operations/test_local_demo_bootstrap.py tests/operations/test_synthetic_bootstrap.py -q`; `git diff --check` must pass.
- [ ] **Step 5: Commit.** `git add scripts/local_demo/bootstrap.py tests/operations/test_local_demo_bootstrap.py && git commit -m "feat(demo): bootstrap isolated local dataset"`.

### Task 4: Independent reconciliation of scope and forecast evidence

**Files:** Create `scripts/local_demo/verify.py`, `scripts/local_demo/verify_forecast_db.py`, `tests/operations/test_local_demo_verify.py`. Read-only reference: `scripts/acceptance/verify_scope.py`, `scripts/acceptance/verify_forecast_pairs.py`, `frontend/src/features/forecasting/types.ts`. The forecast DB script must be self-contained when piped to `python -` in the worker, because the worker image does not copy the host `scripts/` directory.

**Interfaces:** `expected_counts(source_root: Path) -> dict[str, int]` reads the three generated manifests and CSVs and checks each SHA-256/count before returning totals. `assert_region_coverage(expected_codes: set[str], actual_codes: set[str]) -> None` rejects missing or extra canonical regions. `verify(project_dir: Path) -> dict[str, object]` uses the generated realm only in memory for real local OIDC tokens; it compares global and per-region `/api/v1/analytics/overview`, canonical `/api/v1/regions`/`hospitals`, organization analytics, restricted-role responses, and `/api/v1/forecasts/referrals/latest` after the pipeline run. `verify_forecast_db(forecast_id: UUID) -> dict[str, object]` reads persisted forecast/model/version/points and exposes only safe validation fields for comparison to API; it does not invent or recompute a different model's MAE. Results contain safe aggregate counts, region count, forecast ID, and PASS/FAIL categories; no tokens or secrets.

- [ ] **Step 1: Write failing manifest and scope tests.** A corrupted hash, duplicate profile region code, or absent mapping must fail before PASS:

  ```python
  def test_corrupted_manifest_cannot_verify(tmp_path):
      generate(tmp_path)
      manifest = tmp_path / "manifest-REFERRALS.json"
      data = json.loads(manifest.read_text())
      data["file_hashes"] = ["0" * 64]
      manifest.write_text(json.dumps(data))
      with pytest.raises(ValueError, match="hash"):
          expected_counts(tmp_path)

  def test_region_coverage_requires_twelve_distinct_targets():
      expected = {item["code"] for item in load_profile()}
      with pytest.raises(AssertionError, match="region coverage"):
          assert_region_coverage(expected, expected - {"KZ-ASTANA"})
  ```

- [ ] **Step 2: Confirm RED.** Run `python -m pytest tests/operations/test_local_demo_verify.py -q`; expect missing verifier.
- [ ] **Step 3: Implement read-only comparison.** Derive global and region/organization expected totals by parsing the generated rows and ID rule, accounting for waiting as one snapshot and refusing duplicate IDs. Start coverage and forecast checks with explicit predicates:

  ```python
  def assert_region_coverage(expected_codes: set[str], actual_codes: set[str]) -> None:
      if expected_codes != actual_codes:
          raise AssertionError("region coverage mismatch")

  assert forecast["target"] == "DAILY_REFERRAL_COUNT"
  assert forecast["scope_type"] == "GLOBAL"
  assert forecast["horizon_days"] == len(forecast["forecast"]) == 7
  assert forecast["input_period_end"] == "2025-03-31"
  assert forecast["forecast_start"] == "2025-04-01"
  assert forecast["validation_period_start"] and forecast["validation_period_end"]
  ```

  Compare API totals, not just HTTP status; require every one of the 12 canonical region IDs to have a mapped aggregate and the restricted identities not to see foreign hospitals. Check seeded signal evidence's historical cutoff against the imported manifest. Run `verify_forecast_db` in the worker with the actual UUID and compare its persisted fields with API. If the selected model is weekly-naive, also run the existing independent pair-by-pair MAE verifier; otherwise mark independent MAE recomputation NOT VERIFIED, never infer it from the DB/API match. A missing forecast is FAIL, not `skipped`.
- [ ] **Step 4: Confirm GREEN.** Run `python -m pytest tests/operations/test_local_demo_verify.py tests/operations/test_verify_forecast_pairs.py -q`; `git diff --check` must pass.
- [ ] **Step 5: Commit.** `git add scripts/local_demo/verify.py scripts/local_demo/verify_forecast_db.py tests/operations/test_local_demo_verify.py && git commit -m "test(demo): reconcile local source, scope and forecast"`.

### Task 5: Remove the map-only data path

**Files:** Modify `frontend/src/features/map/map-panel.tsx`, `frontend/src/features/map/geography.ts`, `frontend/src/features/map/geography.test.ts`, `frontend/src/app/command-center/page.tsx`, `frontend/src/app/command-center/page.test.tsx`; delete `frontend/src/features/map/demo-regions.ts`. Keep `frontend/src/features/map/region-map.tsx` unchanged unless a failing test proves a map-rendering defect.

**Interfaces:** `MapPanel` continues to accept `apiPoints`, `apiValues`, `selectedRegionId`, and `onSelectRegion`; add `apiLoading: boolean` and `apiError: boolean`. All `RegionPoint.id` values must be canonical IDs from `/api/v1/regions`; never create `demo-*` IDs.

- [ ] **Step 1: Replace the obsolete unit expectation with a failing API-only one.** In `page.test.tsx`, mock two real region results and `useQueries` overview values, then assert both markers are API IDs, selecting the canonical UUID for `KZ-ASTANA` calls `useSituationCenter` with that UUID, no “Демо-слой” button exists, and its panel number equals the API result. Add a direct `MapPanel` test for `apiError`, `apiLoading`, and a `suppressed` point: visible text must be “Данные карты временно недоступны”, “Загружаем регионы…”, and “Скрыто” respectively, never one of the removed hard-coded values. In `geography.test.ts`, assert `centerFor("Астана [синтетические данные]", "KZ-ASTANA")` equals Astana's known center while an unrelated partial name still returns `null`.
- [ ] **Step 2: Confirm RED.** Run `cd frontend; npm test -- --run src/app/command-center/page.test.tsx`; expect the old demo-layer assertion to fail the new API-only expectation.
- [ ] **Step 3: Implement the minimal UI change.** Remove `useState`/`DEMO_MAP_REGIONS`/`demoMapPoints` from `map-panel.tsx`, feed `apiPoints` directly into `RegionMap`, and always call `onSelectRegion` on marker click:

  ```tsx
  <RegionMap points={apiPoints} metric={metric}
    selectedRegionId={selectedRegionId} onSelect={onSelectRegion} />
  ```

  In `geography.ts`, strip only the exact terminal ` [синтетические данные]` marker before its existing exact-name lookup:

  ```ts
  const values = [name.replace(/ \[синтетические данные\]$/i, ""), code]
    .map((value) => value.trim().toLowerCase());
  ```

  Do not introduce substring matching or guessed coordinates. In `command-center/page.tsx` pass `regions.isPending`/`regions.isError`, include region query failure in the visible unavailable state, replace the “Демо-слой карты…” copy with a compact “Синтетические данные — значения из API, исторический период” disclosure under the existing build flag, and retain the geographic-unmapped notice when the API succeeds with an unknown region. Do not alter KPI math or forecast cards.
- [ ] **Step 4: Confirm GREEN.** Run `cd frontend; npm test -- --run src/app/command-center/page.test.tsx src/features/map/geography.test.ts; npm run typecheck; npm run lint; npm run build`; record unrelated baseline failures separately. Search `rg 'DEMO_MAP_REGIONS|demoMapPoints|Демо-слой' frontend/src` and expect zero hits.
- [ ] **Step 5: Commit.** `git add frontend/src/features/map frontend/src/app/command-center/page.tsx frontend/src/app/command-center/page.test.tsx && git commit -m "fix(demo): use authenticated regional API data on map"`.

### Task 6: Real isolated runtime and browser proof

**Files:** Create `frontend/e2e/local-demo.spec.ts`; modify `frontend/playwright.config.ts` only to opt this file in with `MEDSIGNAL_LOCAL_DEMO=1`. No new launcher or product architecture change.

**Interfaces:** The browser test uses existing `frontend/e2e/auth.ts` and the fresh project origin/ignored realm. It checks login, 12 API-derived markers, region marker→KPI/analytics equality, organization navigation/back, persisted signal acknowledge, disabled Copilot, and forecast API→UI validation fields. It never stores credentials or browser storage state.

- [ ] **Step 1: Write the opt-in browser test before runtime.** Start with the existing `login` helper and real API response comparison:

  ```ts
  test.skip(process.env.MEDSIGNAL_LOCAL_DEMO !== "1", "requires fresh local-demo profile");
  test("local demo uses one authenticated dataset", async ({ page }) => {
    const forecastResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === "/api/v1/forecasts/referrals/latest");
    await login(page, "admin", "/command-center");
    const forecast = await forecastResponse;
    expect(forecast.status()).toBe(200);
    const body = await forecast.json();
    expect(body.target).toBe("DAILY_REFERRAL_COUNT");
    expect(body.scope_type).toBe("GLOBAL");
    expect(body.forecast).toHaveLength(7);
  });
  ```

  Extend this test with waits on `/api/v1/analytics/overview`, compare selected region marker value with the same region overview rather than invented constants, and navigate organization/back. Select a fresh `NEW` signal, submit “Принять в работу”, reload, assert `IN_PROGRESS`, and open Copilot to assert `COPILOT_DISABLED` with unchanged algorithmic explanation. If forecast is absent, fail with the actual API status instead of skipping. Prove Playwright discovery with `MEDSIGNAL_LOCAL_DEMO=1` and `playwright test --list local-demo.spec.ts` showing at least one test.
- [ ] **Step 2: Keep the old project safe and stage on a temporary loopback port.** Record `git status`, `git rev-parse HEAD`, old project identity and exact Docker Compose labels/volumes without printing secrets. Stop only the verified old `phase8-local-main-20260929a` project with its existing Compose files and **without** `down`/`-v`. Create a fresh unique project name and run:

  ```powershell
  $project = 'phase8-local-demo-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
  python -m scripts.operations.prepare_acceptance prepare --project $project
  python -m scripts.operations.prepare_acceptance start --project $project
  python -m scripts.local_demo.bootstrap --project $project
  ```

  The existing launcher builds frontend with both required flags, generates a new realm, and pins image IDs. Check its `manifest.json` for `READY`, distinct project volumes, loopback port, and the actual checkout SHA. If any safety gate fails, stop this task and preserve the old volumes.
- [ ] **Step 3: Publish and verify forecast without fabricated numbers.** Use the current project's existing Compose files and `ml-runner` once, after the local-demo referral import; do **not** run `forecast_demo_fixture.py` (the new profile already contains all 90 days). The command structure is:

  ```powershell
  $projectDir = Join-Path (Get-Location).Path "tmp/acceptance/$project"
  $compose = @('--project-name', $project, '--env-file', (Join-Path $projectDir '.env'), '--file', (Join-Path (Get-Location).Path 'docker-compose.yml'), '--file', (Join-Path $projectDir 'compose.override.yml'))
  docker compose @compose --profile tools run --rm ml-runner
  python -m scripts.local_demo.verify --project-dir $projectDir
  ```

  Take the forecast UUID from the sanitized verifier result as `$forecastId`, then pipe `scripts/local_demo/verify_forecast_db.py` into `docker compose @compose exec -T worker python - --forecast-id $forecastId`. If the selected model is weekly-naive, repeat with existing `scripts/acceptance/verify_forecast_pairs.py`; otherwise mark independent MAE recomputation NOT VERIFIED. Never overwrite model choice or MAE to satisfy a test.
- [ ] **Step 4: Run browser and static checks on the exact built SHA.** Set only session-scoped `MEDSIGNAL_E2E_BASE_URL`, `MEDSIGNAL_E2E_REALM`, and `MEDSIGNAL_LOCAL_DEMO=1`; run `cd frontend; npx playwright test e2e/local-demo.spec.ts --reporter=list`. Also run affected Python tests, `npm test`, `npm run lint`, `npm run typecheck`, and `npm run build`. Report executed/passed/failed/skipped counts; zero or skipped tests are not PASS. No paid LLM call.
- [ ] **Step 5: Roll over to `127.0.0.1:8080` only with a complete second verification.** The current launcher embeds the origin in frontend build args and realm; never edit generated URLs in place. Stop the verified staging project without deleting volumes. If `:8080` is free, create a **second** fresh `phase8-*` project with `prepare --port 8080`, then `start`, `bootstrap`, forecast pipeline, verifier, and browser checks again. Only call the new `:8080` project promoted after all pass. If the port/launcher prevents safe start or any verification fails, leave the new project unpromoted and restart only the preserved old project's verified Compose project; report the exact blocker. Keep both projects' volumes intact until the user separately authorizes cleanup.
- [ ] **Step 6: Final evidence and commit.** Commit only test/config files: `git add frontend/e2e/local-demo.spec.ts frontend/playwright.config.ts && git commit -m "test(demo): verify real local synthetic journey"`. Run `git diff --check`, `git status`, a secret scan of staged diff/history being committed, and report exact HEAD, project manifests (sanitized), image IDs/build flags, API/DB results, browser counts, and known baseline/security limitations. Stop; do not push, merge, deploy, or claim production readiness.
