# FORGE — Framework for Ordered Review and Guaranteed Enhancement

A deterministic software analysis framework. Finds every gap in a project — security, resilience, performance, operations, code quality — and produces a prioritized fix plan.

## How it works

Three-level structure:

- **BQ** (Broad Question) — opens a category of analysis
- **TQ** (Targeted Question) — narrows scope within the BQ
- **DQ** (Diagnostic Question) — specific enough that the answer either reveals a gap or confirms none

Every DQ resolves to: `PASS` · `GAP` · `ACCEPTED` · `BLOCKED` · `N/A`

GAPs become Fix Specifications. After all DQs in a BQ produce fixes, re-run the DQs against those fixes. Loop until stable.

## Disciplines (15)

| File | Purpose |
|------|---------|
| `security.yaml` | Auth, secrets, injection, transport, supply chain |
| `architecture-review.yaml` | Coupling, boundaries, scalability |
| `code-review.yaml` | Correctness, maintainability, patterns |
| `performance-review.yaml` | Throughput, latency, resource limits |
| `operations-review.yaml` | Deploy, observability, runbooks |
| `audit.yaml` | Compliance, audit trails, access logging |
| `test-specification.yaml` | Coverage, test quality, CI gates |
| `post-incident-review.yaml` | Root cause, blast radius, prevention |
| `migration-planning.yaml` | Risk, rollback, data integrity |
| `troubleshooting.yaml` | Diagnosis playbooks |
| `documentation.yaml` | Coverage, accuracy, staleness |
| `intake.yaml` | Project onboarding checklist |
| `gates.yaml` | Go/no-go criteria per lifecycle phase |
| `router.yaml` | Triage — which disciplines to run for a given concern |
| `people-performance-review.yaml` | Team process, delivery cadence |

## Usage

```bash
# Full audit — all disciplines
python engine.py --project /path/to/project --mode full

# Triage — specific disciplines
python engine.py --project /path/to/project --discipline security code-review

# Pre-launch gate check
python engine.py --project /path/to/project --mode gates
```

Results written to `RESULTS-<project>-<date>.md`.

## Intended operators

AI agents (Claude Code) and technical leads. The framework assumes the operator can read source code, execute commands on the target system, and access infrastructure.

**Out of scope:** Business viability, UX design, market fit, team management.

## Answer verification (AI operators)

For every PASS answer, cite the specific file and line that handles it. If evidence is ambiguous, mark BLOCKED — never mark PASS on "it probably works."
