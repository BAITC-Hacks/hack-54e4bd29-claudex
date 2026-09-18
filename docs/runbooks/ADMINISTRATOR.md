# MedSignal Administrator Runbook

## Identity и scope

MedSignal не хранит пароли. Keycloak/corporate OIDC выпускает JWT, backend
проверяет подпись, issuer, audience и срок, затем формирует `SecurityContext`.

Роли: `ADMIN`, `HEALTH_AUTHORITY`, `REGIONAL_ANALYST`, `HOSPITAL_MANAGER`,
`HOSPITAL_ANALYST`. Роль задаёт permissions, PostgreSQL scope — доступные
regions/hospitals. Одной роли недостаточно для ограниченного доступа.

Development realm содержит только synthetic users и local-only credentials и
запрещён для production. Corporate SSO — внешняя зависимость до подключения
настоящего IdP.

- Out-of-scope объект возвращается как 404.
- Unmapped source organizations доступны только GLOBAL scope.
- Fuzzy mapping запрещён; допустимы `OFFICIAL_REFERENCE` и `MANUAL_APPROVED`.
- Нельзя создавать фиктивный Hospital для GLOBAL facts/signals.

## Imports и Audit

Admin endpoints возвращают только metadata и агрегированное качество:

```text
GET /api/v1/data-imports
GET /api/v1/data-imports/{id}
GET /api/v1/data-imports/{id}/quality
```

API не принимает произвольный filesystem path. Quarantine не публикуется через
analytics. Quality/Audit messages не должны содержать patient identifiers.

## Production configuration gate

Обязательны: уникальные external secrets; `APP_DEBUG=false`;
`AUTH_TEST_MODE=false`; HTTPS OIDC issuer; `FORCE_HTTPS=true`; конкретные CORS
origins и trusted hosts; private data services; provisioned IdP; утверждённые
TLS/DNS/firewall/VPN. Нельзя обходить gate ослаблением authentication, CORS или
network isolation.

`.env` — только локальный ignored-файл. HMAC pseudonymization key нельзя
печатать или менять без миграционного плана: ротация разрывает связность.
