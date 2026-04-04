#!/usr/bin/env python3
"""Script to fill in all DQ answers for the conduit-review FORGE assessment."""

import sys
sys.path.insert(0, "C:/Users/larro/forge")

from engine import ForgeEngine

STATE_FILE = "C:/Users/larro/forge/forge-state-conduit-review.json"

engine = ForgeEngine.load(STATE_FILE)

# ─── BQ-01: Correctness ───────────────────────────────────────────────────────

# TQ-01.1 Intent
engine.answer("BQ-01", "TQ-01.1", 0, "PASS",
    "Codebase is an AI-powered MSP operations platform with skills, templates, routing, auth, and project execution. Purpose is well-documented in module docstrings.")
engine.answer("BQ-01", "TQ-01.1", 1, "PASS",
    "Every file contributes to the platform. Skills/, templates/, auth/, api/, router/, context/ are all coherent. No scope creep.")
engine.answer("BQ-01", "TQ-01.1", 2, "N/A",
    "No unrelated changes detected.")

# TQ-01.2 Logic
engine.answer("BQ-01", "TQ-01.2", 0, "PASS",
    "Core logic is sound: SkillRegistry discovers/instantiates skills, TemplateEngine executes steps sequentially, auth uses JWT+bcrypt, RBAC uses numeric hierarchy.")
engine.answer("BQ-01", "TQ-01.2", 1, "IMPROVE",
    "In registry.py get_skill_for_action(), it returns the *first* matching skill without deterministic ordering — if two skills share a category+action, the returned skill depends on dict iteration order. Should document or enforce selection priority.")
engine.answer("BQ-01", "TQ-01.2", 2, "GAP",
    "In chat.py the chat endpoint calls skill methods with no params (result = await method()) when confidence >= 0.3. The comment says 'real impl would extract params' — this means every confident skill invocation will fail at runtime since most methods require parameters (e.g. get_ticket requires ticket_id).")
engine.add_gap("BQ-01", "TQ-01.2",
    "chat.py POST /api/chat invokes skill action with zero params regardless of action signature, causing runtime TypeError for nearly all parameterized actions. The 0.3 confidence threshold is also dangerously low.",
    severity="high",
    fix="Implement parameter extraction from natural language before invoking skill, or raise the confidence threshold and return a clarification request when params are missing.")
engine.answer("BQ-01", "TQ-01.2", 3, "IMPROVE",
    "Template engine catches exceptions per step with on_error=stop/continue, but doesn't persist partial step_results to DB during execution — a crash mid-run means project stays in 'running' status and step_results are lost. The execute_project endpoint also has project.status='running' never explicitly set before engine.execute() runs.")
engine.answer("BQ-01", "TQ-01.2", 4, "GAP",
    "In template loader, steps are only validated to have 'id' and 'type' — skill_action steps are not validated to have 'skill_category' and 'action' at load time. A template with a missing field would fail only at execution time with an unhelpful KeyError.")
engine.add_gap("BQ-01", "TQ-01.2",
    "templates/loader.py does not validate step-type-specific required fields (e.g. skill_action requires skill_category+action, ai_generate requires prompt_template). Malformed templates fail at execution time, not at load time.",
    severity="medium",
    fix="Add per-step-type field validation in load_template() for each known step type.")

# TQ-01.3 Edge Cases
engine.answer("BQ-01", "TQ-01.3", 0, "IMPROVE",
    "Empty skills dir returns [] correctly. Empty template steps returns completed with no results. None values in resolve() are left as-is. However, validate_answer() casts string '.' containing floats with 'not in value' logic — int('3.14') path splits on '.' check, which works but is fragile.")
engine.answer("BQ-01", "TQ-01.3", 1, "GAP",
    "SkillRegistry._instances is a plain dict shared across all requests. Multiple concurrent requests for the same (tenant, skill) instantiation (e.g. first request after startup) can race: both miss the cache check and create two instances. The second overwrites the first's httpx client without closing it, leaking connections.")
engine.add_gap("BQ-01", "TQ-01.3",
    "SkillRegistry._instances dict has no concurrency protection — concurrent first-requests for the same skill can race during instantiate(), creating duplicate instances and leaking httpx clients.",
    severity="medium",
    fix="Use asyncio.Lock per (tenant_id, skill_id) key during instantiation, or pre-instantiate skills at startup.")
engine.answer("BQ-01", "TQ-01.3", 2, "GAP",
    "execute_project() in projects.py does not guard against concurrent execution of the same project. Two simultaneous POST /{project_id}/execute calls would both pass the status check ('intake' or 'paused') and run the template twice, potentially duplicating ProjectOutput rows.")
