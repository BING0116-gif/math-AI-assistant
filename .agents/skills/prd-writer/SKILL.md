---
name: prd-writer
description: Write enterprise-ready, agent-executable Product Requirements Documents (PRDs) through interactive guided sessions with ambiguity tracking. Produces PRDs that coding agents can execute with low drift, low rework, and strong governance.
metadata:
  author: thomasrohde
  version: 1.0.0
triggers:
  - /prd-writer
  - /prd
---

# PRD Writer

You are guiding the user through writing an enterprise-ready PRD that serves three purposes simultaneously:

1. **A product contract** — what problem is being solved, for whom, and how success is measured.

2. **An execution contract for coding agents** — how the work should be sliced, constrained, validated, and handed off.

3. **A governance artifact** — approved stack, security posture, compliance constraints, and review rules.

### Core philosophy

In the agentic era, a PRD must do more than explain *what* to build and *why*. It must make execution, validation, and governance explicit. A weak PRD pushes ambiguity downstream into the agent loop, where it becomes drift, retries, and noisy pull requests. Your job is to surface and resolve that ambiguity *now*, before any code is written.

**You must use the AskUserQuestion tool aggressively throughout this process.** Every section of the PRD requires specific information from the user. Do not guess, assume, or fill in placeholders. If the user's answer is vague, ask a follow-up. If a critical detail is missing, ask for it. The goal is zero ambiguity in the final document.

### How to run this skill

#### Phase 1: Understand the project

Before writing anything, conduct a structured interview. Ask the user these questions using AskUserQuestion — one or two at a time, not all at once (that would be overwhelming):

**Round 1 — The basics:**

- What is the product or feature you want to build?

- Who are the primary users? What problem does this solve for them?

- Why now? What is the trigger or business driver?

**Round 2 — Scope and boundaries:**

- What is explicitly in scope for this PRD?

- What is explicitly out of scope or a non-goal?

- Are there any forbidden approaches or shortcuts?

**Round 3 — Technical context:**

- Is there an existing codebase? If so, what repo(s)?

- Is the tech stack already decided, or does it need to be chosen?

- Are there compliance, security, or regulatory constraints?

**Round 4 — Delivery shape:**

- How should the work be phased? Are there natural milestones?

- Who needs to review and approve?

- What does "done" look like?

Adapt these questions to the user's context. If they've already provided some of this information, acknowledge it and skip to what's missing. If they mention a domain you're unfamiliar with, ask clarifying questions about it.

#### Phase 2: Draft the PRD section by section

Work through each section of the PRD in order. For each section:

1. **Explain** what the section covers and why it matters (briefly).

2. **Ask** the user for the specific information needed using AskUserQuestion.

3. **Draft** the section based on their answers.

4. **Confirm** the draft with the user before moving on.

If the user says "I don't know" or "skip this for now," mark the section with an ambiguity tag (see Phase 3) and move on. Do not block progress, but do record what's unresolved.

Use the PRD template from `references/template.md` as the structural backbone. Every section in the template should appear in the final PRD.

##### Section-specific guidance

**Document Control (Section 1):** Ask for: PRD title, owner name, target repository, data classification, any compliance tags. If the user doesn't have formal approvers yet, note it as an open question.

**Executive Summary (Section 2):** Draft this after Sections 3-5, when you have enough context. Keep it to 5-10 lines. Ask the user to confirm the framing.

**Problem Statement (Section 3):** Push for specificity. "Users are frustrated" is not enough — ask *which* users, *what* frustrates them, *how often*, and *what it costs*. Ask for measurable outcomes: reduced cycle time, fewer manual steps, improved completion rate, lower operational risk, fewer defect escapes.

**Scope (Section 4):** This section prevents agent sprawl. Be especially thorough here. Ask the user to confirm each non-goal individually. If the user gives a broad scope, push them to narrow it by asking: "Can this be split into smaller deliverables?"

**Personas and Scenarios (Section 5):** Ask the user to describe their top 1-3 user types and what they do. Push for scenario language that can be turned into tests: "Given X, when Y, then Z."

**Functional Requirements (Section 6):** Each requirement needs: unique ID, plain-language description, rationale, priority (Must/Should/Could), acceptance criteria, and a testability note. Ask the user to walk through requirements one by one. If they give a bullet list, expand each into the full format by asking follow-up questions.

**Non-Functional Requirements (Section 7):** Walk through each category (performance, resilience, accessibility, observability, security, maintainability) and ask if there are expectations. Don't skip observability — in enterprise contexts it's a production requirement, not an optional extra.

**Tech Stack Decision (Section 8):** This is a first-class section, not a footnote. Ask about: language(s), framework(s), runtime(s), database, CI/CD, test framework, linting/formatting tools, package manager, deployment target. Ask what alternatives were considered and why they were rejected. Document guardrails: what the agent may not substitute without approval.

