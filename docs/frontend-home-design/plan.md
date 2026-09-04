# Relay Frontend Home Design Plan

## Context reviewed

- `RELAY-SPEC.md`, especially the ground rules, performance targets, and F9 observability dashboard requirements.
- `ARCHITECTURE.md`, especially the dashboard boundary: UI reads and operator actions go through the control plane and never access Postgres or Redis directly.
- `RELAY-production-folder-structure.md`, especially the React frontend layout under `apps/frontend/src`.
- `docs/design/RELAY Dashboard.dc.html` as the visual and content reference.
- The existing Vite/React entry points, TypeScript configuration, ESLint setup, and empty `pages/Home` production folder.

## Architecture and placement

The landing page belongs in `apps/frontend/src/pages/Home/`, which already exists in the repository and was explicitly requested. The production folder guide enumerates operator pages but does not name a public Home page; using the existing responsibility-based page folder is the smallest consistent extension. Shared global tokens and reset styles belong in `apps/frontend/src/styles/`.

The page uses static presentation data only. It will not talk directly to Redis, Postgres, or backend endpoints. Later console views can replace visual sample data through control-plane API and WebSocket integrations.

## Task 1 — Home foundation and hero

### Goal

Create a production-quality first viewport that establishes Relay's visual identity and explains its core promise immediately.

### Scope

- `apps/frontend/src/app/App.tsx`
- `apps/frontend/src/app/main.tsx`
- `apps/frontend/index.html`
- `apps/frontend/src/pages/Home/HomePage.tsx`
- `apps/frontend/src/pages/Home/HomePage.css`
- `apps/frontend/src/styles/global.css`
- `.gitignore` to exclude TypeScript incremental build artifacts
- `apps/frontend/tests/unit/home-page.test.tsx` if the current dependency setup supports DOM tests without adding a package

### Approach

- Wire the application root to a semantic Home page.
- Define a small set of CSS custom properties for color, typography, spacing, and motion.
- Build an accessible header, hero copy, calls to action, trust signals, and a responsive operations-preview panel.
- Respect reduced-motion preferences and keyboard focus.
- Use inline SVG only for small decorative/data graphics so no image or icon dependency is required.

### Validation

- Run the frontend TypeScript/Vite production build.
- Run ESLint.
- Inspect the page in a real browser at desktop and mobile viewport sizes.
- Confirm the browser console has no application errors.

### Dependency

None.

## Task 2 — Product proof sections

### Goal

Explain how Relay handles failures, traces work across the queue boundary, and surfaces operational problems.

### Scope

Add focused sections below the hero within the Home page and extend its page-local styles.

### Approach

Use concise feature narratives and lightweight visual components for leases/recovery, trace continuity, priority lanes, and grouped DLQ triage. Keep claims aligned with the specification and avoid pretending static examples are live data.

### Validation

- Production build and lint.
- Browser review of content flow, responsive layout, and semantic heading order.

### Dependency

Task 1.

## Task 3 — Completion, interaction, and regression coverage

### Goal

Finish the page with the workflow explanation, final call to action, footer, interaction polish, and maintainable regression coverage.

### Scope

Complete Home-page sections, refine responsive behavior, and add the smallest appropriate test setup only if needed.

### Approach

- Add the enqueue/process/observe workflow and final conversion section.
- Ensure links and controls have truthful destinations or intentionally non-navigation button behavior.
- Validate contrast, keyboard focus, reduced motion, narrow layouts, and overflow.
- Add focused component tests if the repository's frontend testing foundation is available; otherwise document the missing test runner without introducing one solely for this page.

### Validation

- Production build and lint.
- Component tests when supported.
- Browser review at representative desktop and mobile widths with console inspection.

### Dependency

Tasks 1 and 2.

## Edge cases and failure modes

- Long content must wrap without overflowing narrow screens.
- Decorative motion must stop when the user prefers reduced motion.
- Navigation must remain usable without a pointer.
- The operations preview must be identified as illustrative, not live system state.
- The page must remain useful if web fonts or JavaScript animations are unavailable.

## Public behavior

The frontend root renders the new public Home page. Primary actions are visible and semantically labeled. No public API, data model, or backend contract changes.

## Documentation and exports

- Export `HomePage` from its page module for use by the app root.
- Keep feature decisions in this folder; no broad architecture document update is needed because system boundaries do not change.

## Definition of done

- All three tasks are complete and reviewed in sequence.
- The Home page reflects Relay's specified behavior accurately.
- Production build and lint pass.
- Desktop and mobile browser checks pass without console errors or horizontal overflow.
- No new runtime dependency is added.
