# MinIO service access, rotation and recovery

## Access boundary

`minio` and the one-shot `minio-init` are the only services that receive
`MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`. `minio-init` creates the eight
existing private buckets and four distinct users with policies from
`infrastructure/minio/policies/`. No application user is an administrator.

| Identity | Container(s) | Allowed object access | Denied by default |
| --- | --- | --- | --- |
| `MINIO_APP_*` | backend, migrate, clickhouse-migrate | read/version-read `medsignal-models` | write, quarantine, raw, all other buckets |
| `MINIO_WORKER_*` | worker, ml-runner | read/version-read `medsignal-models` | write, quarantine, raw, all other buckets |
| `MINIO_PIPELINE_*` | pipeline | write `medsignal-quarantine` | read quarantine, models, raw, all other buckets |
| `MINIO_MLFLOW_*` | mlflow | read/write/delete `medsignal-models` | quarantine, raw, all other buckets |

The backend also has `ListAllMyBuckets`, scoped to the models bucket, because
the current `/ready` storage probe calls `list_buckets()`. It does not grant
object access to another bucket. The pipeline can HEAD/list its quarantine
bucket for `ensure_bucket`; creation of buckets remains bootstrap-only.
No application identity can read `medsignal-raw`. The raw bucket is reserved
for a future explicitly reviewed workflow. Backup/restore tooling still uses
root as an administrative operation, not as an application credential.

Each service secret must be independently generated and supplied through the
deployment secret store or untracked `.env`. `.env.example` contains *local
development only* values. The production overlay forces `APP_ENV=production`
for bootstrap; it rejects any `local_dev_only` value. Service identities may
not reuse the root access key or root secret. Do not place credentials in
Compose command arguments, logs, Git, tickets or analytics artifacts.

## Upgrade of an existing installation

1. Back up MinIO and verify restore according to
   [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Do not clear the existing volume.
2. Provide `MINIO_APP_*`, `MINIO_WORKER_*`, `MINIO_PIPELINE_*` and
   `MINIO_MLFLOW_*` in the secret store. Compose deliberately refuses to
   render if any service key is absent.
3. Apply the Compose overlay appropriate to the environment and run
   `docker compose up -d minio-init`. The one-shot job must exit 0 before
   backend, worker, pipeline or MLflow start.
4. Recreate the consuming containers so they read the new keys. Check
   `/api/v1/ready`, a controlled import/quarantine write and an MLflow
   artifact round-trip. Verify unauthorized bucket access with the test below.
5. Retain the old root secret only in the restricted administrative store.
   Rotate it after the application identities are proven working and after
   backup/restore tooling has been updated. Root rotation is a separate
   maintenance operation.

The bootstrap is repeatable: it recreates policies from versioned JSON,
upserts users and keeps existing buckets/objects. A failed run must be
investigated from its stage label; it must never be repaired by granting
`readwrite`/`consoleAdmin` to application identities.

## Rotation and revocation

For routine secret rotation, keep each access key stable, issue a new secret
through the deployment secret store, rerun `minio-init`, then recreate the
affected consumers in the same maintenance window. Verify both an allowed
operation and a denied cross-bucket operation. Until consumers restart, the
old secret may no longer authenticate.

If an access key itself changes, bootstrap creates a new user. The old user
is **not** deleted automatically because bootstrap cannot safely infer whether
it is still used. Once the new identity is verified, an administrator must
disable then remove the *specific old access key* using `mc admin user` in a
restricted session. Record the key name and approval in the operational audit;
never record either secret. Run the cross-bucket test again after revocation.

For compromise, immediately disable the affected user, rotate its key and
secret, restart consumers, inspect access logs and verify no unauthorized
objects were read or written. Quarantine/raw incidents require the data
owner's incident process. Do not publish MinIO ports to diagnose access.

## Recovery and verification

When bootstrap fails, inspect only the generic stage label in `minio-init`
logs (`alias`, `bucket-create`, `policy-create`, `user-create`, `policy-attach`).
Check policy JSON, distinct nonempty credentials and MinIO health. Fix the
cause and rerun the one-shot job; **do not remove buckets or volumes**.
If an object is lost or MinIO storage is damaged, use isolated restore
verification in [BACKUP_RESTORE.md](BACKUP_RESTORE.md) before cutover.
Losing root access requires a controlled infrastructure recovery procedure,
not a policy bypass.

Automated test (fresh, isolated Compose project; uses only synthetic objects
and `.env.example`, then removes only its own project and volume):

```powershell
$env:MEDSIGNAL_MINIO_INTEGRATION = '1'
python -m pytest tests/security/test_minio_least_privilege.py -q
```

Without that variable, the test file still checks the Compose wiring and
versioned policies statically. The real test checks allowed reads/writes,
denied cross-bucket reads, denied model writes by app/worker, denied raw
access, repeatable bootstrap and rotation of one service secret. It requires
Docker and locally available MinIO images. This verifies access control for
the local MinIO release;
external S3 providers need equivalent policy tests before deployment.
