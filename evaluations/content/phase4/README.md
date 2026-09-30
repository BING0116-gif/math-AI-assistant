# Phase 4 practice content audit

The 195 questions are generated from
`app/services/phase5_standard_practice.py`. Machine checks cover the required
2 basic, 2 standard, 1 advanced shape, complete stems/options/answers/analysis,
unique stems and options, deterministic answer references, and primary knowledge
point alignment.

Generate the audit and review worksheet with:

```powershell
python -m scripts.audit_phase4_practice --output artifacts/phase4/content
```

The command intentionally reports `machine_passed_human_pending` until an
accountable reviewer completes all required rows. At least one question per
knowledge point is required; formula/example questions and all high-risk theorem,
limit, improper-integral, extrema, geometry, work, and fluid-force questions are
also mandatory reviews. Blank notes or placeholder reviewer identifiers do not
complete the gate.

Content corrections must be made in the authored source and reseeded through the
normal idempotent seed path. Do not edit a deployed database to make the report
pass.
