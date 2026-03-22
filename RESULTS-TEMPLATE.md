# FORGE Run: [PROJECT NAME] — Results

**Date:** YYYY-MM-DD
**Target:** [path/description of what was analyzed]
**Mode:** Full / Triage (BQs: XX, XX, XX)
**Operator:** [AI model or person]
**Version:** FORGE v1.2

---

## Run Metrics

| Metric | Value |
|--------|-------|
| Total DQs evaluated | |
| PASS | |
| GAP | |
| ACCEPTED | |
| BLOCKED | |
| N/A | |
| Fixes proposed | |
| Fixes implemented | |
| KB entries generated | |
| Elapsed time | |

---

## BQ-XX: [CATEGORY NAME]

### TQ-XX.X: [Targeted Question Area]

| DQ | Answer | State | Evidence |
|----|--------|-------|----------|
| [Question text] | [Answer] | PASS/GAP/ACCEPTED/BLOCKED/N/A | [File:line or justification] |

*(Repeat for each TQ and DQ)*

---

## Gap Summary

| ID | BQ | TQ | Description | Severity | Fix |
|----|----|----|-------------|----------|-----|
| G-001 | XX | XX.X | [Gap description] | Critical/High/Medium/Low | [Fix reference] |

---

## Fixes Applied

| ID | Files Changed | Description | Gaps Addressed |
|----|--------------|-------------|----------------|
| F-001 | [files] | [what was changed] | G-001, G-002 |

---

## Accepted Risks

| ID | BQ | Description | Reason for Acceptance |
|----|-----|-------------|----------------------|
| A-001 | XX | [what's not being fixed] | [why it's acceptable] |

---

## Blocked Items

| ID | BQ | DQ | Blocker | Resolution |
|----|-----|-----|---------|------------|
| B-001 | XX | [question] | [why it can't be answered] | [how it was resolved or left] |

---

## Conflicts Resolved

| Fix A | Fix B | Conflict | Resolution |
|-------|-------|----------|------------|
| F-XXX | F-XXX | [what conflicts] | [compromise or priority decision] |

---

## Verification Pass

### VP-01: Fix Conflict Check
- [ ] No proposed fixes contradict each other
- [ ] Implementation order is clear
- [ ] Atomic deployment requirements identified

### VP-02: Regression Risk
- [ ] Each fix has a rollback plan
- [ ] No fix breaks existing behavior
- [ ] KB checked for similar past issues

### VP-03: Security Review of Fixes
- [ ] No new attack surface introduced
- [ ] No existing controls weakened
- [ ] No new dependencies with vulnerabilities

### VP-04: Completeness Check
- [ ] Every selected BQ addressed
- [ ] All DQ loops run to exhaustion
- [ ] All BLOCKED items resolved or escalated
- [ ] All gaps either fixed or explicitly accepted

### VP-05: Acceptance Criteria
- [ ] Each fix has "done" criteria defined
- [ ] Verification method specified per fix
- [ ] Overall success criteria met

---

## Knowledge Base Entries

### KB-XXX: [Pattern Name]
- **Category**: BQ-XX / TQ-XX.X
- **Trigger**: [when this pattern applies]
- **Pattern**: [what the common gap is]
- **Impact**: [what happens if unaddressed]
- **Source**: [this project]
- **Added to Framework**: Yes/No

---

## Deferred Items

| Gap | BQ | Priority | Reason for Deferral |
|-----|-----|----------|-------------------|
| [description] | XX | High/Medium/Low | [why it's deferred, not accepted] |
