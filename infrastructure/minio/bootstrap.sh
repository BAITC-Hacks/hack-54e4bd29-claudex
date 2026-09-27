#!/bin/sh
# One-shot provisioning. This is the only application-stack container given
# the MinIO root credential; failures expose no account names or secrets.
set -eu

fail() {
  printf '%s\n' "[medsignal] MinIO bootstrap failed: $1" >&2
  exit 1
}

for name in MINIO_ROOT_USER MINIO_ROOT_PASSWORD \
  MINIO_APP_ACCESS_KEY MINIO_APP_SECRET_KEY \
  MINIO_WORKER_ACCESS_KEY MINIO_WORKER_SECRET_KEY \
  MINIO_PIPELINE_ACCESS_KEY MINIO_PIPELINE_SECRET_KEY \
  MINIO_MLFLOW_ACCESS_KEY MINIO_MLFLOW_SECRET_KEY; do
  eval "value=\${$name-}"
  [ -n "$value" ] || fail "required credential is empty"
  if [ "${APP_ENV:-local}" != local ]; then
    case "$value" in *local_dev_only*) fail "development credential outside local" ;; esac
  fi
done

for key in "$MINIO_APP_ACCESS_KEY" "$MINIO_WORKER_ACCESS_KEY" \
  "$MINIO_PIPELINE_ACCESS_KEY" "$MINIO_MLFLOW_ACCESS_KEY"; do
  [ "$key" != "$MINIO_ROOT_USER" ] || fail "root identity reused by service"
done
for secret in "$MINIO_APP_SECRET_KEY" "$MINIO_WORKER_SECRET_KEY" \
  "$MINIO_PIPELINE_SECRET_KEY" "$MINIO_MLFLOW_SECRET_KEY"; do
  [ "$secret" != "$MINIO_ROOT_PASSWORD" ] || fail "root secret reused by service"
done
[ "$MINIO_APP_ACCESS_KEY" != "$MINIO_WORKER_ACCESS_KEY" ] || fail "service identities overlap"
[ "$MINIO_APP_ACCESS_KEY" != "$MINIO_PIPELINE_ACCESS_KEY" ] || fail "service identities overlap"
[ "$MINIO_APP_ACCESS_KEY" != "$MINIO_MLFLOW_ACCESS_KEY" ] || fail "service identities overlap"
[ "$MINIO_WORKER_ACCESS_KEY" != "$MINIO_PIPELINE_ACCESS_KEY" ] || fail "service identities overlap"
[ "$MINIO_WORKER_ACCESS_KEY" != "$MINIO_MLFLOW_ACCESS_KEY" ] || fail "service identities overlap"
[ "$MINIO_PIPELINE_ACCESS_KEY" != "$MINIO_MLFLOW_ACCESS_KEY" ] || fail "service identities overlap"
[ "$MINIO_APP_SECRET_KEY" != "$MINIO_WORKER_SECRET_KEY" ] || fail "service secrets overlap"
[ "$MINIO_APP_SECRET_KEY" != "$MINIO_PIPELINE_SECRET_KEY" ] || fail "service secrets overlap"
[ "$MINIO_APP_SECRET_KEY" != "$MINIO_MLFLOW_SECRET_KEY" ] || fail "service secrets overlap"
[ "$MINIO_WORKER_SECRET_KEY" != "$MINIO_PIPELINE_SECRET_KEY" ] || fail "service secrets overlap"
[ "$MINIO_WORKER_SECRET_KEY" != "$MINIO_MLFLOW_SECRET_KEY" ] || fail "service secrets overlap"
[ "$MINIO_PIPELINE_SECRET_KEY" != "$MINIO_MLFLOW_SECRET_KEY" ] || fail "service secrets overlap"

run_quiet() {
  stage=$1
  shift
  "$@" >/dev/null 2>&1 || fail "$stage"
}

run_quiet alias mc alias set -- local http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
for bucket in medsignal-imports medsignal-models medsignal-exports \
  medsignal-reports medsignal-raw medsignal-quarantine \
  medsignal-quality medsignal-artifacts; do
  run_quiet bucket-create mc mb --ignore-existing "local/$bucket"
  run_quiet bucket-private mc anonymous set none "local/$bucket"
done

provision() {
  role=$1
  key=$2
  secret=$3
  run_quiet policy-create mc admin policy create local "medsignal-$role" \
    "/opt/medsignal/minio/policies/$role.json"
  run_quiet user-create mc admin user add -- local "$key" "$secret"
  run_quiet policy-attach mc admin policy attach local "medsignal-$role" --user "$key"
}

provision app "$MINIO_APP_ACCESS_KEY" "$MINIO_APP_SECRET_KEY"
provision worker "$MINIO_WORKER_ACCESS_KEY" "$MINIO_WORKER_SECRET_KEY"
provision pipeline "$MINIO_PIPELINE_ACCESS_KEY" "$MINIO_PIPELINE_SECRET_KEY"
provision mlflow "$MINIO_MLFLOW_ACCESS_KEY" "$MINIO_MLFLOW_SECRET_KEY"

printf '%s\n' '[medsignal] MinIO buckets and scoped service identities ready'
