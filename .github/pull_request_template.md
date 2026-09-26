## Problem and resulting behavior

Describe the concrete trigger, previous behavior, new behavior, and scope of this PR.

## Changes and boundaries

List the files/modules changed and any dependency on another PR. Explain any
change to API contracts, migrations, data scope, security controls or model
claims. Link the approved decision when one is required.

## Verification

| Check | PASS / FAIL / NOT TESTED | Command, CI job or evidence |
|---|---|---|
| Relevant unit/integration tests | | |
| Ruff / mypy / import-linter where applicable | | |
| Frontend lint / typecheck / tests / production build where applicable | | |
| Synthetic data/privacy/security checks where applicable | | |
| Final-image Trivy gate when an image changes | | |
| Isolated runtime/browser verification when needed | | |

## Ownership and review

Select reviewers from [CODEOWNERS](CODEOWNERS) for every changed zone. For a
cross-zone change, request each affected owner: U1 `@zzhassyn` (backend, data,
ML, SQL/migrations, Python manifests), U2 `@Alim-Rakhmet` (infrastructure,
CI, Compose, Dockerfiles), U3 `@aldabergenuly` (frontend and package manifests).
The additional account `@albqqd` has no assigned ownership zone. File-type
exceptions in CODEOWNERS take precedence over their containing directory.

- [ ] Relevant owners have reviewed the API, schema, security and UI contracts.
- [ ] Any failed required gate is recorded as a blocker; no blanket acceptance
      or silent suppression is claimed.
- [ ] No credentials, tokens, patient-level data or unsafe browser artifacts
      are attached.

Record the exact source SHA and environment for runtime or performance claims.
`NOT TESTED` is an honest result, not a pass. Do not attach tokens, private
datasets, patient-level values, or raw sensitive logs.

## Reviewer notes

- [ ] An independent human reviewer with the relevant backend/data/ML,
      infrastructure/security/CI or frontend/UX expertise has been requested.
- [ ] The reviewer can assess the final diff and any cross-module contract.
- [ ] No self-approval or exception to a failed required check is claimed.

This template records evidence; it does not itself enforce branch protection
or required checks. GitHub settings remain the responsibility of authorized
repository administrators.