engine.add_gap("BQ-01", "TQ-01.3",
    "projects.py execute_project has a TOCTOU race: status check and status update are not atomic. Two concurrent calls can both read 'intake' status and both execute the template, causing duplicate outputs.",
    severity="medium",
    fix="Use SELECT FOR UPDATE on the project row, or update status to 'running' in a single atomic UPDATE...WHERE status IN ('intake','paused') and check affected rows.")
engine.answer("BQ-01", "TQ-01.3", 3, "PASS",
    "No significant TOCTOU issues beyond the project execution race noted above. JWT decode includes expiry check. Rate limit check uses current time.")

# ─── BQ-02: Security Impact ───────────────────────────────────────────────────

# TQ-02.1 Attack Surface
engine.answer("BQ-02", "TQ-02.1", 0, "IMPROVE",
    "New input handling in intake validation is thorough for question types. However, chat endpoint accepts free-form 'message' string with no length limit — could be used for prompt injection to the AI router or overflow log storage.")
engine.answer("BQ-02", "TQ-02.1", 1, "IMPROVE",
    "All API endpoints require authentication via get_current_user dependency. However, the POST /api/skills/invoke/{skill_id}/{action} endpoint only requires any authenticated user — it should require admin or lead_tech role since it directly invokes arbitrary skill actions.")
engine.add_gap("BQ-02", "TQ-02.1",
    "POST /api/skills/invoke/{skill_id}/{action} endpoint accepts params from request body and invokes any skill action for any authenticated user. No role check — a viewer could invoke destructive actions like disable_user or initiate_restore.",
    severity="high",
    fix="Add @require_role('lead_tech') or equivalent permission check to the invoke endpoint.")
engine.answer("BQ-02", "TQ-02.1", 2, "PASS",
    "Auth logic is standard: bcrypt for passwords, HS256 JWT, HTTPBearer extraction, expiry validation. No obvious bypass paths.")
engine.answer("BQ-02", "TQ-02.1", 3, "GAP",
    "config.py has plaintext default values for jwt_secret ('change-this-to-a-random-secret') and database_url with password ('changeme'). No validation that these have been changed from defaults — a production deployment with defaults is silently insecure.")
engine.add_gap("BQ-02", "TQ-02.1",
    "config.py jwt_secret defaults to a known string. No startup validation that secrets have been changed from defaults. A misconfigured deployment is silently vulnerable.",
    severity="high",
    fix="Add a startup check that raises if jwt_secret is the default value, or use a required field with no default (Pydantic will refuse to start if not set via env).")

# TQ-02.2 Injection & Encoding
engine.answer("BQ-02", "TQ-02.2", 0, "PASS",
    "All database queries use SQLAlchemy ORM with parameterized queries. No raw SQL string concatenation found.")
engine.answer("BQ-02", "TQ-02.2", 1, "PASS",
    "No shell command execution found in the codebase.")
engine.answer("BQ-02", "TQ-02.2", 2, "N/A",
    "No HTML rendering of user input — API returns JSON only.")
engine.answer("BQ-02", "TQ-02.2", 3, "GAP",
    "projects.py create_project uses settings.templates_path / body.template_id to construct the template directory path without sanitizing template_id. An attacker could pass '../../../etc' as template_id to achieve path traversal.")
engine.add_gap("BQ-02", "TQ-02.2",
    "create_project and execute_project use body.template_id / project.template_id directly in path construction (settings.templates_path / body.template_id). No sanitization prevents path traversal (e.g. '../../../etc/passwd').",
    severity="critical",
    fix="Validate template_id against a whitelist of discovered templates (e.g. check against keys returned by discover_templates), or strip/reject any id containing path separators or '..'.")
engine.answer("BQ-02", "TQ-02.2", 4, "N/A",
    "No redirect handling in this codebase.")

# TQ-02.3 Data Exposure
engine.answer("BQ-02", "TQ-02.3", 0, "IMPROVE",
    "Errors from skill invocations are included verbatim in API responses and logs (e.g. SkillAuthError body includes raw API error text). Vendor error messages sometimes contain partial credentials or internal IPs.")
engine.answer("BQ-02", "TQ-02.3", 1, "GAP",
    "execute_project catches all exceptions and re-raises as HTTPException(500, detail=str(e)). The exception string may contain internal details (stack traces from SQLAlchemy, etc.) that would be visible to the client.")
