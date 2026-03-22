# FORGE — Framework for Ordered Review and Guaranteed Enhancement

**Version:** 1.2 (2026-03-21)

## Purpose & Audience

FORGE is a deterministic software analysis framework that identifies every gap in a software project — security, resilience, performance, operations, code quality, and AI/ML components — and produces a prioritized fix plan.

**Intended operators:** AI agents (Claude Code) and technical leads. The framework assumes the operator can read source code, execute commands on the target system, and access infrastructure.

**Use cases:**
1. **Full audit** — comprehensive analysis of existing software (all 13 BQs)
2. **Pre-launch review** — validate readiness before deployment
3. **Post-incident retrospective** — trace root causes and prevent recurrence
4. **Targeted assessment** — triage mode, run specific BQs relevant to a concern

**Out of scope:** Business viability, UX design, market fit, team management, project estimation.

---

## How This Works

Every software project runs through this framework. In **full mode**, all 13 BQs run top to bottom. In **triage mode**, the operator selects priority BQs based on the concern (see Triage Guide below).

Each **Broad Question** (BQ) opens a category of analysis. Under each BQ are **Targeted Questions** (TQ) that narrow the scope. Under each TQ are **Diagnostic Questions** (DQ) — specific enough that the answer either reveals a gap (which becomes a fix) or confirms no gap exists.

**The loop:** After all DQs under a BQ produce fixes, re-run the DQs against the proposed fixes. New gaps? New fixes. Repeat until stable. Then move to the next BQ.

### DQ Answer States

Every DQ must end in one of these states:

| State | Meaning | Action |
|-------|---------|--------|
| **PASS** | Handled correctly, verified | Move on |
| **GAP** | Not handled, needs a fix | Generate Fix Specification |
| **ACCEPTED** | Not handled, risk acknowledged | Document reason for acceptance |
| **BLOCKED** | Cannot be answered (no access, missing info) | Log blocker, revisit after other BQs |
| **N/A** | Does not apply to this project | Document why |

A DQ in BLOCKED state must be revisited before the run is complete. If still blocked at the end, it becomes either GAP or ACCEPTED with justification.

### Conflict Resolution

When fixes from different BQs conflict (e.g., security overhead vs. performance):
1. Document both fixes and the conflict
2. Evaluate: which gap has higher impact if left unfixed?
3. Design a compromise that addresses both, or explicitly accept the lower-priority gap
4. Record the decision and reasoning in the results

### Answer Verification (AI Operators)

When FORGE is run by an AI agent, answers are at risk of being marked PASS based on surface-level inspection. For each PASS answer, the AI must:
1. Cite the specific file, line, or config that handles it
2. If the evidence is ambiguous, mark BLOCKED instead of PASS
3. Never mark PASS based on "it probably works" — verify or block

**After all BQs are exhausted:** Run the Verification Pass (Section V).

---

## Triage Guide

For targeted assessments, use these BQ groups:

| Concern | Run These BQs | Skip |
|---------|--------------|------|
| **Security audit** | 04, 05, 10, 13 | 11, 12 |
| **Production readiness** | 06, 07, 09 | 12 |
| **Performance issue** | 03, 11 | 01, 12 |
| **Post-incident** | 06, 07, 03 + the BQ matching the incident | Others |
| **New codebase onboarding** | 01, 02, 12 | 08, 11 |
| **AI/ML safety review** | 04, 05, 10, 13 | 11, 12 |
| **Full audit** | All 13 | None |

In triage mode, the Verification Pass still runs but only against the assessed BQs.

---

## Run Metrics

Track these for every FORGE run:

| Metric | Purpose |
|--------|---------|
| Total DQs evaluated | Coverage |
| PASS / GAP / ACCEPTED / BLOCKED / N/A counts | Distribution |
| Fixes proposed | Work output |
| Fixes implemented | Completion |
| KB entries generated | Learning |
| Elapsed time | Efficiency baseline |
| BQs completed vs. total | Completeness |

---

## Quickstart

1. **Identify the target** — what software are you analyzing?
2. **Choose mode** — full audit (all 13 BQs) or triage (select BQs from the guide)
3. **Gather access** — source code, infrastructure access, config files, documentation
4. **Run BQs in order** — for each DQ, record the answer and state
5. **Generate fixes** — for every GAP, write a Fix Specification
6. **Re-evaluate** — run DQs against proposed fixes, loop until stable
7. **Run Verification Pass** — check for conflicts, regressions, completeness
8. **Implement fixes** — apply changes to the target system
9. **Re-run affected BQs** — verify fixes resolved the gaps
10. **Update Knowledge Base** — record new patterns discovered

