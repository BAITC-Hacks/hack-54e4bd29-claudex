# Current image findings — 2026-09-26

Status: **FAIL**. Current-branch evidence below does not admit the three Python
images or accept their residual vulnerabilities.

## Final local HEAD recheck — `4cc44083ac79c1c284f420593761027224c7ea4d`

The isolated `phase8-accept-20260926e` project built and ran these five
production images from the exact commit above. Pinned Trivy `0.58.2` image
`sha256:665030f4d33a82c1e8d9d5e0453365842236723c1ee5cc3becca698268e66a56`
scanned all five exported image archives independently on 2026-09-26, using
vulnerability DB v2 updated `2026-09-26T01:14:39Z`. The scanner ran with no
network access, no ignored findings and no severity filtering. Raw per-image
reports remain in ignored `tmp/security-current/acceptance-e/`.

| Image | Exact local image content digest | Base image content/digest | HIGH | CRITICAL | Gate |
|---|---|---|---:|---:|---|
| backend | `sha256:cbc87268c985e71b4ff12df17d8c1ea08e3e9f1da74c6e816b7d8a89d757da19` | `python:3.12-slim` `sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea` | 44 | 0 | FAIL |
| worker | `sha256:f4ac54fd7a0ac506de0f0e5bfd03c3ef206218563acf366098305ebf56085b32` | same Python base | 44 | 0 | FAIL |
| MLflow | `sha256:9bde97dca4aa6ba2bbf31739ddec94aa68a7f5d2d3c2998ef329b47127c06f99` | same Python base | 44 | 0 | FAIL |
| frontend | `sha256:7a13cead9cfbd00bc89832459d8160cc5f8776da2f5b3b56549a8f221954cbff` | `node:22-alpine` `sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32` | 0 | 0 | PASS for scanned image |
| nginx | `sha256:f87d949b38e93518b37fe6cb93ad5ab456ec3b60308d8a1a3d546fc2a8f45fe2` | pinned `nginx:1.30.5-alpine` `sha256:f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d` | 0 | 0 | PASS for scanned image |

Every blocking finding is a Debian OS-package row. The Python-package and
Node-package result sets each contain **0 HIGH and 0 CRITICAL**. The 44 rows
in each Python image represent the same eight CVEs and package versions listed
below. Trivy reports no fixed version for them in this Debian stable base.
No Python dependency upgrade is indicated by this scan. Neither image-policy
suppression nor blanket risk acceptance was added. The local synthetic
acceptance runtime passed separately; its success does **not** change this
production image gate.

## Earlier branch recheck — `452873bb453e2bf310cad90909e68c24b6b3c300`

The five production images were built with `docker build --pull` from the
ownership-corrected branch HEAD above. The backend, worker and MLflow images were rebuilt
and scanned **independently**; no CI result from a prior branch substitutes for
these scans. Pinned Trivy `0.58.2` image digest
`sha256:665030f4d33a82c1e8d9d5e0453365842236723c1ee5cc3becca698268e66a56`
used vulnerability DB v2, updated `2026-09-26T01:14:39Z` and downloaded
`2026-09-26T04:40:06Z`. It scanned exported image archives without a Docker
socket, with no ignorefile suppressions and no severity filtering. Raw local
reports remain ignored under `tmp/security-current/`.

| Image | Local image content digest | Base image digest | HIGH | CRITICAL | Gate |
|---|---|---|---:|---:|---|
| backend | `sha256:02e9bd31d19db775a30753368880237612b6f8364f6113259ee1e467955896fa` | `python:3.12-slim` platform `sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f` | 44 | 0 | FAIL |
| worker | `sha256:9d7a51b617da3ebb555f9f762988d789f8565ca78b7345a29eb8b7088e1ad241` | same Python base | 44 | 0 | FAIL |
| MLflow | `sha256:ed616d10c37574a20993989386125636887cdd453dd3c5701b91dbc3f956421e` | same Python base | 44 | 0 | FAIL |
| frontend | `sha256:e8c6ecf17bad0249c46e61dffe5bd5d8ea2926b045c53ef86169112300cf6967` | `node:22-alpine` registry `sha256:c610fcdfb1d5b4740dd70c284ed3cb16bb857e0f7166196e36a5501df7a3aa32` | 0 | 0 | PASS for scanned image |
| nginx | `sha256:466c3ae9215a070b9a95c86c6379c067fe8777aabdfe956c2656cd1862a5f4fc` | pinned `nginx:1.30.5-alpine` `sha256:f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d` | 0 | 0 | PASS for scanned image |

All 44 HIGH rows in each Python image are **Debian OS packages**. Trivy found
zero HIGH/CRITICAL Python packages, so no Python dependency upgrade is indicated
by this gate. The same eight CVEs and package versions occur in all three
Python images. `—` means neither this Trivy DB nor the trixie security tracker
offers a fixed package version within the selected stable base.