engine.add_gap("BQ-02", "TQ-02.3",
    "projects.py execute_project re-raises raw exception messages to the HTTP client via HTTPException(500, detail=str(e)). Internal errors, SQLAlchemy messages, or skill error bodies may expose sensitive data.",
    severity="medium",
    fix="Log the full exception server-side, but return a generic error message to the client (e.g. 'Execution failed — see server logs').")
engine.answer("BQ-02", "TQ-02.3", 2, "N/A",
    "No new external service integrations beyond what skills define.")
engine.answer("BQ-02", "TQ-02.3", 3, "PASS",
    "Tenant isolation is enforced via tenant_id filter on all project/org queries. JWT encodes tenant_id and it is used consistently.")

# ─── BQ-03: Performance Impact ────────────────────────────────────────────────

# TQ-03.1 Complexity
engine.answer("BQ-03", "TQ-03.1", 0, "IMPROVE",
    "AIRouter._match_actions is O(signals * actions * phrases) = ~200 iterations per call — acceptable. resolve_deep is O(n) where n is the tree size. No unbounded recursion. However _flatten_context for deeply nested contexts may produce exponential entries due to the 'Also store without prefix' behavior overwriting earlier keys with the same leaf name.")
engine.answer("BQ-03", "TQ-03.1", 1, "IMPROVE",
    "SkillRegistry.health_check_all loops over all instances sequentially (not concurrently). With many tenants/skills this could be slow. Should use asyncio.gather.")
engine.answer("BQ-03", "TQ-03.1", 2, "PASS",
    "No unbatched network calls. Skills use httpx.AsyncClient. Template engine awaits steps sequentially by design.")
engine.answer("BQ-03", "TQ-03.1", 3, "IMPROVE",
    "ContextStore.get_ai_context makes 2 DB queries (get_full_context + Organization select) — reasonable but could be combined into a single join.")

# TQ-03.2 Resource Usage
engine.answer("BQ-03", "TQ-03.2", 0, "GAP",
    "BaseSkill creates one httpx.AsyncClient per skill instance but never closes it unless close() is called. SkillRegistry.close_all() exists but is never called from main.py lifespan. On server shutdown the clients leak.")
engine.add_gap("BQ-03", "TQ-03.2",
    "main.py lifespan only calls engine.dispose() but never registry.close_all(). All skill httpx.AsyncClient instances leak on shutdown.",
    severity="medium",
    fix="Call registry.close_all() in the lifespan shutdown section, or use a module-level registry accessible from lifespan.")
engine.answer("BQ-03", "TQ-03.2", 1, "IMPROVE",
    "get_registry() in skills.py uses a module-level global that is initialized lazily. Under concurrency, two requests could simultaneously find _registry is None and both call discover(), wasting work but not causing data corruption.")
engine.answer("BQ-03", "TQ-03.2", 2, "GAP",
    "No caching of template loading. Every create_project and execute_project call reads and parses the template YAML from disk. With many concurrent project operations this adds unnecessary I/O.")
engine.add_gap("BQ-03", "TQ-03.2",
    "Templates are loaded from disk on every create_project and execute_project call with no caching. Under load, this becomes redundant file I/O.",
    severity="low",
    fix="Cache loaded templates in memory (e.g. a module-level dict or LRU cache) keyed by template_id.")
engine.answer("BQ-03", "TQ-03.2", 3, "PASS",
    "Under 10x load, the bottleneck would be the external skill API calls, not the routing or template logic itself.")

# TQ-03.3 Database Impact
engine.answer("BQ-03", "TQ-03.3", 0, "PASS",
    "All queries use indexed tenant_id and id columns. No full table scans observed. SQLAlchemy ORM with async driver.")
engine.answer("BQ-03", "TQ-03.3", 1, "N/A",
    "No new indexes added in this codebase (models define indexes via index=True on mapped_column).")
engine.answer("BQ-03", "TQ-03.3", 2, "N/A",
    "No migrations present in this codebase snapshot — would need Alembic.")
engine.answer("BQ-03", "TQ-03.3", 3, "PASS",
    "Project model stores intake_answers and step_results as JSON columns — appropriate for flexible schema data. No excessive denormalization.")

# ─── BQ-04: Test Coverage ─────────────────────────────────────────────────────

# TQ-04.1 Test Presence
engine.answer("BQ-04", "TQ-04.1", 0, "PASS",
    "Test suite covers: auth (JWT, passwords, RBAC, API), skills (loader, registry, mock skill), templates (interpolation, intake, engine execution), context store, and AI router. 5 test files with good breadth.")
engine.answer("BQ-04", "TQ-04.1", 1, "PASS",
    "Happy paths are well covered: register+login, skill discovery+instantiate, template execution, context set/get, router keyword matching.")
