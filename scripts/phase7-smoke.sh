#!/usr/bin/env bash
# Safe local Phase 7 smoke test. Prints aggregate/scenario metadata only.
set -euo pipefail

API_URL="${MEDSIGNAL_API_URL:-http://localhost/api/v1}"
PYTHON_BIN="${PYTHON_BIN:-.venv-phase4/Scripts/python.exe}"
TOKEN="$(./scripts/dev-token.sh)"
WORK_DIR="${PHASE7_SMOKE_DIR:-.test-tmp-phase7-smoke}"
mkdir -p "$WORK_DIR"

auth=(-H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json')

curl --fail --silent --show-error "${auth[@]}" \
  "$API_URL/signals?page_size=1&scope_type=GLOBAL" > "$WORK_DIR/signals.json"
SIGNAL_ID="$($PYTHON_BIN -c "import json; d=json.load(open('$WORK_DIR/signals.json', encoding='utf-8')); print(d['items'][0]['id'])")"
curl --fail --silent --show-error "${auth[@]}" \
  "$API_URL/signals/$SIGNAL_ID" > "$WORK_DIR/signal-before.json"

OBSERVED_BODY="$($PYTHON_BIN -c "import json; print(json.dumps({'scenario_type':'REFERRAL_INFLOW_CHANGE','scope_type':'GLOBAL','baseline_type':'OBSERVED','assumption_value':'0.20','period_start':'2025-01-01','period_end':'2025-03-31','historical_analysis':True,'source_signal_id':'$SIGNAL_ID'}))")"
curl --fail --silent --show-error "${auth[@]}" -X POST \
  -d "$OBSERVED_BODY" "$API_URL/scenarios/preview" > "$WORK_DIR/observed-preview.json"

REQUEST_ID="$($PYTHON_BIN -c "import uuid; print(uuid.uuid4())")"
SAVE_BODY="$($PYTHON_BIN -c "import json; d=json.loads('''$OBSERVED_BODY'''); d['client_request_id']='$REQUEST_ID'; print(json.dumps(d))")"
curl --fail --silent --show-error "${auth[@]}" -X POST \
  -d "$SAVE_BODY" "$API_URL/scenarios" > "$WORK_DIR/observed-save.json"
curl --fail --silent --show-error "${auth[@]}" -X POST \
  -d "$SAVE_BODY" "$API_URL/scenarios" > "$WORK_DIR/observed-retry.json"

curl --fail --silent --show-error "${auth[@]}" \
  "$API_URL/forecasts/referrals/latest" > "$WORK_DIR/forecast.json"
FORECAST_ID="$($PYTHON_BIN -c "import json; print(json.load(open('$WORK_DIR/forecast.json', encoding='utf-8'))['id'])")"
FORECAST_BODY="$($PYTHON_BIN -c "import json; print(json.dumps({'scenario_type':'REFERRAL_INFLOW_CHANGE','scope_type':'GLOBAL','baseline_type':'FORECAST','assumption_value':'0.20','forecast_id':'$FORECAST_ID','historical_analysis':True}))")"
FORECAST_CURRENT_BODY="$($PYTHON_BIN -c "import json; d=json.loads('''$FORECAST_BODY'''); d['historical_analysis']=False; print(json.dumps(d))")"
STALE_DENIAL_STATUS="$(curl --silent --output "$WORK_DIR/stale-denial.json" --write-out '%{http_code}' "${auth[@]}" -X POST -d "$FORECAST_CURRENT_BODY" "$API_URL/scenarios/preview")"
test "$STALE_DENIAL_STATUS" = "422"
curl --fail --silent --show-error "${auth[@]}" -X POST \
  -d "$FORECAST_BODY" "$API_URL/scenarios/preview" > "$WORK_DIR/forecast-preview.json"
FORECAST_REQUEST_ID="$($PYTHON_BIN -c "import uuid; print(uuid.uuid4())")"
FORECAST_SAVE_BODY="$($PYTHON_BIN -c "import json; d=json.loads('''$FORECAST_BODY'''); d['client_request_id']='$FORECAST_REQUEST_ID'; print(json.dumps(d))")"
curl --fail --silent --show-error "${auth[@]}" -X POST \
  -d "$FORECAST_SAVE_BODY" "$API_URL/scenarios" > "$WORK_DIR/forecast-save.json"
curl --fail --silent --show-error "${auth[@]}" \
  "$API_URL/signals/$SIGNAL_ID" > "$WORK_DIR/signal-after.json"

$PYTHON_BIN - "$WORK_DIR" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
load = lambda name: json.loads((root / name).read_text(encoding="utf-8"))
observed = load("observed-preview.json")
saved = load("observed-save.json")
retry = load("observed-retry.json")
forecast = load("forecast-preview.json")
forecast_saved = load("forecast-save.json")
before = load("signal-before.json")
after = load("signal-after.json")
assert saved["id"] == retry["id"]
assert before["version"] == after["version"]
assert before["status"] == after["status"]
assert before["incident_id"] == after["incident_id"]
print(json.dumps({
    "observed": {
        "baseline": observed["baseline_value"],
        "scenario": observed["calculated_value"],
        "delta": observed["delta_absolute"],
        "period": [observed["baseline_period_start"], observed["baseline_period_end"]],
        "freshness": observed["baseline_freshness_status"],
    },
    "forecast": {
        "baseline": forecast["baseline_value"],
        "scenario": forecast["calculated_value"],
        "validity": forecast["forecast_status"],
        "freshness": forecast["baseline_freshness_status"],
        "historical": forecast["historical"],
        "model_version": forecast["model_version"],
        "saved_scenario_id": forecast_saved["id"],
    },
    "idempotent": saved["id"] == retry["id"],
    "source_signal_unchanged": True,
    "stale_without_historical_opt_in_status": 422,
    "saved_scenario_id": saved["id"],
}, ensure_ascii=False, indent=2))
PY
