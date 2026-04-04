# FORGE Run: conduit-review — Results

**Date:** 2026-03-26
**Discipline:** Code Review v1.0.0
**Mode:** full (BQs: BQ-01, BQ-02, BQ-03, BQ-04, BQ-05, BQ-06)
**Version:** FORGE v2.1.0

## Run Metrics

| Metric | Value |
|--------|-------|
| Discipline | Code Review |
| Total DQs evaluated | 73 / 73 |
| ACCEPTED | 0 |
| BLOCKED | 0 |
| GAP | 14 |
| IMPROVE | 20 |
| N/A | 18 |
| PASS | 21 |
| Improvements | 20 |
| Fixes applied | 0 |
| KB entries | 0 |
| Elapsed | 0h 4m |

## Gap Summary

| ID | BQ | Description | Severity | Fix |
|----|-----|-------------|----------|-----|
| G-001 | BQ-01 | chat.py POST /api/chat invokes skill action with zero params regardless of action signature, causing runtime TypeError for nearly all parameterized actions. The 0.3 confidence threshold is also dangerously low. | high | Implement parameter extraction from natural langua |
| G-002 | BQ-01 | templates/loader.py does not validate step-type-specific required fields (e.g. skill_action requires skill_category+action, ai_generate requires prompt_template). Malformed templates fail at execution time, not at load time. | medium | Add per-step-type field validation in load_templat |
| G-003 | BQ-01 | SkillRegistry._instances dict has no concurrency protection — concurrent first-requests for the same skill can race during instantiate(), creating duplicate instances and leaking httpx clients. | medium | Use asyncio.Lock per (tenant_id, skill_id) key dur |
| G-004 | BQ-01 | projects.py execute_project has a TOCTOU race: status check and status update are not atomic. Two concurrent calls can both read 'intake' status and both execute the template, causing duplicate outputs. | medium | Use SELECT FOR UPDATE on the project row, or updat |
| G-005 | BQ-02 | POST /api/skills/invoke/{skill_id}/{action} endpoint accepts params from request body and invokes any skill action for any authenticated user. No role check — a viewer could invoke destructive actions like disable_user or initiate_restore. | high | Add @require_role('lead_tech') or equivalent permi |
| G-006 | BQ-02 | config.py jwt_secret defaults to a known string. No startup validation that secrets have been changed from defaults. A misconfigured deployment is silently vulnerable. | high | Add a startup check that raises if jwt_secret is t |
| G-007 | BQ-02 | create_project and execute_project use body.template_id / project.template_id directly in path construction (settings.templates_path / body.template_id). No sanitization prevents path traversal (e.g. '../../../etc/passwd'). | critical | Validate template_id against a whitelist of discov |
| G-008 | BQ-02 | projects.py execute_project re-raises raw exception messages to the HTTP client via HTTPException(500, detail=str(e)). Internal errors, SQLAlchemy messages, or skill error bodies may expose sensitive data. | medium | Log the full exception server-side, but return a g |
| G-009 | BQ-03 | main.py lifespan only calls engine.dispose() but never registry.close_all(). All skill httpx.AsyncClient instances leak on shutdown. | medium | Call registry.close_all() in the lifespan shutdown |
| G-010 | BQ-03 | Templates are loaded from disk on every create_project and execute_project call with no caching. Under load, this becomes redundant file I/O. | low | Cache loaded templates in memory (e.g. a module-le |
| G-011 | BQ-04 | No security scenario tests: path traversal via template_id in create_project, role enforcement on /api/skills/invoke, behavior with expired JWT tokens at API layer. | high | Add test_security.py covering: template_id='../etc |
| G-012 | BQ-04 | No tests for: chat endpoint (the primary user-facing feature), project GET/list endpoints, execute_project returning 400 when project status is 'running', or template step failure scenarios. | medium | Add tests for chat.py (routing + execution result) |
| G-013 | BQ-05 | No feature flags or dry-run mode. Chat endpoint executes destructive skill actions (disable_user, initiate_restore) based on keyword matching with 0.3 confidence threshold. No way to preview actions before execution. | high | Add a 'dry_run' flag to the chat endpoint, and/or  |
| G-014 | BQ-06 | No developer documentation: no README explaining how to install/run, no skill authoring guide documenting the skill.yaml schema, no API reference. | medium | Add README.md with setup instructions, and a SKILL |
| G-015 | BQ-06 | No operational documentation: no deployment guide, no environment variable reference, no runbook for common operations tasks. | low | Add docs/deployment.md and docs/runbook.md coverin |

## Improvement Opportunities

| ID | BQ | Description | Suggestion |
|----|-----|-------------|------------|
| I-001 | BQ-01 | Are there off-by-one errors, wrong compa | In registry.py get_skill_for_action(), it returns  |
| I-002 | BQ-01 | Are error cases handled? What happens on | Template engine catches exceptions per step with o |
| I-003 | BQ-01 | What happens with empty input? Null? Zer | Empty skills dir returns [] correctly. Empty templ |
| I-004 | BQ-02 | Does this change add new input handling? | New input handling in intake validation is thoroug |
| I-005 | BQ-02 | Does this change add new API endpoints?  | All API endpoints require authentication via get_c |
| I-006 | BQ-02 | Does this change log anything that could | Errors from skill invocations are included verbati |
| I-007 | BQ-03 | Does this change add loops or recursion? | AIRouter._match_actions is O(signals * actions * p |
| I-008 | BQ-03 | Does this change add database queries? A | SkillRegistry.health_check_all loops over all inst |
| I-009 | BQ-03 | Does this change increase memory usage?  | ContextStore.get_ai_context makes 2 DB queries (ge |
| I-010 | BQ-03 | Does this change add to a hot path? (cal | get_registry() in skills.py uses a module-level gl |
| I-011 | BQ-04 | Are there tests for error cases and edge | Error cases have partial coverage: invalid token,  |
| I-012 | BQ-04 | Could the tests fail with a correct impl | Test for router's ai_fallback_not_called_on_high_c |
| I-013 | BQ-04 | What edge cases are NOT tested? Should t | Edge cases not tested: empty chat message, very lo |
| I-014 | BQ-04 | Would this change benefit from an integr | Integration tests (e.g. full create+execute projec |
| I-015 | BQ-05 | Is the API versioned? Should this be a n | API is not versioned (no /v1/ prefix). Given this  |
| I-016 | BQ-05 | Does this change modify database schema? | No migration system present (no Alembic setup). Sc |
| I-017 | BQ-05 | Does this change modify default values,  | jwt_expire_minutes defaults to 480 (8 hours). This |
| I-018 | BQ-06 | Are complex algorithms or business rules | The AIRouter confidence scoring formula (category_ |
| I-019 | BQ-06 | Is there dead code, commented-out code,  | Several TODO/MVP placeholders: _execute_approval_g |
| I-020 | BQ-06 | Are there architectural decisions in thi | The architectural choice to use YAML-defined skill |

## Verification Pass

### VP-01: Fix Conflict Check — PASS
- [x] no_contradictions
- [x] order_clear

### VP-02: Regression Risk — FAIL
- [x] fixes_reference_gaps
- [x] fix_gap_refs_valid
- [ ] kb_checked

### VP-03: Security Review of Fixes — PASS
- [x] no_suspicious_fix_patterns
- [x] no_new_dependencies_added

### VP-04: Completeness Check — FAIL
- [x] all_bqs_addressed
- [x] all_dqs_answered
- [x] no_unresolved_blocked
- [ ] all_gaps_resolved

### VP-05: Acceptance Criteria — FAIL
- [ ] fixes_have_done_criteria

**Overall: FAIL**