Output goes in `RESULTS-<project-name>.md` using the standard template (see `RESULTS-TEMPLATE.md`).

---

## BQ-01: PURPOSE & SCOPE

*What does this software do and what are its boundaries?*

### TQ-01.1: Core Function
- DQ: What is the single-sentence description of what this software does?
- DQ: Who are the intended users? (roles, skill levels, access patterns)
- DQ: What are the primary use cases? List each one.
- DQ: For each use case — what does "success" look like? What is the expected output?
- DQ: What is explicitly OUT of scope? What should this software NOT do?

### TQ-01.2: Requirements Traceability
- DQ: Is there a written specification, requirements doc, or design doc?
- DQ: For each stated requirement — is it implemented? Is it tested?
- DQ: Are there implemented features that have NO corresponding requirement? (scope creep)
- DQ: Are there requirements that conflict with each other?
- DQ: Who decides when requirements change? Is there a change control process?

### TQ-01.3: Assumptions & Constraints
- DQ: What assumptions does the software make about its environment? (OS, network, disk, memory)
- DQ: What assumptions does it make about its users? (trusted? authenticated? technical?)
- DQ: What assumptions does it make about its data? (clean? validated? well-formed?)
- DQ: Which of these assumptions are validated at runtime vs. taken on faith?
- DQ: What are the hard constraints? (budget, hardware, compliance, legacy compatibility)

---

## BQ-02: ARCHITECTURE & DEPENDENCIES

*How is it built and what does it depend on?*

### TQ-02.1: System Architecture
- DQ: What is the high-level architecture? (monolith, microservices, serverless, hybrid)
- DQ: Draw the component diagram — what talks to what?
- DQ: What are the communication patterns? (sync HTTP, async queues, events, shared DB)
- DQ: Where are the single points of failure?
- DQ: What happens if any single component goes down? (cascading failures?)

### TQ-02.2: Technology Stack
- DQ: What languages and versions are used? Are any end-of-life or unsupported?
- DQ: What frameworks are used? What versions? Are they actively maintained?
- DQ: What databases/datastores are used? What version? What configuration?
- DQ: What OS and runtime requirements exist?
- DQ: Are there any vendor-locked components? What's the exit strategy?

### TQ-02.3: Dependencies
- DQ: List all direct dependencies. For each: version, license, last update, known CVEs.
- DQ: List all transitive dependencies. Any with known vulnerabilities?
- DQ: Are dependencies pinned to exact versions or floating?
- DQ: Is there a dependency update process? How often are they reviewed?
- DQ: Are there any dependencies that are abandoned, archived, or single-maintainer?
- DQ: Could any dependency be removed entirely? (used for one function that could be inlined)
- DQ: Are there build/runtime files (docker-compose, .env, Makefile) that contain secrets? Are they gitignored? *(KB-003: video-pipeline 2026-03-21)*

### TQ-02.4: Build System
- DQ: What is the build process? Is it documented? Is it reproducible?
- DQ: Can you build from a clean checkout with one command?
- DQ: Are there build-time secrets or environment-specific config baked in?
- DQ: How long does a full build take? Is it parallelizable?
- DQ: Are build artifacts versioned and traceable to a specific commit?

---

## BQ-03: DATA FLOW & STORAGE

*Where does data come from, where does it go, and what happens to it in between?*

### TQ-03.1: Data Inputs
- DQ: What are ALL the input sources? (user input, APIs, files, databases, message queues, environment variables)
- DQ: For each input — what format is expected? What format could actually arrive?
- DQ: For each input — what happens if it's missing? Malformed? Enormous? Empty?
- DQ: Are inputs validated at the boundary before processing?
- DQ: Are inputs sanitized/escaped before use in queries, commands, or rendering?

### TQ-03.2: Data Processing
- DQ: What transformations happen to data between input and output?
- DQ: Are there any data transformations that are lossy? (truncation, rounding, encoding changes)
- DQ: Is processing idempotent? What happens if the same input is processed twice?
- DQ: Are there race conditions in data processing? (concurrent access, TOCTOU)
- DQ: What happens if processing is interrupted midway? (partial writes, corrupt state)