**Architecture and Repo Boundaries (Section 9):** Ask which directories/modules will change and which are off-limits. This stops agents from wandering across unrelated services.

**Build/Run/Validate Contract (Section 10):** This is one of the most critical sections for agent execution. Ask for the exact commands for: setup, local run, lint, tests, build, and security scans. Also ask about runtime versions, environment variables, preconditions, and known flaky steps. If the user doesn't have these yet (e.g., greenfield project), work with them to define what they *will* be.

**Security, Risk, and Compliance (Section 11):** Ask about: data classification, secret handling, access scope, prohibited data in logs, threat assumptions, review requirements before merge. This section is mandatory for enterprise use.

**Observability and Operational Readiness (Section 12):** Ask about: required logs, metrics, alerts, dashboards, audit trails, retention policy, support ownership.

**Phase Plan (Section 13):** Break the work into epics that fit one agentic coding session. Read `references/epic-sizing.md` for the sizing rubric. Organize epics under phase headings (Phase 0 — Foundations, Phase 1 — Core Vertical Slices, Phase 2 — Hardening, Phase 3 — Rollout). Each epic in the phase plan must be a markdown checkbox item (`- [ ] E0: Name — objective`) so the PRD doubles as a living progress tracker — teams and agents can check off epics as they are completed.

**Epic Cards (Section 14):** For each epic in the phase plan, create a detailed card. Use checkboxes (`- [ ]`) for acceptance criteria and evidence items within each card so they can be checked off during implementation. Ask the user to confirm each epic's scope and validation commands.

**Open Questions and Decision Log (Section 15):** Compile all unresolved items from the drafting process. Ask the user if there are additional open questions.

**Definition of Done (Section 16):** Present the standard definition-of-done checklist and ask the user to confirm or modify it.

#### Phase 3: Track and report ambiguity

Throughout the process, maintain an internal ambiguity tracker. When you encounter any of these situations, log it:

- The user said "I don't know" or "skip this"

- The user gave a vague answer that you couldn't fully resolve

- A decision depends on information not yet available

- A requirement is stated but has no acceptance criteria

- A technical choice is deferred

- A security or compliance question is unanswered

At the end of the PRD, add a dedicated section:

```
## Appendix: Unresolved Ambiguity Log

| # | Section | Topic | What's Missing | Impact | Suggested Next Step |
|---|---------|-------|----------------|--------|---------------------|
| 1 | Tech Stack | Database choice | User is evaluating PostgreSQL vs DynamoDB | Blocks E3 (data layer epic) | Decision needed before Phase 1 starts |
```
**This section is mandatory.** Even if the user resolves everything (rare), include the section with a note: "All ambiguities were resolved during drafting."

Before finalizing, present the ambiguity log to the user using AskUserQuestion and ask: "Here are the unresolved items. Can we resolve any of these now, or should they remain as open questions?"

#### Phase 4: Write the file

Save the completed PRD as `PRD.md` in the current working directory (or wherever the user specifies). Use the full template structure from `references/template.md`.

#### Phase 5: Suggest companion files

After the PRD is written, explain the companion file pattern to the user:

- `AGENTS.md` or repo instructions — how the repo should be understood and operated

- `PLAN.md` — ordered milestones and validation commands

- `IMPLEMENT.md` — execution runbook for the agent

- `DECISIONS.md` — architecture and implementation decision log

- `STATUS.md` — current progress, blockers, and evidence

Ask if they want you to scaffold any of these. The PRD is the authoritative document; companion files specialize execution.

### Anti-patterns to watch for

When interviewing the user, push back if you see any of these smells:

- "Use whatever stack you think is best." — The stack must be explicitly approved.

- "Refactor the app for quality." — Needs a target boundary.

- "Add tests as needed." — Needs specific coverage expectations.

- "Production ready" with no security, observability, or support requirements.

- Acceptance criteria that are subjective only ("it should feel fast").

- No explicit non-goals.

- No command-level validation.

- One giant implementation phase.

When you spot these, use AskUserQuestion to dig deeper. Explain *why* the detail matters for agent execution — not to be pedantic, but because vague instructions cause agent drift, retries, and noisy PRs.

### Review checklist

Before presenting the final PRD, verify:

- Stack is explicitly approved

- Alternatives and forbidden substitutions are clear

- Exact commands for setup, test, lint, build, validation exist

- Epics are small enough for one agentic coding session

- Each epic has acceptance criteria and evidence requirements

- Boundaries, off-limits areas, and source-of-truth systems are named

- Security, secrets, compliance, and data rules are explicit

- Observability and retention requirements are documented

- Human review/approval policy is clear

- A new engineer could understand "done" without hidden context

- Ambiguity log is complete and presented to user

If any item fails, ask the user to resolve it before finalizing.
