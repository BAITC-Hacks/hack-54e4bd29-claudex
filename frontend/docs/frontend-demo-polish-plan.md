# Frontend Demo Polish Plan

**Base:** `demo/integration` at `5a8669167ed7f504a36b0c74c4a1f86c30d88ef8`

**Goal:** Make MedSignal presentation-ready for a public-sector healthcare demo without changing backend contracts, forecast calculations, or Copilot request behavior.

## Work packages

### Task 1: Authentication-aware shell and landing

**Files:** `src/app/layout.tsx`, `src/app/page.tsx`, `src/components/site-header.tsx`, new shell/landing components, and component tests.

   - Replace the redirecting home route with a factual public landing page.
   - Show only brand, research/demo status, and sign-in before authentication.
   - Add a desktop sidebar, contextual top bar, and accessible mobile drawer after authentication.
   - Tests cover hidden public navigation, authenticated routes, drawer Escape/focus behavior, and landing content.

**Cycle:** write the shell/landing tests; run them and confirm they fail on the current top-navigation/redirect behavior; implement; rerun the focused tests and the frontend suite.

### Task 2: Situation center hierarchy and copy

**Files:** `src/app/command-center/page.tsx`, analytics presentation components, and focused tests.

   - Keep the existing API-backed data flow while reorganizing the main screen around four KPIs, referral trend, regional context, organizations requiring attention, signals, and global forecast evidence.
   - Replace misleading wording such as ministry affiliation, “real aggregates,” “actual load,” and “real source rows.”
   - Tests cover truthful synthetic/historical labels and understandable loading, empty, and error states.

**Cycle:** add focused presentation tests; confirm the old hierarchy/copy fails them; implement with existing queries only; rerun focused and full tests.

### Task 3: Signals, forecast, and Copilot polish

**Files:** signal list/detail presentation, `src/features/forecasting/components/referral-forecast-card.tsx`, `src/features/copilot/copilot-entry.tsx`, and their tests.

   - Make signal severity, title, organization, change, time, and status easy to scan at desktop and mobile widths.
   - Keep deterministic evidence separate from the explicitly requested Copilot drawer.
   - Preserve `DAILY_REFERRAL_COUNT`, `GLOBAL`, validation period, model, MAE/baseline MAE units, stale state, and unavailable state.

**Cycle:** extend existing behavior tests; confirm new semantics fail first; implement presentation-only changes; rerun focused and full tests.

### Task 4: Responsive and release verification

**Files:** responsive styles and screenshot artifacts only; no QA-owned Playwright tests.

   - Inspect 390, 768, 1280, and 1440 pixel viewports.
   - Run `npm run lint`, `npm run typecheck`, `npm test`, and `npm run build`.
   - Capture screenshots and prepare branch/commit/file/test handoff details for `demo/integration`.

**Cycle:** use the browser to inspect each viewport, correct frontend-only defects with a failing test when behavior changes, then run every required verification command.

## Constraints

- Frontend-only changes.
- No invented data or unsupported controls.
- No automatic Copilot requests.
- No official government branding or unsupported realtime claims.
- No Playwright/QA infrastructure changes owned by the integration agent.
