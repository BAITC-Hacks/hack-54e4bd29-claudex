# Keycloak production realm contract

The committed JSON realm is **local development data only**. It contains
synthetic users and fixed `local_dev_only` credentials so automated acceptance
can exercise real signed tokens. `docker-compose.production.yml` removes that
mount and does not bootstrap those users.

The production identity administrator must provision a realm named
`medsignal` (or set the matching issuer) with:

- asymmetric token signing (`RS256` or an approved successor);
- the audience `medsignal-api` in access tokens;
- Authorization Code + PKCE for the public frontend client;
- no password storage in MedSignal;
- realm roles `ADMIN`, `HEALTH_AUTHORITY`, `REGIONAL_ANALYST`,
  `HOSPITAL_MANAGER`, `HOSPITAL_ANALYST`;
- HTTPS issuer reachable by browsers and a trusted internal JWKS endpoint;
- corporate SSO, MFA, account lifecycle and session policy supplied by the
  organization.

Corporate SSO is an **EXTERNAL DEPENDENCY / NOT CONFIGURED** in Phase 8 because
no production IdP, DNS name or certificates were provided.