### TQ-03.3: Data Storage
- DQ: What data is persisted? Where? In what format?
- DQ: What is the data retention policy? Is old data ever cleaned up?
- DQ: Is stored data encrypted at rest?
- DQ: What are the backup procedures? How often? Tested restore?
- DQ: Is there data in multiple stores that must stay in sync? How is consistency maintained?
- DQ: What happens if storage is full? Read-only filesystem? Slow disk?

### TQ-03.4: Data Outputs
- DQ: What are ALL the output destinations? (UI, APIs, files, logs, emails, webhooks)
- DQ: Is sensitive data ever included in outputs that go to less-trusted destinations?
- DQ: Are outputs properly encoded for their destination? (HTML-escaped for web, parameterized for SQL)
- DQ: Can output volume overwhelm a downstream consumer?
- DQ: Are outputs validated before sending? (well-formed JSON, valid email, etc.)

---

## BQ-04: AUTHENTICATION & AUTHORIZATION

*Who and what can access it, and what can they do?*

### TQ-04.1: Authentication
- DQ: How do users prove they are who they claim to be? (passwords, tokens, SSO, certificates, none)
- DQ: How are credentials stored? (hashed? salted? what algorithm?)
- DQ: Is there multi-factor authentication? Is it optional or required?
- DQ: How are sessions managed? (tokens, cookies, server-side sessions)
- DQ: What is the session lifetime? Is there idle timeout? Absolute timeout?
- DQ: How does logout work? Are tokens/sessions actually invalidated?
- DQ: Is there account lockout after failed attempts? Is it bypassable?
- DQ: How does password/credential reset work? Is the reset flow itself secure?

