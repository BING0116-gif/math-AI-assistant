# Epic Sizing for Agentic Coding Sessions

## What is an agentic coding session?

A single autonomous or semi-autonomous implementation run that ends in one reviewable outcome: a working increment, a bounded diff, passing validation commands, and a human-reviewable PR or patch set.

## Good session-sized epic

A well-sized epic:

- Delivers one coherent outcome
- Can usually be expressed as one reviewable PR
- Has a small set of touched surfaces
- Can be validated by a finite, explicit command set
- Does not require unresolved architectural decisions mid-flight
- Does not depend on external approvals during execution
- Does not combine product discovery with implementation

## Bad session-sized epic

A poorly sized epic:

- Spans multiple services plus infrastructure plus UI plus migration plus policy decisions
- Requires the agent to choose the stack as it goes
- Asks for "full refactor" without a target boundary
- Mixes "investigate," "design," and "implement everything" in one run
- Depends on hidden domain knowledge or undocumented systems

## Practical sizing heuristic

Prefer an epic that fits one of these shapes:

- **Scaffold** one bounded module or service
- **Implement** one user journey end-to-end behind a flag
- **Add** one integration with mocks and contract tests
- **Refactor** one subsystem with parity tests
- **Harden** one slice with auth, logging, validation, and tests
- **Migrate** one component or package boundary

Avoid using an epic as a project bucket. In agentic delivery, epics behave more like execution packets than broad themes.

## Recommended phase pattern

Use checkboxes for all phase items so the PRD doubles as a living progress tracker. Teams and agents check off items as they complete them.

### Phase 0 — Foundations
- [ ] Confirm stack
- [ ] Confirm architecture boundaries
- [ ] Establish repo instructions
- [ ] Establish command contract
- [ ] Set security and observability baselines
- Typical epics: repo bootstrap, CI scaffold, logging/tracing scaffold, auth scaffold

### Phase 1 — Core vertical slices
- [ ] Deliver the first valuable journeys end-to-end
- One journey per epic
- Feature flags where needed
- [ ] Full acceptance criteria and tests per slice

### Phase 2 — Hardening and enterprise controls
- [ ] Audit trail
- [ ] Role-based access control
- [ ] Compliance screens
- [ ] Error handling and resilience
- [ ] Migration and rollback automation

### Phase 3 — Rollout and optimization
- [ ] Dashboards and alerts
- [ ] Runbooks
- [ ] Docs and support content
- [ ] Performance tuning
- [ ] Cost optimization
