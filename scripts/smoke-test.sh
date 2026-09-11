#!/usr/bin/env bash
# Сквозная проверка фундамента PHASE 1.
#
# Проверяет то, что перечислено в критериях приёмки: доступность
# приложения, готовность зависимостей, приём действительного токена
# Keycloak, отклонение недействительного и работу фоновой задачи
# с устойчивым состоянием операции.
set -uo pipefail

BASE="${MEDSIGNAL_BASE_URL:-http://localhost}"
API="${BASE}/api/v1"
failures=0

pass() { printf '  \033[32mOK\033[0m   %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; failures=$((failures + 1)); }

check_status() {
  local name="$1" expected="$2" actual="$3"
  if [ "$actual" = "$expected" ]; then pass "$name ($actual)"; else fail "$name: ожидалось $expected, получено $actual"; fi
}

echo "== Доступность =="
check_status "Frontend отвечает" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/")"
check_status "GET /api/v1/health" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$API/health")"
check_status "GET /api/v1/ready" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$API/ready")"

echo
echo "== Зависимости =="
ready_body="$(curl -s "$API/ready")"
for dep in postgres clickhouse redis object_storage; do
  status="$(python -c "
import json,sys
d=json.loads(sys.stdin.read())
print(next((x['status'] for x in d['dependencies'] if x['name']=='$dep'), 'missing'))
" <<< "$ready_body")"
  if [ "$status" = "up" ]; then pass "$dep доступна"; else fail "$dep: $status"; fi
done

echo
echo "== Периметр =="
check_status "/metrics не опубликован" 404 "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/metrics")"
hdr="$(curl -s -D - -o /dev/null "$API/health")"
grep -qi 'x-content-type-options: nosniff' <<< "$hdr" && pass "Заголовок X-Content-Type-Options" || fail "Нет X-Content-Type-Options"
grep -qi 'x-frame-options: DENY' <<< "$hdr" && pass "Заголовок X-Frame-Options" || fail "Нет X-Frame-Options"
grep -qi 'x-request-id:' <<< "$hdr" && pass "Заголовок X-Request-ID" || fail "Нет X-Request-ID"

echo
echo "== Keycloak =="
check_status "Метаданные области" 200 \
  "$(curl -s -o /dev/null -w '%{http_code}' "$BASE/auth/realms/medsignal/.well-known/openid-configuration")"

token="$(bash "$(dirname "$0")/dev-token.sh" 2>/dev/null || true)"
if [ -n "$token" ]; then
  pass "Токен получен"
  check_status "Защищённый эндпоинт принимает токен" 200 \
    "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $token" "$API/system/whoami")"
  check_status "Недействительный токен отклонён" 401 \
    "$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer недействительный" "$API/system/whoami")"
  check_status "Запрос без токена отклонён" 401 \
    "$(curl -s -o /dev/null -w '%{http_code}' "$API/system/whoami")"

  echo
  echo "== Фоновая задача =="
  accepted="$(curl -s -X POST -H "Authorization: Bearer $token" "$API/system/ping-task")"
  op_id="$(python -c "import json,sys; print(json.loads(sys.stdin.read()).get('operation_id',''))" <<< "$accepted")"
  if [ -n "$op_id" ]; then
    pass "Операция зарегистрирована: $op_id"
    status=""
    for _ in $(seq 1 20); do
      status="$(curl -s -H "Authorization: Bearer $token" "$API/system/operations/$op_id" \
        | python -c "import json,sys; print(json.loads(sys.stdin.read()).get('status',''))")"
      [ "$status" = "COMPLETED" ] || [ "$status" = "FAILED" ] && break
      sleep 1
    done
    [ "$status" = "COMPLETED" ] && pass "Воркер выполнил задачу (COMPLETED)" || fail "Состояние операции: $status"
  else
    fail "Операция не зарегистрирована: $accepted"
  fi
else
  fail "Не удалось получить токен Keycloak"
fi

echo
if [ "$failures" -eq 0 ]; then
  printf '\033[32mВсе проверки пройдены\033[0m\n'
else
  printf '\033[31mНе пройдено проверок: %s\033[0m\n' "$failures"
fi
exit "$failures"