### TQ-04.2: Authorization
- DQ: What is the permission model? (RBAC, ABAC, ACLs, none)
- DQ: List every role/permission level. What can each do?
- DQ: Is authorization checked on every request or only at login?
- DQ: Can a user escalate their own privileges? (parameter tampering, IDOR)
- DQ: Are there admin/superuser accounts? How are they protected?
- DQ: Is there separation of duties? (the person who deploys can't approve their own deploy)

### TQ-04.3: Service-to-Service Auth
- DQ: How do internal services authenticate to each other?
- DQ: Are service credentials rotatable without downtime?
- DQ: Is there network-level isolation between services? (zero trust vs. trusted network)
- DQ: Can an compromised internal service access other services' data?
- DQ: Are service-to-service calls authenticated AND authorized? (not just "is it internal")
- DQ: Is the Docker socket mounted to any container? RW or RO? What API calls does the service actually need? *(KB-007: EMBER 2026-03-21 — RW socket gave root-equivalent host access)*

### TQ-04.4: API Security
- DQ: Are all API endpoints authenticated? List any unauthenticated endpoints and justify each.
- DQ: Is there rate limiting? Per user? Per IP? Per endpoint?
- DQ: Are API keys/tokens scoped to minimum necessary permissions?
- DQ: Is there an API gateway or is each service handling its own auth?
- DQ: Are deprecated API versions still accessible? Are they still secure?

---

## BQ-05: INPUT VALIDATION & INJECTION DEFENSE

*How does the software handle untrusted input?*

### TQ-05.1: Injection Vectors
- DQ: Does the software construct SQL queries with user input? How? (parameterized? ORM? string concat?)
- DQ: Does it execute shell commands with user input? How is it escaped?
- DQ: Does it render user input in HTML/JavaScript? Is it escaped? (XSS)
- DQ: Does it process user-supplied file paths? Can path traversal occur? (../../etc/passwd)
- DQ: Does it deserialize user-supplied data? (pickle, YAML, XML — all dangerous)
- DQ: Does it process user-supplied XML? Is XXE disabled?
- DQ: Does it use user input in LDAP queries, regex, HTTP headers, or redirects?

### TQ-05.2: Validation Strategy
- DQ: Is validation allowlist-based (accept known good) or denylist-based (reject known bad)?
- DQ: Where does validation happen? Client-side only? Server-side? Both?
- DQ: Are file uploads validated? (type, size, content — not just extension)
- DQ: Are numeric inputs bounds-checked? (integer overflow, negative values)
- DQ: Are string inputs length-limited? (buffer overflow, storage exhaustion)
- DQ: Is there a central validation layer or is each endpoint rolling its own?

### TQ-05.3: Output Encoding
- DQ: Is output context-aware encoded? (HTML entities for HTML, URL encoding for URLs, etc.)
- DQ: Are Content-Type headers set correctly on all responses?
- DQ: Are security headers present? (CSP, X-Frame-Options, X-Content-Type-Options, HSTS)
- DQ: Is there protection against open redirects?
- DQ: Are error messages sanitized? (no stack traces, internal paths, or query text leaked to users)

---

## BQ-06: ERROR HANDLING & RESILIENCE

*What happens when things go wrong?*

### TQ-06.1: Error Handling
- DQ: Is there a consistent error handling pattern across the codebase?
- DQ: Are errors caught at appropriate levels? (not swallowed, not leaked to users)
- DQ: Do error responses reveal internal details? (stack traces, SQL queries, file paths)
- DQ: Are errors logged with enough context to diagnose? (request ID, user, timestamp, input)
- DQ: Are expected errors (validation, auth) handled differently from unexpected errors (crashes)?

### TQ-06.2: Failure Modes
- DQ: What happens if the database is unreachable? (crash? queue? degrade? retry?)
- DQ: What happens if an external API is down or slow?
- DQ: What happens if disk is full?
- DQ: What happens if memory is exhausted?
- DQ: What happens if the network is intermittent? (partial failures, split brain)
- DQ: Is there circuit breaker logic for external dependencies?
- DQ: Are retries implemented? With backoff? With jitter? With a max?

### TQ-06.3: Recovery
- DQ: After a crash, does the system recover to a consistent state automatically?
- DQ: Are there any operations that leave the system in an inconsistent state if interrupted?
- DQ: Is there a defined recovery procedure? Is it documented? Tested?
- DQ: How long does recovery take? Is there a Recovery Time Objective (RTO)?
- DQ: How much data can be lost? Is there a Recovery Point Objective (RPO)?

### TQ-06.4: Graceful Degradation
- DQ: Can the system operate with reduced functionality when dependencies are down?
- DQ: Are there fallback paths for critical operations?
- DQ: Does the system communicate its degraded state to users/operators?
- DQ: Are there timeouts on all external calls? Are they reasonable?

---

## BQ-07: OBSERVABILITY

*How do you know it's working, and how do you find out when it's not?*

### TQ-07.1: Logging
- DQ: What is logged? Is there a logging standard? (levels, format, fields)
- DQ: Are logs structured (JSON) or unstructured (free text)?
- DQ: Do logs include correlation/request IDs for tracing across services?
- DQ: Are sensitive data values excluded from logs? (passwords, tokens, PII)
- DQ: Where are logs stored? For how long? Are they searchable?
- DQ: Is log volume manageable? Could an attacker trigger log flooding?

### TQ-07.2: Monitoring & Alerting
- DQ: What metrics are collected? (request rate, error rate, latency, saturation)
- DQ: Are there health check endpoints? What do they actually verify?
- DQ: What conditions trigger alerts? Who receives them?
- DQ: Are there alerts for business-level anomalies? (not just infrastructure)
- DQ: Is there alert fatigue? Are alerts actionable or noisy?
- DQ: Would you know within 5 minutes if the system stopped working?

### TQ-07.3: Tracing & Debugging
- DQ: Can you trace a single request through all services it touches?
- DQ: Can you reproduce a production issue locally?
- DQ: Are there runbooks for common issues?
- DQ: Is there a way to enable debug logging in production without redeploying?

### TQ-07.4: Audit Trail
- DQ: Are security-relevant actions logged? (login, permission change, data access, admin actions)
- DQ: Are audit logs tamper-resistant? (append-only, separate storage)
- DQ: Can you answer "who did what, when, from where" for any action?
- DQ: Are audit logs retained long enough for compliance requirements?

---

## BQ-08: TESTING

*How do you know the software does what it should — and doesn't do what it shouldn't?*

### TQ-08.1: Test Coverage
- DQ: What percentage of code is covered by tests? What percentage of BEHAVIOR?
- DQ: Are there unit tests? What do they cover?
- DQ: Are there integration tests? Do they test real dependencies or mocks?
- DQ: Are there end-to-end tests? Do they cover critical user journeys?
- DQ: What is NOT tested? Why?

### TQ-08.2: Test Quality
- DQ: Do tests verify behavior or implementation? (will they break on refactor?)
- DQ: Are there tests for error/edge cases? (empty input, boundary values, concurrent access)
- DQ: Are there tests for security scenarios? (auth bypass, injection, privilege escalation)
- DQ: Do tests run in CI on every commit? Can they be skipped?
- DQ: How long does the test suite take? Are flaky tests tracked and addressed?

### TQ-08.3: Security Testing
- DQ: Has the software had a security audit or penetration test?
- DQ: Are there automated security scans? (SAST, DAST, dependency scanning)
- DQ: Is there fuzzing for input handling?
- DQ: Are security regression tests written for every vulnerability found?

### TQ-08.4: Data Testing
- DQ: Are tests run against realistic data? (volume, variety, edge cases)
- DQ: Are there data migration tests?
- DQ: Is test data isolated from production data?
- DQ: Are tests deterministic? (no dependence on external state, time, or ordering)

---

## BQ-09: DEPLOYMENT & OPERATIONS

*How does it get to production and how is it managed there?*

### TQ-09.1: Deployment Pipeline
- DQ: What is the deployment process? Is it automated? Documented?
- DQ: Can you deploy with one command? How long does it take?
- DQ: Is there a staging/pre-production environment? Does it match production?
- DQ: Are deployments atomic? (all-or-nothing, not partial)
- DQ: Can you roll back a bad deploy? How quickly? Has it been tested?

### TQ-09.2: Configuration Management
- DQ: How is configuration managed? (env vars, config files, secrets manager, hardcoded)
- DQ: Is configuration separated from code?
- DQ: Can configuration be changed without redeploying?
- DQ: Is there configuration drift between environments?
- DQ: Are configuration changes audited?

### TQ-09.3: Infrastructure
- DQ: Is infrastructure defined as code? (Terraform, CloudFormation, Docker Compose)
- DQ: Can the entire environment be recreated from scratch?
- DQ: Are there resource limits set? (CPU, memory, disk, connections)
- DQ: Is there auto-scaling? What triggers it? What are the limits?
- DQ: Is the infrastructure hardened? (unnecessary ports closed, services minimized)

### TQ-09.4: Operational Readiness
- DQ: Is there an on-call rotation? Escalation path?
- DQ: Are there runbooks for common operational tasks?
- DQ: Can you perform maintenance without downtime?
- DQ: Is there a disaster recovery plan? Has it been tested?
- DQ: What is the bus factor? (how many people can operate this system?)

---

## BQ-10: SECRETS & SENSITIVE DATA

*Where are the keys, and who's guarding them?*

### TQ-10.1: Credential Management
- DQ: List every secret the system uses. (DB passwords, API keys, signing keys, certificates)
- DQ: Where is each secret stored? (env var, config file, secrets manager, hardcoded, in VCS)
- DQ: Is each secret defined in exactly ONE place? Or duplicated across multiple files? *(KB-003: video-pipeline 2026-03-21 — same key was hardcoded in 3 files, fixed one, missed two)*
- DQ: Are any secrets committed to version control? (check git history, not just current)
- DQ: Can secrets be rotated without downtime?
- DQ: When were secrets last rotated?
- DQ: Are secrets scoped to minimum necessary? (one key per service, not shared)

### TQ-10.2: Data Classification
- DQ: What data qualifies as sensitive? (PII, financial, health, credentials)
- DQ: Is sensitive data identified and labeled in the schema/codebase?
- DQ: Is sensitive data encrypted at rest? With what? Who holds the keys?
- DQ: Is sensitive data encrypted in transit? (TLS everywhere? Internal too?)
- DQ: Is sensitive data masked in non-production environments?

### TQ-10.3: Data Exposure
- DQ: Can sensitive data appear in logs?
- DQ: Can sensitive data appear in error messages?
- DQ: Can sensitive data appear in URLs? (query parameters are logged by proxies/browsers)
- DQ: Can sensitive data be exported/downloaded by authorized users? Is it audited?
- DQ: Is sensitive data cached? Where? For how long? Can the cache be cleared?

### TQ-10.4: Compliance
- DQ: What regulations apply? (GDPR, HIPAA, SOC2, PCI-DSS, CCPA)
- DQ: Is there a data processing agreement with third parties?
- DQ: Can user data be exported on request? (data portability)
- DQ: Can user data be deleted on request? Completely? Including backups?
- DQ: Are data retention periods defined and enforced?

---

## BQ-11: PERFORMANCE & SCALABILITY

*Can it handle load, and what breaks first?*

### TQ-11.1: Current Performance
- DQ: What are the current response times? (p50, p95, p99)
- DQ: What is the current throughput? (requests/sec, events/sec)
- DQ: What are the resource utilization patterns? (CPU, memory, disk I/O, network)
- DQ: Are there known slow endpoints or operations?
- DQ: Are there N+1 queries, missing indexes, or expensive joins?
- DQ: Are batch operations bounded by time or count? What happens when input size doubles? *(KB-002: video-pipeline 2026-03-21 — approve-all with 705 files exceeded 60s subprocess timeout)*

### TQ-11.2: Scalability
- DQ: What is the bottleneck under load? (CPU, memory, DB connections, disk I/O, network)
- DQ: Can it scale horizontally? (add more instances)
- DQ: Can it scale vertically? (bigger machine) What are the limits?
- DQ: What shared state prevents horizontal scaling? (sessions, locks, local files)
- DQ: Is there a caching layer? What is cached? What is the invalidation strategy?

### TQ-11.3: Load Testing
- DQ: Has load testing been performed? Against realistic scenarios?
- DQ: What is the breaking point? What fails first?
- DQ: What happens at 2x, 5x, 10x expected load?
- DQ: Does the system degrade gracefully or fall off a cliff?

### TQ-11.4: Resource Management
- DQ: Are database connections pooled? What are the pool limits?
- DQ: Are HTTP connections reused or opened per request?
- DQ: Are there resource leaks? (connections, file handles, memory)
- DQ: Are there unbounded queues, caches, or buffers that could exhaust memory?
- DQ: Are there timeouts on all blocking operations?

---

## BQ-12: CODE QUALITY & MAINTAINABILITY

*Can someone else understand, modify, and extend this code?*

### TQ-12.1: Code Organization
- DQ: Is the codebase organized by feature, layer, or some other principle?
- DQ: Is the directory structure intuitive? Can a new developer find things?
- DQ: Are there clear boundaries between modules? (minimal coupling, high cohesion)
- DQ: Is there dead code? Unused imports? Unreachable paths?
- DQ: Are there TODO/FIXME/HACK comments? What do they say?

### TQ-12.2: Code Consistency
- DQ: Is there a style guide? Is it enforced? (linter, formatter)
- DQ: Are naming conventions consistent? (variables, functions, files, APIs)
- DQ: Are design patterns used consistently? (error handling, logging, config access)
- DQ: Is there a contribution guide for new developers?

### TQ-12.3: Documentation
- DQ: Is there architectural documentation? Is it current?
- DQ: Are APIs documented? (OpenAPI, JSDoc, docstrings — at the boundaries)
- DQ: Are complex algorithms or business logic explained?
- DQ: Are setup/install instructions accurate? Can a new developer get running from the README?

### TQ-12.4: Technical Debt
- DQ: What shortcuts were taken? Are they documented?
- DQ: What would the original developers do differently if starting over?
- DQ: Are there known anti-patterns in the codebase?
- DQ: Is there a plan to address tech debt? Is it prioritized?
- DQ: What parts of the code does everyone avoid touching? Why?

---

## BQ-13: AI/ML COMPONENTS

*If the software uses AI/ML models, LLM APIs, or autonomous agents — skip if not applicable.*

### TQ-13.1: Model Integration
- DQ: What AI/ML models or LLM APIs does the system use? List each with provider and model ID.
- DQ: What is each model used for? (classification, generation, routing, embedding, etc.)
- DQ: What happens if the model API is down, slow, or returns an error?
- DQ: What happens if the model returns nonsensical or hallucinated output?
- DQ: Is there a fallback when AI is unavailable? (rule-based, cached, graceful skip)
- DQ: Are model responses validated before acting on them? (format, schema, sanity checks)

### TQ-13.2: Prompt Security
- DQ: Can user-controlled input reach the model prompt? (prompt injection risk)
- DQ: Is there input sanitization before prompt construction?
- DQ: Can the model be tricked into executing unintended actions? (tool abuse, command injection via LLM)
- DQ: Are model outputs sanitized before use in SQL, shell commands, or HTML? (second-order injection)
- DQ: Are tool outputs passed through shell-interpreted constructs (heredocs, eval, template strings)? *(KB-004: EMBER 2026-03-21 — heredoc delimiter in write_file allowed shell injection)*
- DQ: Is the system prompt / SOUL / instructions protected from extraction?

### TQ-13.3: Cost & Token Management
- DQ: Is token usage tracked per request?
- DQ: Are there per-request or per-user cost limits?
- DQ: Could a malicious or accidental input cause runaway token consumption?
- DQ: Is there a maximum prompt/context size enforced?
- DQ: Are large inputs truncated or rejected before sending to the model?

### TQ-13.4: Agent Behavior (if autonomous agents)
- DQ: What actions can the agent take? What is the maximum blast radius of one action?
- DQ: Is there a human-in-the-loop for destructive or irreversible actions?
- DQ: Are agent actions logged with full context? (input, reasoning, action, result)
- DQ: Is the agent's temperature appropriate for its role? (low for routing/tool-calling, higher for creative tasks)
- DQ: Can the agent enter an infinite loop? Is there a max-iterations or max-actions limit?
- DQ: Are there competing skills/tools that could cause the agent to pick the wrong one?
- DQ: Does any automated process execute code generated by an LLM? What validation exists? *(KB-005: EMBER 2026-03-21 — proposal executor ran LLM-generated SQL directly)*
- DQ: After updating agent instructions, is conversation history cleared? (stale context overrides new prompts)

### TQ-13.5: Data Privacy with AI
- DQ: Is sensitive data (PII, credentials, internal paths) sent to external model APIs?
- DQ: Is there a sanitization layer between internal data and the model?
- DQ: Are model API calls logged? Do the logs contain sensitive prompt content?
- DQ: Does the model provider retain or train on submitted data? (check ToS/DPA)

---

# SECTION V: VERIFICATION PASS

*Run AFTER all BQs are exhausted and all fixes are designed.*

## VP-01: Fix Conflict Check
- Do any proposed fixes contradict each other?
- Do any fixes remove functionality that another fix depends on?
- Is the implementation order clear? (dependencies between fixes)
- Are there fixes that must be deployed atomically (all-or-nothing)?

## VP-02: Regression Risk
- For each fix — what could it break?
- Does each fix have a rollback plan?
- Are there tests that verify the fix works AND doesn't break existing behavior?
- Have similar fixes caused issues in previous projects? (Knowledge Base check)

## VP-03: Security Review of Fixes
- Do any fixes introduce new attack surface?
- Do any fixes weaken existing security controls?
- Do any fixes change trust boundaries?
- Do any fixes add new dependencies with their own vulnerabilities?
- Do any fixes expose new data to less-trusted contexts?

## VP-04: Completeness Check
- Was every BQ addressed? (not skipped, not "N/A" without justification)
- Were all DQ loops run to exhaustion? (no open threads)
- Are all identified gaps either fixed or explicitly accepted with documented risk?
- Is the final fix set achievable within the project constraints?

## VP-05: Acceptance Criteria
- For each fix — what does "done" look like?
- How will each fix be verified? (automated test, manual check, metric threshold)
- Who signs off on each fix?
- What is the success criteria for the overall improvement effort?

---

# SECTION KB: KNOWLEDGE BASE

*Patterns learned from running this framework across projects. This section grows over time.*

## KB Structure

Each learned pattern contains:
- **Pattern ID**: Unique identifier
- **Category**: Which BQ/TQ it relates to
- **Trigger**: What condition suggests this pattern applies
- **Pattern**: What the common gap or issue is
- **Impact**: What happens if it's not addressed
- **Source**: Which project(s) revealed this pattern
- **Added to Framework**: Whether this created a new DQ (and which one)

## KB-001: Hardcoded Secrets in Multi-File Projects
- **Category**: BQ-10 / TQ-10.1
- **Trigger**: Project with multiple source files that share configuration (API keys, URLs, credentials)
- **Pattern**: Same secret hardcoded in multiple files. Fix one, miss the others.
- **Impact**: Keys remain in source code, visible in VCS, can't rotate without editing N files
- **Source**: Video pipeline (2026-03-21) — Radarr/Sonarr API keys in staging_api.py, controller.py, AND tracker.py
- **Added to Framework**: Yes — added DQ to TQ-10.1: "Is each secret defined in exactly ONE place?"

## KB-002: Batch Operations Hit Timeout Cliffs
- **Category**: BQ-11 / TQ-11.1
- **Trigger**: Batch endpoint that spawns a subprocess or external call per item
- **Pattern**: O(n) operations with a fixed timeout. Works fine at n=50, fails silently at n=500.
- **Impact**: Operations hang or timeout, data gets stuck in intermediate state
- **Source**: Video pipeline (2026-03-21) — approve-all ran ffprobe per file, 705 files exceeded 60s timeout
- **Added to Framework**: Yes — added DQ to TQ-11.1: "Are batch operations bounded by time or count?"

## KB-003: Build Files as Secret Stores
- **Category**: BQ-02 / TQ-02.3, BQ-10 / TQ-10.1
- **Trigger**: Docker-based project with docker-compose.yml, Makefile, or CI config
- **Pattern**: Secrets stored in build/deploy files that are committed to VCS or readable by all users
- **Impact**: API keys, tokens, and passwords exposed in plain text in shared files
- **Source**: Video pipeline (2026-03-21) — Anthropic API key in docker-compose.yml
- **Added to Framework**: Yes — added DQ to TQ-02.3: "Are there build/runtime files that contain secrets?"

## KB-004: Heredoc Injection via LLM Output
- **Category**: BQ-05 / TQ-05.1, BQ-13 / TQ-13.2
- **Trigger**: LLM tool writes file content via shell heredoc or template string
- **Pattern**: Fixed delimiter in shell command allows LLM output to break the boundary and inject shell commands
- **Impact**: Remote code execution on host via prompt injection → tool call → heredoc break
- **Source**: EMBER write_file tool (2026-03-21)
- **Added to Framework**: Yes — added DQ to TQ-13.2

## KB-005: LLM-Generated SQL Execution
- **Category**: BQ-05 / TQ-05.1, BQ-13 / TQ-13.4
- **Trigger**: Self-improvement or automation system that generates code from LLM output
- **Pattern**: LLM output used as executable code (SQL, shell) without validation
- **Impact**: Database destruction or data exfiltration via prompt injection chain
- **Source**: EMBER proposal executor (2026-03-21)
- **Added to Framework**: Yes — added DQ to TQ-13.4

## KB-006: Temperature 1.0 for Tool-Calling
- **Category**: BQ-13 / TQ-13.4
- **Trigger**: LLM provider used for tool-calling or routing decisions
- **Pattern**: Default temperature (1.0) used for deterministic operations
- **Impact**: Unpredictable tool selection, wrong arguments, inconsistent behavior
- **Source**: EMBER cloud providers (2026-03-21)
- **Added to Framework**: No — existing DQ covers this

## KB-007: Docker Socket Mount as Lateral Movement
- **Category**: BQ-04 / TQ-04.3
- **Trigger**: Docker-based service that needs container management capabilities
- **Pattern**: Docker socket mounted RW gives root-equivalent host access to any container
- **Impact**: Compromised container → full host control → all other containers
- **Source**: EMBER backend (2026-03-21)
- **Added to Framework**: Yes — added DQ to TQ-04.3

## KB-008: System Prompt as Attack Surface
- **Category**: BQ-13 / TQ-13.2
- **Trigger**: LLM system prompt contains infrastructure details (paths, IPs, tool definitions)
- **Pattern**: System prompt extractable via social engineering or prompt injection
- **Impact**: Attacker learns infrastructure layout, available tools, and security boundaries
- **Source**: EMBER chat system (2026-03-21)
- **Added to Framework**: No — existing DQ covers this

## KB-TEMPLATE:
- **Category**: BQ-XX / TQ-XX.X
- **Trigger**: "When the project uses ___ and ___"
- **Pattern**: "The common gap is ___"
- **Impact**: "If unaddressed, ___ happens"
- **Source**: First observed in project ___
- **Added to Framework**: Yes/No — added DQ to TQ-XX.X

---

# Process Summary

```
FOR EACH BQ (01 through 13):
    FOR EACH TQ under this BQ:
        FOR EACH DQ under this TQ:
            Ask the question
            Record the answer
            IF answer reveals a gap:
                Generate Fix Specification
                Record fix
            END IF
        END FOR

        Re-evaluate: Do proposed fixes create new gaps?
        IF yes: Generate new DQs, loop
        UNTIL stable
    END FOR
END FOR

RUN Verification Pass (VP-01 through VP-05)
IF verification reveals issues:
    Generate additional fixes
    Re-run affected BQs
    Re-run Verification Pass
UNTIL clean

OUTPUT: Complete Fix Set + Verification Report

UPDATE Knowledge Base with new patterns discovered
```