engine.answer("BQ-04", "TQ-04.1", 2, "IMPROVE",
    "Error cases have partial coverage: invalid token, wrong password, unknown skill, missing yaml. But missing: rate limit behavior, skill unavailability during template execution, concurrent instantiation, partial template execution failure with on_error=continue.")
engine.answer("BQ-04", "TQ-04.1", 3, "GAP",
    "No security-focused tests: no test for path traversal via template_id, no test that /api/skills/invoke requires elevated role, no test that expired tokens are rejected at the API layer (only unit-level), no test for prompt injection via chat message.")
engine.add_gap("BQ-04", "TQ-04.1",
    "No security scenario tests: path traversal via template_id in create_project, role enforcement on /api/skills/invoke, behavior with expired JWT tokens at API layer.",
    severity="high",
    fix="Add test_security.py covering: template_id='../etc' returns 400/404, invoke endpoint returns 403 for TECH role, expired token returns 401.")

# TQ-04.2 Test Quality
engine.answer("BQ-04", "TQ-04.2", 0, "PASS",
    "Tests verify behavior (returned data, exception types) not implementation details. Test for list_organizations checks returned structure, not internal state.")
engine.answer("BQ-04", "TQ-04.2", 1, "PASS",
    "Assertions are specific enough — test_duplicate_hashes checks h1 != h2, test_list_organizations checks total==5 and data[0]['name'].")
engine.answer("BQ-04", "TQ-04.2", 2, "IMPROVE",
    "Test for router's ai_fallback_not_called_on_high_confidence depends on the keyword confidence calculation for 'search documentation for network stuff' being >= 0.5. This is fragile if scoring changes.")
engine.answer("BQ-04", "TQ-04.2", 3, "PASS",
    "Test names and fixture setup are clear. The conftest structure with seed_tenant/seed_admin/seed_tech is easy to follow.")

# TQ-04.3 Missing Tests
engine.answer("BQ-04", "TQ-04.3", 0, "GAP",
    "Not tested: (1) chat endpoint execution path, (2) project list/get endpoints, (3) concurrent skill instantiation, (4) template execution with skill that raises SkillError mid-run, (5) execute_project with already-running project (should return 400).")
engine.add_gap("BQ-04", "TQ-04.3",
    "No tests for: chat endpoint (the primary user-facing feature), project GET/list endpoints, execute_project returning 400 when project status is 'running', or template step failure scenarios.",
    severity="medium",
    fix="Add tests for chat.py (routing + execution result), and project API endpoints.")
engine.answer("BQ-04", "TQ-04.3", 1, "IMPROVE",
    "Edge cases not tested: empty chat message, very long message, template with zero steps, intake with all optional questions left empty.")
engine.answer("BQ-04", "TQ-04.3", 2, "N/A",
    "This is new functionality, not a bugfix — no regression test required.")
engine.answer("BQ-04", "TQ-04.3", 3, "IMPROVE",
    "Integration tests (e.g. full create+execute project flow via HTTP) are absent. The individual unit tests cover components but not the end-to-end flow.")

# ─── BQ-05: Backward Compatibility ───────────────────────────────────────────

# TQ-05.1 API Compatibility
engine.answer("BQ-05", "TQ-05.1", 0, "N/A",
    "This is a new codebase (v0.1.0) — no existing public API to break.")
engine.answer("BQ-05", "TQ-05.1", 1, "N/A",
    "New API, no backward compat concerns.")
engine.answer("BQ-05", "TQ-05.1", 2, "N/A",
    "No known consumers of this API yet.")
engine.answer("BQ-05", "TQ-05.1", 3, "IMPROVE",
    "API is not versioned (no /v1/ prefix). Given this is an early release, adding versioning now would prevent future compat issues as the API evolves.")

# TQ-05.2 Data Compatibility
engine.answer("BQ-05", "TQ-05.2", 0, "IMPROVE",
    "No migration system present (no Alembic setup). Schema changes would require manual migration. This should be established now before data accumulates.")
engine.answer("BQ-05", "TQ-05.2", 1, "N/A",
    "Initial schema — no old code to worry about.")
engine.answer("BQ-05", "TQ-05.2", 2, "N/A",
    "Initial schema — no existing data.")
engine.answer("BQ-05", "TQ-05.2", 3, "N/A",
    "No serialization format changes.")

# TQ-05.3 Behavioral Compatibility
engine.answer("BQ-05", "TQ-05.3", 0, "N/A",
    "Initial implementation — no existing behavior to break.")
engine.answer("BQ-05", "TQ-05.3", 1, "N/A",
    "No existing downstream systems.")
