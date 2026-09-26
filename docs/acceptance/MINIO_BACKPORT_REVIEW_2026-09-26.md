# MinIO advisory review — patched synthetic acceptance (2026-09-26)

This review covers the 27 published advisories in the official `minio/minio` GitHub security-advisory feed on 2026-09-26. CI rechecks the complete set and advisory metadata before any runtime. New/changed advisory or unavailable feed blocks the probe and Compose. The selected source is the signed `RELEASE.2024-11-07T00-52-20Z` (`cefc43e4daa4cbb490ef6726ea374e26a93eb85e`), with only the exact `f246c9053f9603e610d98439799bdd2a6b293427` application backport plus the separately approved Go module patches. This is not an official release or production approval.

AFFECTED means the base falls before the published fix (or is within the stated affected range); feature exposure in the disposable configuration is not proof of production safety. NOT AFFECTED means the published fix predates the signed base release or the platform does not apply. FIXED BY BACKPORT is only the one reviewed IAM change. There are 10 remaining AFFECTED advisories, all below the official CRITICAL severity. Therefore `SECURITY_ADMISSION=FAIL` even if functional tests later pass.

| Advisory / CVE | Severity | Published affected range | Published fix | Base applicability / review status |
|---|---|---|---|---|
| [GHSA-xh8f-g2qw-gcm7](https://github.com/minio/minio/security/advisories/GHSA-xh8f-g2qw-gcm7) / CVE-2026-42600 | MEDIUM | >= RELEASE.2022-07-24T01-54-52Z | >= RELEASE.2026-04-14T21-32-45Z | YES / AFFECTED |
| [GHSA-hv4r-mvr4-25vw](https://github.com/minio/minio/security/advisories/GHSA-hv4r-mvr4-25vw) / CVE-2026-41145 | HIGH | >= RELEASE.2023-05-18T00-05-36Z | >= RELEASE.2026-04-11T03-20-12Z | YES / AFFECTED |
| [GHSA-9c4q-hq6p-c237](https://github.com/minio/minio/security/advisories/GHSA-9c4q-hq6p-c237) / CVE-2026-40344 | HIGH | >= RELEASE.2023-05-18T00-05-36Z | >= RELEASE.2026-04-11T03-20-12Z | YES / AFFECTED |
| [GHSA-h749-fxx7-pwpg](https://github.com/minio/minio/security/advisories/GHSA-h749-fxx7-pwpg) / CVE-2026-39414 | HIGH | >= RELEASE.2018-08-18T03-49-57Z | MinIO AIStor RELEASE.2025-12-20T04-58-37Z | YES / AFFECTED |
| [GHSA-3rh2-v3gr-35p9](https://github.com/minio/minio/security/advisories/GHSA-3rh2-v3gr-35p9) / CVE-2026-34204 | HIGH | > RELEASE.2024-03-30T09-41-56Z | >= RELEASE.2026-03-26T21-24-40Z | YES / AFFECTED |
| [GHSA-jv87-32hw-hh99](https://github.com/minio/minio/security/advisories/GHSA-jv87-32hw-hh99) / CVE-2026-33419 | MEDIUM | < RELEASE.2026-03-17T21-25-16Z | RELEASE.2026-03-17T21-25-16Z | YES / AFFECTED |
| [GHSA-5cx5-wh4m-82fh](https://github.com/minio/minio/security/advisories/GHSA-5cx5-wh4m-82fh) / CVE-2026-33322 | MEDIUM | >= RELEASE.2022-11-08T05-27-07Z | RELEASE.2026-03-17T21-25-16Z | YES / AFFECTED |
| [GHSA-jjjj-jwhf-8rgr](https://github.com/minio/minio/security/advisories/GHSA-jjjj-jwhf-8rgr) / CVE-2025-62506 | HIGH | all | RELEASE.2025-10-15T17-29-55Z | YES / AFFECTED |
| [GHSA-wg47-6jq2-q2hh](https://github.com/minio/minio/security/advisories/GHSA-wg47-6jq2-q2hh) / CVE-2025-31489 | HIGH | RELEASE.2023-05-18T00-05-36Z | RELEASE.2025-04-03T14-56-28Z | YES / AFFECTED |
| [GHSA-wc79-7x8x-2p58](https://github.com/minio/minio/security/advisories/GHSA-wc79-7x8x-2p58) / CVE-2025-27414 | MEDIUM | RELEASE.2024-06-06T09-36-42Z and newer | RELEASE.2025-02-28T09-55-16Z | YES / AFFECTED |
| [GHSA-cwq8-g58r-32hg](https://github.com/minio/minio/security/advisories/GHSA-cwq8-g58r-32hg) / CVE-2024-55949 | CRITICAL | RELEASE.2022-06-25T15-50-16Z | RELEASE.2024-12-13T22-19-12Z | YES / FIXED BY BACKPORT |
| [GHSA-95fr-cm4m-q5p9](https://github.com/minio/minio/security/advisories/GHSA-95fr-cm4m-q5p9) / CVE-2024-36107 | MEDIUM | RELEASE.2022-10-02T19-29-29Z | RELEASE.2024-05-27T19-17-46Z | NO / NOT AFFECTED |
| [GHSA-xx8w-mq23-29g4](https://github.com/minio/minio/security/advisories/GHSA-xx8w-mq23-29g4) / CVE-2024-24747 | HIGH | all | RELEASE.2024-01-31T20-20-33Z | NO / NOT AFFECTED |
| [GHSA-6xvq-wj2x-3h3q](https://github.com/minio/minio/security/advisories/GHSA-6xvq-wj2x-3h3q) / CVE-2023-28432 | CRITICAL | RELEASE.2021-08-31T05-46-54Z | RELEASE.2023-03-20T20-16-18Z | NO / NOT AFFECTED |
| [GHSA-2pxw-r47w-4p8c](https://github.com/minio/minio/security/advisories/GHSA-2pxw-r47w-4p8c) / CVE-2023-28434 | CRITICAL | all | RELEASE.2023-03-20T20-16-18Z | NO / NOT AFFECTED |
| [GHSA-w23q-4hw3-2pp6](https://github.com/minio/minio/security/advisories/GHSA-w23q-4hw3-2pp6) / CVE-2023-28433 | CRITICAL | all | RELEASE.2023-03-20T20-16-18Z | NO / NOT AFFECTED |
| [GHSA-9wfv-wmf7-6753](https://github.com/minio/minio/security/advisories/GHSA-9wfv-wmf7-6753) / CVE-2023-27589 | MEDIUM | >= RELEASE.2020-12-23T02-24-12Z | RELEASE.2023-03-13T19-46-17Z | NO / NOT AFFECTED |
| [GHSA-c8fc-mjj8-fc63](https://github.com/minio/minio/security/advisories/GHSA-c8fc-mjj8-fc63) / CVE-2023-25812 | HIGH | >= RELEASE.2020-04-10T03-34-42Z | RELEASE.2023-02-17T17-52-43Z | NO / NOT AFFECTED |
| [GHSA-gr9v-6pcm-rqvg](https://github.com/minio/minio/security/advisories/GHSA-gr9v-6pcm-rqvg) / CVE-2022-35919 | HIGH | >= RELEASE.2020-07-24T22-43-05Z | RELEASE.2022-07-29T19-40-48Z | NO / NOT AFFECTED |
| [GHSA-qrpr-r3pw-f636](https://github.com/minio/minio/security/advisories/GHSA-qrpr-r3pw-f636) / CVE-2022-31028 | HIGH | >= RELEASE.2019-09-25T18-25-51Z | RELEASE.2022-06-02T02-11-04Z | NO / NOT AFFECTED |
| [GHSA-2j69-jjmg-534q](https://github.com/minio/minio/security/advisories/GHSA-2j69-jjmg-534q) / CVE-2022-24842 | HIGH | >= RELEASE.2021-12-09T06-19-41Z | RELEASE.2022-04-12T06-55-35Z | NO / NOT AFFECTED |
| [GHSA-j6jc-jqqc-p6cx](https://github.com/minio/minio/security/advisories/GHSA-j6jc-jqqc-p6cx) / CVE-2021-43858 | HIGH | RELEASE.2019-07-31T18-57-56Z | RELEASE.2021-12-27T07-23-18Z | NO / NOT AFFECTED |
| [GHSA-v64v-g97p-577c](https://github.com/minio/minio/security/advisories/GHSA-v64v-g97p-577c) / CVE-2021-41137 | HIGH | RELEASE.2021-10-10T16-53-30Z | RELEASE.2021-10-13T00-23-17Z | NO / NOT AFFECTED |
| [GHSA-xr7r-7gpj-5pgp](https://github.com/minio/minio/security/advisories/GHSA-xr7r-7gpj-5pgp) / CVE-2021-21390 | MEDIUM | < RELEASE.2021-03-17T02-33-02Z | RELEASE.2021-03-17T02-33-02Z | NO / NOT AFFECTED |
| [GHSA-hq5j-6r98-9m8v](https://github.com/minio/minio/security/advisories/GHSA-hq5j-6r98-9m8v) / CVE-2021-21362 | MEDIUM | < RELEASE.2021-03-04T00-53-13Z | RELEASE.2021-03-04T00-53-13Z | NO / NOT AFFECTED |
| [GHSA-m4qq-5f7c-693q](https://github.com/minio/minio/security/advisories/GHSA-m4qq-5f7c-693q) / CVE-2021-21287 | MEDIUM | >= RELEASE.2019-12-17T23-16-33Z | RELEASE.2021-01-30T00-20-58Z | NO / NOT AFFECTED |
| [GHSA-xv4r-vccv-mg4w](https://github.com/minio/minio/security/advisories/GHSA-xv4r-vccv-mg4w) / CVE-2020-11012 | HIGH | RELEASE.2019-12-17T23-16-33Z | RELEASE.2020-04-23T00-58-49Z | NO / NOT AFFECTED |

## Exact backport provenance

- Upstream repository: <https://github.com/minio/minio>.
- Base signed tag: `RELEASE.2024-11-07T00-52-20Z`; base commit: `cefc43e4daa4cbb490ef6726ea374e26a93eb85e`.
- Fix commit: [`f246c9053f9603e610d98439799bdd2a6b293427`](https://github.com/minio/minio/commit/f246c9053f9603e610d98439799bdd2a6b293427).
- Exact `git show --format= --binary` patch SHA-256: `26bd3d86e09b0fbf8b5fe472d43a20dc087c6f208a822f375ca67ce93de31de6`.
- Changed application file: `cmd/admin-handlers-users.go` only. Previously approved dependency metadata: `go.mod`, `go.sum`.
- Patched source Git tree SHA-1 after both patches on a clean `core.autocrlf=false` checkout: `094a00c707fcf5e7a9a01cebea1158486c5ba553`.
- `git apply --check` and `git apply` are used without fuzzy or three-way application; the exact added/deleted source lines and final tree are checked before build.

## Gate semantics

The source provenance check, live advisory-feed comparison, final-image Trivy scan and disposable IAM deny/allow probe are independent gates before the full Compose acceptance project. Any CRITICAL in either final image, unreviewed/changed advisory, absent Go inventory, or failed limited/service-account denial stops before Compose. HIGH findings do not receive suppressions and keep production security admission at FAIL. The IAM probe uses a separate `phase8-*` Docker bridge and volume, no published ports, synthetic identities, and removes its exported IAM ZIP and temporary credentials in `finally`.

The official advisory feed is one source, not a guarantee that no unreported vulnerability exists. The 2024 community source line is archived; a supported production storage decision remains separate.