| CVE | Affected installed packages and versions (OS packages) | Fixed in trixie | Remediation availability |
|---|---|---|---|
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) | `libncursesw6`, `libtinfo6`, `ncurses-base`, `ncurses-bin` at `6.5+20250216-2` | — | Forky/sid source `6.6+20260608-2`; incompatible release, not adopted |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) | `libsystemd0`, `libudev1` at `257.13-1~deb13u1` | — | Forky source `261.2-1`; incompatible release, not adopted |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) | `libacl1` at `2.3.2-2+b1` | — | Forky/sid source `2.4.0-1`; ABI concerns, not adopted |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642), [78408](https://security-tracker.debian.org/tracker/CVE-2026-78408), [78409](https://security-tracker.debian.org/tracker/CVE-2026-78409), [78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) | `bsdutils` `1:2.41.5-0+deb13u1`; `libblkid1`, `liblastlog2-2`, `libmount1`, `libsmartcols1`, `libuuid1`, `mount`, `util-linux` at `2.41.5-0+deb13u1`; `login` at `1:4.16.0-2+really2.41.5-0+deb13u1` | — | Forky/sid source `2.42.3-1`; incompatible release, not adopted |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) | `perl-base` at `5.40.1-6+deb13u1` | — | Forky/sid source `5.42.3-1`; incompatible release, not adopted |

The `--pull` build resolved the latest `python:3.12-slim` to platform digest
`f77ac9e4…`. Explicitly pulling the compatible `python:3.12-slim-trixie`
resolved to the **same digest**, so switching the tag would not reduce findings.
No Dockerfile or Python pin change is justified. A build of these same images
with a future patched stable base, followed by fresh Trivy, application tests
and runtime smoke, is required before gate reassessment. This recheck does not
claim runtime or acceptance-environment verification.

## Earlier baseline and reduction

## Evidence and method

The baseline is GitHub Actions [run 36050773275](https://github.com/zzhassyn/govtech_case1/actions/runs/36050773275)
for main commit `307339fcd4cddea6f5d4f0acd157da7e4053bf67`. Its preserved image
artifacts report backend 52 HIGH, worker 44 HIGH, MLflow 44 HIGH, all with 0
CRITICAL. The CI reports were generated on 2026-09-24; the artifact format does
not record its vulnerability DB update time. The image IDs below identify those
exact CI builds, not the changed branch.

For the branch image, `docker build --pull --no-cache --target production` rebuilt
the backend from `python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f`.
Pinned Trivy `0.58.2` (`aquasec/trivy@sha256:665030f4d33a82c1e8d9d5e0453365842236723c1ee5cc3becca698268e66a56`)
scanned exported image archives without a Docker socket. The local scanner DB
was updated at `2026-09-26T01:14:39Z`, downloaded at `04:40:06Z`. Raw local
reports are in ignored `tmp/security-local/`; they are not a Git artifact.

| Build | Content ID | HIGH | CRITICAL | Gate |
|---|---|---:|---:|---|
| CI backend | `sha256:39a8600bdaa9a083bdcbb182b47289d3de7ef8cea53cb90343d5d2ae30d00947` | 52 | 0 | FAIL |
| CI worker | `sha256:3d5112d4adf394af7beeb23ca9a03aedb781a90460ddbf0fe720e1adbd0c80bb` | 44 | 0 | FAIL |
| CI MLflow | `sha256:085cdf3320b78236383ecbb8eefc9e45b03d8781cbe0af5f6807087ef417287e` | 44 | 0 | FAIL |
| Branch backend before change, fresh DB | `sha256:2f4c8facc2a8b7bb050644ccf41232b6d425eb207d2a70afc8953b1a4d0ceabf` | 52 | 0 | FAIL |
| Branch backend after change, fresh DB | `sha256:41e6b7d8623f8be5b9208c6525f4c92378e446b81edc721fedeb86478711ac12` | 44 | 0 | FAIL |

The backend-only difference was the production installation of `curl` and its
libraries for a liveness check. Production now uses Python's standard library;
the Compose development target still installs `curl` because its existing
Compose healthcheck calls it. The production healthcheck was exercised in a
network-isolated disposable container with a synthetic loopback HTTP server:
Docker reported `healthy`, exit code 0, and user `medsignal`. This checks the
healthcheck mechanism, not full backend readiness.

## Remaining findings in the rebuilt backend

The 44 HIGH rows are **8 distinct advisories**, repeated across related Debian
binary packages. Trivy reported no fixed Debian version for these findings in
the 2026-09-26 DB and no HIGH/CRITICAL Python package finding in this image.
The original CI worker and MLflow reports showed the same eight advisories;
at that point those images had not yet been rebuilt from this branch. The
final HEAD scan above supersedes that gap.

| Advisory | Scanner rows | Representative package/version | Disposition |
|---|---:|---|---|
| CVE-2025-69720 | 4 | `libncursesw6 6.5+20250216-2` | Open |
| CVE-2026-16742 | 2 | `libsystemd0 257.13-1~deb13u1` | Open |
| CVE-2026-54369 | 1 | `libacl1 2.3.2-2+b1` | Open |
| CVE-2026-76642 | 9 | `bsdutils 1:2.41.5-0+deb13u1` | Open |
| CVE-2026-78408 | 9 | `bsdutils 1:2.41.5-0+deb13u1` | Open |
| CVE-2026-78409 | 9 | `bsdutils 1:2.41.5-0+deb13u1` | Open |
| CVE-2026-78410 | 9 | `bsdutils 1:2.41.5-0+deb13u1` | Open |
| CVE-2026-9538 | 1 | `perl-base 5.40.1-6+deb13u1` | Open |

Debian's [util-linux tracker](https://security-tracker.debian.org/tracker/source-package/util-linux)
and individual [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642)
entry list supported bookworm/trixie as vulnerable and a fix in forky/sid.
The [CVE-2026-9538 tracker](https://security-tracker.debian.org/tracker/CVE-2026-9538)
also lists bookworm/trixie as vulnerable. Moving the production image to an
unstable distribution, suppressing findings, or recording an unapproved risk
acceptance would not satisfy the project security gate. Recheck vendor updates
and rebuild/rescan exact final images when fixes become available.

The image-risk acceptance manifest remains empty. **U1-04 is not activated by
these scan results:** none of the reported blocking findings is in a Python
package. No new requirements pins were changed. The final worker/MLflow
rebuild and scan are recorded above. Runtime acceptance is documented
separately and the overall image gate remains **FAIL**.
