# PRD Template

Use this exact structure when generating the PRD. Every section must appear in the final document. If a section has no content yet, include it with a placeholder noting it needs to be filled.

````md
# <Product / Feature Name> PRD

## 1. Document Control
- Version:
- Status: Draft | In Review | Approved | Superseded
- Owner:
- Product Owner:
- Engineering Owner:
- Security Reviewer:
- Architecture Reviewer:
- Compliance Reviewer:
- Target Repository/Repositories:
- Linked ADRs:
- Linked Diagrams:
- Data Classification:
- Regulatory / Policy Tags:
- Last Updated:

## 2. Executive Summary
<5-10 lines describing the problem, users, target outcome, and top constraints>

## 3. Problem Statement
### Current State

### Pain / Opportunity

### Why Now

## 4. Business Outcomes and Success Metrics
| Metric | Baseline | Target | Measurement Method | Owner |
|---|---:|---:|---|---|
| Example: task completion time | 25 min | 10 min | telemetry | Ops |

## 5. Scope
### In Scope
-

### Out of Scope
-

### Non-Goals
-

### Explicit Boundaries
-

## 6. Personas and Scenarios
### Primary Persona(s)
-

### Critical User Journeys
1.
2.

### Failure / Edge Scenarios
-

## 7. Functional Requirements
| ID | Requirement | Priority | Rationale | Acceptance Criteria | Testability Notes |
|---|---|---|---|---|---|
| FR-1 |  | Must |  |  |  |

## 8. Non-Functional Requirements
| Category | Requirement | Target / Policy | Validation |
|---|---|---|---|
| Performance |  |  |  |
| Resilience |  |  |  |
| Accessibility |  |  |  |
| Observability |  |  |  |
| Security |  |  |  |
| Maintainability |  |  |  |

## 9. Tech Stack Decision
### Approved Stack
- Frontend:
- Backend:
- Runtime(s):
- Database / Storage:
- Messaging:
- Infra / Hosting:
- CI/CD:
- Testing:
- Lint / Format / Type-check:
- Package Manager(s):
- Approved External Services:

### Version Expectations
-

### Decision Drivers
-

### Alternatives Considered
- Option A:
- Option B:

### Chosen Option and Rationale
-

### Consequences / Trade-offs
-

### Stack Guardrails
- The agent must not substitute framework/runtime without approval.
- The agent must not add new paid SaaS dependencies without approval.
- The agent must not introduce a database or queue technology not listed above.

## 10. Architecture and Repo Boundaries
### System Context
-

### Components / Modules
-

### Likely Touched Paths
- `/src/...`
- `/services/...`

### Off-Limits Paths
- `/legacy/...`
- `/regulated/...`

### Source-of-Truth Systems
-

## 11. Build / Run / Validate Contract
### Toolchain Versions
- Node:
- Python:
- Java:
- Docker:
- Other:

### Setup
```bash
# exact commands
```

### Run
```bash
# exact commands
```

### Lint / Type-check
```bash
# exact commands
```

### Tests
```bash
# exact commands
```

### Build / Package
```bash
# exact commands
```

### Security / Contract Checks
```bash
# exact commands
```

### Preconditions
-

### Postconditions
-

### Known Flaky or Slow Steps
-

## 12. Security, Risk, and Compliance
### Data Handling Rules
-

### Secrets Rules
-

### Access Scope / Least Privilege
-

### Prohibited Data in Prompts, Logs, or Traces
-

### Mandatory Human Review Gates
-

### Risk Notes
-

## 13. Observability and Operational Readiness
### Logs
-

### Metrics
-

### Traces
-

### Alerts
-

### Audit Requirements
-

### Retention / Redaction Rules
-

### Support Ownership
-

## 14. Phase Plan

### Phase 0 — Foundations
- [ ] E0: <Epic name> — <one-line objective>
- [ ] E1: <Epic name> — <one-line objective>

### Phase 1 — Core Vertical Slices
- [ ] E2: <Epic name> — <one-line objective>
- [ ] E3: <Epic name> — <one-line objective>

### Phase 2 — Hardening & Enterprise Controls
- [ ] E4: <Epic name> — <one-line objective>

### Phase 3 — Rollout & Optimization
- [ ] E5: <Epic name> — <one-line objective>

## 15. Epic Cards
### E0 - <Epic Name>
- **Goal:**
- **Why this can fit one agentic coding session:**
- **Touched paths:**
- **Explicitly excluded paths:**
- **Dependencies:**
- **Required reviewers:**
- **Acceptance criteria:**
  - [ ] <Criterion 1>
  - [ ] <Criterion 2>
  - [ ] <Criterion 3>
- **Validation commands:**
```bash
# exact commands
```
- **Evidence to attach to PR:**
  - [ ] test output
  - [ ] screenshots / logs
  - [ ] migration notes
- **Rollback / fallback:**
- **Open questions:**

## 16. Open Questions and Decision Log
| Date | Topic | Question / Decision | Owner | Status |
|---|---|---|---|---|

## 17. Definition of Done
- [ ] Functional requirements in scope are complete
- [ ] Acceptance criteria are met
- [ ] Validation commands pass
- [ ] Documentation is updated
- [ ] Security / compliance checks are complete
- [ ] Observability is in place
- [ ] Required reviewers approved
- [ ] Rollback / support notes exist where relevant

## Appendix: Unresolved Ambiguity Log
| # | Section | Topic | What's Missing | Impact | Suggested Next Step |
|---|---------|-------|----------------|--------|---------------------|
| 1 |  |  |  |  |  |
````
