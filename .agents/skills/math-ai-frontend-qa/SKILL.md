---
name: math-ai-frontend-qa
description: Verify Vue 3 student-facing flows in this Math AI Assistant, especially chat/math rendering, error book, knowledge learning, profile, and dashboard UI. Use after frontend changes, API-client contract changes, responsive layout work, or when diagnosing a visual or interaction regression; combine Vitest/build evidence with browser-based runtime QA.
---

# Math AI Frontend QA

## Input

List changed routes/components/stores/API calls, primary student task, expected loaded/empty/error states, and target viewport sizes. Read the related route and existing API client before starting the server.

## Execute

1. Make a QA inventory that maps every user-visible claim and control to a functional check and visual state. Cover the changed flow plus one failure or empty state.
2. Run existing checks in `frontend/`: `npm run test` when tests cover the change, then `npm run build`.
3. Start the normal Vite app and use the built-in `browser:control-in-app-browser` skill for runtime validation. Check desktop and a 390 px-wide mobile viewport, route navigation, loading/error handling, keyboard/focus behavior, and KaTeX/Markdown rendering where applicable.
4. Compare outgoing frontend payloads and rendered fields to the FastAPI request/response model. Record screenshots or concrete browser observations for signed-off states.
5. Add a focused Vitest component/store test when behavior is deterministic. Propose committed Playwright specs only after the repository explicitly adopts `@playwright/test` and a stable seeded/mock backend; do not add browser dependencies solely for an ad-hoc check.

## Output

Return the QA inventory, commands/results, runtime evidence, viewport coverage, failed states, and API-contract mismatch.

## Verify

Require a successful production build. Do not sign off an interaction without exercising it through visible user input; do not sign off a visually central change without inspecting its rendered state.

## Do Not

Do not use DOM mutation or mocked store state as final UI proof, rely only on screenshots for functional behavior, alter user data in a shared environment, or claim Playwright coverage when no Playwright test was executed.
