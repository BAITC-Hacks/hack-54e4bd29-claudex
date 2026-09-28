#!/usr/bin/env bash
# Получить действительный токен Keycloak для локальной проверки.
#
# Использует служебный клиент medsignal-dev-cli из области разработки.
# В общих средах этот клиент не создаётся.
set -euo pipefail

REALM_URL="${KEYCLOAK_TOKEN_URL:-http://localhost/auth/realms/medsignal/protocol/openid-connect/token}"
CLIENT_ID="medsignal-dev-cli"
CLIENT_SECRET="medsignal-dev-cli-local_dev_only"

response="$(curl --fail --silent --show-error \
  --request POST "$REALM_URL" \
  --header 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'grant_type=client_credentials' \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}")"

python -c "import json,sys; print(json.load(sys.stdin)['access_token'])" <<< "$response"