engine.answer("BQ-05", "TQ-05.3", 2, "IMPROVE",
    "jwt_expire_minutes defaults to 480 (8 hours). This is longer than typical (1 hour). No refresh token mechanism exists. Consider documenting the security trade-off.")
engine.answer("BQ-05", "TQ-05.3", 3, "GAP",
    "No feature flags. The chat endpoint directly executes skill actions at confidence >= 0.3. In production this could trigger unintended mutations. There is no way to run in 'read-only' or 'suggest-only' mode for new deployments.")
engine.add_gap("BQ-05", "TQ-05.3",
    "No feature flags or dry-run mode. Chat endpoint executes destructive skill actions (disable_user, initiate_restore) based on keyword matching with 0.3 confidence threshold. No way to preview actions before execution.",
    severity="high",
    fix="Add a 'dry_run' flag to the chat endpoint, and/or add a configuration setting to restrict chat-executed actions to read-only capabilities.")

# ─── BQ-06: Documentation & Clarity ──────────────────────────────────────────

# TQ-06.1 Code Clarity
engine.answer("BQ-06", "TQ-06.1", 0, "PASS",
    "Naming is clear and consistent throughout: skill_id, tenant_id, template_id, intake_answers, step_results. Category class names are descriptive (PSASkill, RMMSkill).")
engine.answer("BQ-06", "TQ-06.1", 1, "PASS",
    "Module docstrings explain purpose and architecture. Key design decisions (e.g. capabilities validation, category interface) are documented. Code is largely self-documenting.")
engine.answer("BQ-06", "TQ-06.1", 2, "IMPROVE",
    "The AIRouter confidence scoring formula (category_score + action_score) * 1.2 capped at 1.0 is not explained. The 0.3 threshold in chat.py and 0.5 threshold in route_with_ai are magic numbers with no comment explaining their derivation.")
engine.answer("BQ-06", "TQ-06.1", 3, "IMPROVE",
    "Several TODO/MVP placeholders: _execute_approval_gate auto-approves with 'MVP' comment, _execute_notification logs with 'not yet implemented', chat.py has 'real impl would extract params'. These need tracking issues to prevent them from becoming permanent.")

# TQ-06.2 Change Documentation
engine.answer("BQ-06", "TQ-06.2", 0, "N/A",
    "No PR/commit description available for review — this is an initial codebase assessment.")
engine.answer("BQ-06", "TQ-06.2", 1, "IMPROVE",
    "The architectural choice to use YAML-defined skills loaded dynamically (vs code-only) is significant and not documented outside of module docstrings. An ADR (Architecture Decision Record) would be valuable.")
engine.answer("BQ-06", "TQ-06.2", 2, "GAP",
    "No README, no API documentation, no developer onboarding guide. The skill.yaml schema is not documented — skill authors must infer the format from the validator code and example mock skill.")
engine.add_gap("BQ-06", "TQ-06.2",
    "No developer documentation: no README explaining how to install/run, no skill authoring guide documenting the skill.yaml schema, no API reference.",
    severity="medium",
    fix="Add README.md with setup instructions, and a SKILL_AUTHORING.md documenting the skill.yaml schema with examples.")
engine.answer("BQ-06", "TQ-06.2", 3, "GAP",
    "No operational runbook: no documentation on how to deploy, configure environment variables, set up the database, or troubleshoot skill connectivity issues.")
engine.add_gap("BQ-06", "TQ-06.2",
    "No operational documentation: no deployment guide, no environment variable reference, no runbook for common operations tasks.",
    severity="low",
    fix="Add docs/deployment.md and docs/runbook.md covering environment setup, database initialization, and skill troubleshooting.")

# TQ-06.3 Reviewability
engine.answer("BQ-06", "TQ-06.3", 0, "PASS",
    "Codebase is well-structured and appropriately sized for a single review. No single file is excessively long.")
engine.answer("BQ-06", "TQ-06.3", 1, "N/A",
    "Not a PR — initial codebase assessment.")
engine.answer("BQ-06", "TQ-06.3", 2, "PASS",
    "No unrelated changes mixed in. The codebase is coherent.")
engine.answer("BQ-06", "TQ-06.3", 3, "N/A",
    "Not a PR — no test plan expected.")

# ─── Save ─────────────────────────────────────────────────────────────────────
engine.save(STATE_FILE)
print("All DQs answered and saved.")
m = engine.metrics()
print(f"Progress: {m['dqs_answered']}/{m['total_dqs']} DQs answered")
print(f"States: {m['states']}")
print(f"Gaps: {len(engine.gaps)}")
print(f"Improvements: {len(engine.improvements)}")
