#!/usr/bin/env python3
"""FORGE assessment of the Chief of Staff (CoS) system.

Target: End-to-end CoS system built in session 2026-04-03
Components:
  - TrueNAS cron scripts: chief_of_staff_morning.py, chief_of_staff_evening.py, cos_task_checker.py
  - ops-monitor endpoints: /tasks/*, /vault/delete-file, /vault/daily-log, /vault/files
  - EMBER skills: remind-me, my-tasks, daily-summary
  - Windows Task Scheduler: sync_ember_vault.py (every 5 min)
  - PostgreSQL: cos_tasks table, vault_documents (daily-log source)

Disciplines: operations-review
Triage: BQ-02 (monitoring), BQ-03 (scheduled tasks), BQ-05 (config), BQ-09 (credentials), BQ-10 (resilience)
"""

import sys
sys.path.insert(0, "C:/dev/active/forge")
from engine import ForgeEngine

STATE_FILE = "C:/dev/active/forge/forge-state-cos-assessment.json"
engine = ForgeEngine.load(STATE_FILE)

# ─── BQ-02: Monitoring & Observability ────────────────────────────────────────

# TQ-02.1 Monitor Health
engine.answer("BQ-02", "TQ-02.1", 0, "GAP",
    "cos_task_checker.py runs every minute via cron but has no self-reporting. If it crashes or exits non-zero, the cron daemon logs it to syslog but there is no alert. Morning/evening scripts have no health reporting either.",
    evidence="/mnt/Main/scripts/cos_task_checker.py — no health endpoint or heartbeat")
engine.add_gap("BQ-02", "TQ-02.1",
    "CoS cron scripts (task_checker, morning, evening) run silently. Failures are logged to /mnt/Main/scripts/logs/ but no alert fires if a script fails. A broken task_checker could mean tasks fire hours late with no one noticing.",
    severity="high",
    fix="Add a dead-man's switch: cos_task_checker.py should POST a heartbeat to EMBER /heartbeat or ops-monitor on each successful run. Add a monitor that alerts if no heartbeat in >2 minutes.")

engine.answer("BQ-02", "TQ-02.1", 1, "GAP",
    "sync_ember_vault.py on Windows runs via Task Scheduler every 5 min. Last run status and exit code are in Task Scheduler history but there is no alert if it fails. Memory files could go stale in EMBER with no notification.",
    evidence="Task Scheduler task 'EmberVaultSync' — no failure notification configured")
engine.add_gap("BQ-02", "TQ-02.1",
    "sync_ember_vault.py failures are silent — Task Scheduler records exit code but no Discord alert fires. Changed memory files would not reach EMBER vault.",
    severity="medium",
    fix="Add --notify flag to sync_ember_vault.py that POSTs failure to Discord webhook. Configure Task Scheduler to run with --notify on failure, or add a wrapper that catches non-zero exit and sends alert.")

engine.answer("BQ-02", "TQ-02.1", 2, "PASS",
    "ops-monitor has /health endpoint with active healthcheck (curl -f http://localhost:5079/health). Docker restarts it on failure.",
    evidence="docker-compose.yml healthcheck + restart: unless-stopped")

engine.answer("BQ-02", "TQ-02.1", 3, "GAP",
    "No end-to-end smoke test for the CoS pipeline. We know EMBER is up and ops-monitor is up individually, but nothing tests: trigger phrase → skill match → http_request → ops-monitor → postgres write → task_checker → Discord. A break anywhere in this chain is invisible.",
    evidence="No integration test script exists for CoS flow")
engine.add_gap("BQ-02", "TQ-02.1",
    "No end-to-end health check for the CoS pipeline. Each component has its own health check but the full chain (NullClaw → EMBER skill → ops-monitor → postgres → Discord) is never tested as a unit.",
    severity="medium",
    fix="Add a daily smoke test (cron or heartbeat) that creates a test task via the ops-monitor API directly, verifies it appears in /tasks, then marks it done. Alert if any step fails.")

engine.answer("BQ-02", "TQ-02.1", 4, "PASS",
    "EMBER OpsAgent monitors the EMBER backend itself (provider health, DB, heartbeat) every ~25 min. It escalates to Discord after 3 consecutive failures.",
    evidence="/mnt/Main/appdata/ember/backend/heartbeat/ops_agent.py")

# TQ-02.2 Coverage Gaps
engine.answer("BQ-02", "TQ-02.2", 0, "GAP",
    "ops-monitor /tasks, /tasks/create, /vault/delete-file, /vault/daily-log endpoints have no per-endpoint metrics. No way to know if daily-summary skill calls are failing (e.g., EMBER vault ingest timing out) without reading logs.",
    evidence="ops-monitor agent.py — no request counters or error rate tracking")
engine.add_gap("BQ-02", "TQ-02.2",
    "CoS ops-monitor endpoints have no request metrics (call count, error rate, latency). A failing /vault/daily-log endpoint would only appear in container logs.",
    severity="low",
    fix="Add simple in-memory counters (success/error per endpoint) to a /cos/metrics endpoint on ops-monitor. Low effort, high diagnostic value.")

engine.answer("BQ-02", "TQ-02.2", 1, "GAP",
    "cos_tasks table has no monitoring. No alert if the table grows unexpectedly large, if completed tasks are never pruned, or if sent_at is NULL for tasks past due_at (missed fire).",
    evidence="cos_tasks schema — no monitoring query or alert")
engine.add_gap("BQ-02", "TQ-02.2",
    "cos_tasks table is unmonitored. Missed task fires (due_at past, status still 'pending', sent_at NULL) would be invisible. Table also grows without bound — no pruning.",
    severity="medium",
    fix="Add to cos_task_checker.py: (1) alert if any task is >15 min past due_at with status=pending; (2) DELETE completed/sent tasks older than 30 days on each run.")

engine.answer("BQ-02", "TQ-02.2", 2, "PASS",
    "Background cron logs go to /mnt/Main/scripts/logs/ with separate files per script. Log rotation is handled by ops-monitor's log retention loop.",
    evidence="crontab entries redirect stdout/stderr to cos_*.log files")

engine.answer("BQ-02", "TQ-02.2", 3, "PASS",
    "EMBER skill execution is logged in the backend with skill name, confidence, and execution ID. Failures surface in docker logs ember-backend.",
    evidence="backend/routers/chat.py logger_chat")

# TQ-02.3 Alert Quality
engine.answer("BQ-02", "TQ-02.3", 0, "IMPROVE",
    "Task reminders fire to Discord with priority icons (🔴🟠🟡🟢) and description. Good context. However, there's no 'snooze' or 'acknowledge' mechanism — if a task fires while you're away, it just sits in Discord with no way to defer it except marking it done.",
    evidence="cos_task_checker.py Discord embed format")

engine.answer("BQ-02", "TQ-02.3", 1, "PASS",
    "Morning briefing includes pending tasks and a EMBER vault context summary. Evening check-in includes pending task list. Alert content is meaningful.",
    evidence="chief_of_staff_morning.py + chief_of_staff_evening.py")

engine.answer("BQ-02", "TQ-02.3", 2, "GAP",
    "No deduplication on task reminders. If cos_task_checker fires and Discord POST fails (webhook down, rate limit), the task sent_at is never set, so it fires again next minute. Repeated failures create a task reminder storm.",
    evidence="cos_task_checker.py — UPDATE sent_at only runs after successful POST; no retry cap")
engine.add_gap("BQ-02", "TQ-02.3",
    "Task reminder has no retry cap. If Discord webhook is down, cos_task_checker will re-fire the same task every minute indefinitely. When Discord recovers, a flood of duplicate reminders arrives.",
    severity="medium",
    fix="Add a retry_count column to cos_tasks, or mark tasks as sent optimistically before posting, with a compensation step on failure. Cap retries at 3.")

engine.answer("BQ-02", "TQ-02.3", 3, "PASS",
    "Daily summary and morning briefing both go to Discord where they're persistent and reviewable. No silent drops on the EMBER side.",
    evidence="chief_of_staff_morning.py curl_post() behavior")

# ─── BQ-03: Scheduled Tasks & Automation ─────────────────────────────────────

# TQ-03.1 Task Inventory
engine.answer("BQ-03", "TQ-03.1", 0, "PASS",
    "CoS scheduled tasks: (1) 0 7 * * 1-5 morning briefing, (2) 0 17 * * 1-5 evening check-in, (3) * * * * * task checker — all on TrueNAS crontab. (4) EmberVaultSync on Windows Task Scheduler every 5 min. Total: 4 tasks.",
    evidence="TrueNAS crontab + Windows Task Scheduler")

engine.answer("BQ-03", "TQ-03.1", 1, "GAP",
    "Scheduled tasks are split across two systems: TrueNAS crontab (3 tasks) and Windows Task Scheduler (1 task). No single inventory. To audit all CoS tasks you must check both systems.",
    evidence="crontab -l on TrueNAS + Task Scheduler on Windows")
engine.add_gap("BQ-03", "TQ-03.1",
    "CoS scheduled task inventory is split: TrueNAS crontab + Windows Task Scheduler. No single source of truth. Easy to lose track of what's running where.",
    severity="low",
    fix="Document all CoS scheduled tasks in a single CLAUDE.md or project README section with name, schedule, host, log location, and failure behavior.")

engine.answer("BQ-03", "TQ-03.1", 2, "PASS",
    "No duplicate registrations found. Each task runs on exactly one host and appears once in the relevant scheduler.",
    evidence="Confirmed via crontab -l and Task Scheduler review")

engine.answer("BQ-03", "TQ-03.1", 3, "PASS",
    "All 4 tasks have run successfully since creation. No blocking conditions found.",
    evidence="Task Scheduler LastTaskResult=0, cron log files exist and are non-empty")

engine.answer("BQ-03", "TQ-03.1", 4, "N/A",
    "No disabled tasks to clean up — all registered tasks are active and intentional.")

# TQ-03.2 Task Health
engine.answer("BQ-03", "TQ-03.2", 0, "PASS",
    "No recent failures observed. Morning briefing, evening check-in, and task checker have all run successfully in the current session. sync_ember_vault.py exited 0.",
    evidence="Log files + Task Scheduler history")

engine.answer("BQ-03", "TQ-03.2", 1, "IMPROVE",
    "cos_task_checker.py runs every minute. When there are no pending tasks, it runs a DB query, gets 0 rows, and exits. This is efficient (fast psql exec). However, when tasks exist, it fires Discord and updates DB — all within the 1-minute window. Under normal load this is fine, but with many concurrent tasks it could lag.",
    evidence="cos_task_checker.py — no batching or rate limiting on Discord POSTs")

engine.answer("BQ-03", "TQ-03.2", 2, "GAP",
    "Task outcomes are logged to files but not to a queryable store. No way to ask 'how many tasks fired last week' or 'which tasks were missed'. The cos_tasks table tracks sent_at but no summary analytics.",
    evidence="cos_task_checker.py — no analytics logging beyond file output")
engine.add_gap("BQ-03", "TQ-03.2",
    "No analytics on CoS task execution. Cannot answer: how many tasks created/fired/missed this week, what are peak creation hours, what % of tasks are urgent vs. normal.",
    severity="low",
    fix="Add a cos_task_stats view or periodic summary to the morning briefing: 'This week: 12 tasks created, 11 fired, 0 missed.'")

engine.answer("BQ-03", "TQ-03.2", 3, "GAP",
    "sync_ember_vault.py has no timeout. If EMBER vault API is slow (large file, slow embedding), the script blocks. With a 5-min schedule and a blocking call, a slow run could cause overlap with the next scheduled run.",
    evidence="sync_ember_vault.py — urllib.request.urlopen(req, timeout=30) per file, no total run timeout")
engine.add_gap("BQ-03", "TQ-03.2",
    "sync_ember_vault.py has per-request timeout (30s) but no total run timeout. A single large file or slow EMBER response could cause the script to run >5 min, overlapping with the next Task Scheduler invocation.",
    severity="low",
    fix="Add a total run start time check and exit early if approaching 4 min: 'if time.time() - START > 240: print(\"timeout — resuming next run\"); sys.exit(0)'")

engine.answer("BQ-03", "TQ-03.2", 4, "PASS",
    "Morning/evening scripts have a fixed runtime (one EMBER query + one Discord POST). They cannot hang indefinitely — urllib has a 30s timeout.",
    evidence="chief_of_staff_morning.py timeout=30 on all curl calls")

# TQ-03.3 Scheduling Conflicts
engine.answer("BQ-03", "TQ-03.3", 0, "PASS",
    "No scheduling conflicts. Morning (7 AM) and evening (5 PM) scripts are 10 hours apart. Task checker (every min) is lightweight. sync_ember_vault (every 5 min Windows) is independent of TrueNAS tasks.",
    evidence="Cron schedules reviewed — no overlap")

engine.answer("BQ-03", "TQ-03.3", 1, "PASS",
    "All tasks are lightweight. The heaviest is cos_task_checker.py (docker exec psql + optional Discord POST), which completes in <2s. No contention risk.",
    evidence="Observed runtime from logs")

engine.answer("BQ-03", "TQ-03.3", 2, "GAP",
    "No single document lists all CoS scheduled tasks. To find them you must check TrueNAS crontab AND Windows Task Scheduler. No visual timeline.",
    evidence="Documentation gap — same as TQ-03.1.1")

engine.answer("BQ-03", "TQ-03.3", 3, "N/A",
    "Covered under task inventory gap above.")

# TQ-03.4 Automation Gaps
engine.answer("BQ-03", "TQ-03.4", 0, "GAP",
    "No 'task done' or 'task snooze' command in Discord. To mark a task complete the user must either know to say nothing (tasks auto-expire?) or use ops-monitor API directly. The my-tasks skill shows tasks but has no 'mark done' action.",
    evidence="skill DB — my-tasks skill has GET /tasks action only, no /tasks/<id>/done")
engine.add_gap("BQ-03", "TQ-03.4",
    "No natural language command to complete or snooze a task from Discord. User sees reminders but cannot dismiss them via chat. Tasks just sit as 'pending' until manually updated via API.",
    severity="high",
    fix="Add 'done with task X' / 'mark task X done' / 'task X complete' skill that calls POST /tasks/<id>/done. Use LLM to match description to pending task ID.")

engine.answer("BQ-03", "TQ-03.4", 1, "IMPROVE",
    "Vault auto-sync (sync_ember_vault.py) only syncs from Windows home machine. If you edit memory files on a different machine or directly on TrueNAS, those changes won't sync automatically.",
    evidence="MEMORY_DIR hardcoded to C:\\\\Users\\\\larro\\\\.claude\\\\projects\\\\...\\\\memory")

engine.answer("BQ-03", "TQ-03.4", 2, "GAP",
    "EMBER skill embeddings fail to refresh on startup (WARNING: Failed to refresh skill embeddings). This means new skills like daily-summary, my-tasks rely solely on text trigger matching, not semantic matching. A user saying 'log my day' won't match 'today i' via substring.",
    evidence="docker logs ember-backend — 'Failed to refresh skill embeddings: could not convert string to float'")
engine.add_gap("BQ-03", "TQ-03.4",
    "EMBER skill embedding refresh fails on startup with a float conversion error on stored embeddings. All skill routing falls back to text matching only. Semantic trigger matching is broken — users must use exact trigger phrases.",
    severity="high",
    fix="Investigate description_embedding column format. The error suggests stored embeddings are strings not vectors. Run: SELECT id, description_embedding FROM skills LIMIT 1 and check type. May need to re-generate embeddings after fixing storage format.")

engine.answer("BQ-03", "TQ-03.4", 3, "PASS",
    "Morning briefing automation fully replaces a manual 'what do I have today' workflow. Evening check-in and daily logging replace manual journaling. Task reminders replace mental overhead of tracking deadlines.",
    evidence="End-to-end CoS system tested and working")

# ─── BQ-05: Service Configuration ────────────────────────────────────────────

# TQ-05.1 Container Configuration
engine.answer("BQ-05", "TQ-05.1", 0, "PASS",
    "ops-monitor has restart: unless-stopped and healthcheck defined.",
    evidence="docker-compose.yml")

engine.answer("BQ-05", "TQ-05.1", 1, "PASS",
    "ops-monitor healthcheck: curl -f http://localhost:5079/health every 30s, 3 retries.",
    evidence="docker-compose.yml healthcheck block")

engine.answer("BQ-05", "TQ-05.1", 2, "PASS",
    "No port conflicts. ops-monitor on 5079, EMBER on 3000/8000, NullClaw on 5081. TZ=America/Chicago set in env.",
    evidence="docker-compose.yml environment section")

engine.answer("BQ-05", "TQ-05.1", 3, "PASS",
    "Volume mounts are correct: /data, /logs, /config, docker.sock, /mnt/Main.",
    evidence="docker-compose.yml volumes")

engine.answer("BQ-05", "TQ-05.1", 4, "GAP",
    "ops-monitor image uses build: . (local build) — no pinned base image version in Dockerfile. The FROM line likely uses a tag like python:3.11-slim which could pull a different patch version on rebuild.",
    evidence="ops-monitor Dockerfile (assumed — not verified against a specific FROM tag)")
engine.add_gap("BQ-05", "TQ-05.1",
    "ops-monitor Dockerfile likely uses an unpinned base image tag. Rebuilds could pull updated base images that introduce breaking changes.",
    severity="low",
    fix="Pin the base image to a specific digest: FROM python:3.11-slim@sha256:<digest>. Check current Dockerfile.")

# TQ-05.2 Configuration Drift
engine.answer("BQ-05", "TQ-05.2", 0, "GAP",
    "Several CoS endpoint additions to ops-monitor agent.py were made via direct file edits on TrueNAS, not through the container build process. The source-of-truth is the TrueNAS host file, but if the container is rebuilt from scratch from a git clone, the CoS endpoints would be missing.",
    evidence="/mnt/Main/inop/ops-monitor/agent.py modified directly — not committed to git")
engine.add_gap("BQ-05", "TQ-05.2",
    "ops-monitor agent.py was modified in-place on TrueNAS host. These changes are NOT in git. A fresh clone and rebuild would lose all CoS endpoints (/tasks/*, /vault/*, /cos/*).",
    severity="critical",
    fix="Commit /mnt/Main/inop/ops-monitor/agent.py to the ops-monitor git repo (or the TrueNAS config repo). This is the highest-priority fix from this assessment.")

engine.answer("BQ-05", "TQ-05.2", 1, "GAP",
    "CoS scripts (chief_of_staff_morning.py, chief_of_staff_evening.py, cos_task_checker.py, cos_add_task.py) are in /mnt/Main/scripts/ which is on the ZFS pool (backed up by daily snapshot) but NOT in git. A script edit could be undone by a snapshot restore with no history.",
    evidence="/mnt/Main/scripts/ — no .git directory")
engine.add_gap("BQ-05", "TQ-05.2",
    "CoS scripts in /mnt/Main/scripts/ are not version-controlled. Changes are not tracked, reviewable, or safely rollback-able.",
    severity="high",
    fix="Initialize a git repo at /mnt/Main/scripts/ or commit these files to an existing repo. At minimum: git init, git add cos_*.py chief_of_staff_*.py, commit.")

engine.answer("BQ-05", "TQ-05.2", 2, "GAP",
    "EMBER skill changes (remind-me actions, my-tasks, daily-summary) were made directly to the DB. The bundled_skills.py source was also updated but the DB is the live state. If the DB is restored from a snapshot, the skill changes are lost and need to be re-applied.",
    evidence="DB edits via docker exec psql not reflected in a migration file")
engine.add_gap("BQ-05", "TQ-05.2",
    "EMBER skill DB state and bundled_skills.py source can diverge. DB is the live state; source is only applied on first install. After a DB restore, CoS skills would need manual re-application.",
    severity="medium",
    fix="Create a cos_skills_migration.sql that recreates all CoS skill changes (remind-me updates, my-tasks, daily-summary inserts). Store in /mnt/Main/appdata/ember/migrations/.")

engine.answer("BQ-05", "TQ-05.2", 3, "PASS",
    "sync_ember_vault.py and seed_ember_vault.py are in C:/dev/active/msp-toolkit/ which is on the home machine. These are the canonical source.",
    evidence="C:/dev/active/msp-toolkit/*.py")

# TQ-05.3 Network Configuration
engine.answer("BQ-05", "TQ-05.3", 0, "GAP",
    "ops-monitor endpoints /tasks/create, /vault/delete-file, /vault/daily-log have NO authentication. Anyone on the 192.168.110.0/24 network can create tasks, delete vault documents, or inject daily logs. The EMBER skill uses these endpoints with no token.",
    evidence="agent.py task/vault endpoints — no auth check")
engine.add_gap("BQ-05", "TQ-05.3",
    "ops-monitor CoS endpoints are unauthenticated. Any device on the home LAN can create tasks, delete vault docs, or forge daily logs. No token validation, no IP allowlist, no rate limiting.",
    severity="high",
    fix="Add a simple shared secret: CoS endpoints check for X-CoS-Token header matching an env var COS_API_TOKEN. EMBER skills pass this header in http_request config headers field.")

engine.answer("BQ-05", "TQ-05.3", 1, "PASS",
    "ops-monitor is only on inop-network. Port 5079 is published to host for LAN access. Not exposed to WAN.",
    evidence="docker-compose.yml — no external exposure beyond host port")

engine.answer("BQ-05", "TQ-05.3", 2, "PASS",
    "No orphaned networks. ops-monitor is on inop-network (external: true) which is the correct shared network.",
    evidence="docker-compose.yml networks section")

# ─── BQ-09: Dependency & Provider Health ──────────────────────────────────────

# TQ-09.1 Provider Status
engine.answer("BQ-09", "TQ-09.1", 0, "PASS",
    "CoS external dependencies: (1) Anthropic API via EMBER — monitored by OpsAgent. (2) Discord webhook — not monitored. (3) PostgreSQL — monitored by EMBER. (4) ops-monitor — Docker healthcheck.",
    evidence="EMBER OpsAgent + docker-compose healthchecks")

engine.answer("BQ-09", "TQ-09.1", 1, "GAP",
    "Discord webhook is not health-checked. If the webhook URL rotates or Discord changes the format, all CoS notifications silently stop. The only detection is 'user notices no morning briefing'.",
    evidence="chief_of_staff_morning.py — no webhook validation or status check")
engine.add_gap("BQ-09", "TQ-09.1",
    "Discord webhook health is never checked. A broken webhook causes silent failure of morning briefing, evening check-in, and task reminders.",
    severity="medium",
    fix="Add a weekly webhook test: POST a silent test message (delete_after=0) and verify 204 response. Alert via EMBER chat if it fails.")

engine.answer("BQ-09", "TQ-09.1", 2, "IMPROVE",
    "EMBER is a critical dependency for all CoS skills. EMBER going down stops remind-me, my-tasks, and daily-summary. Morning/evening scripts also fail. However EMBER has its own health monitoring and auto-restart via Docker.",
    evidence="EMBER docker restart: unless-stopped + OpsAgent monitoring")

engine.answer("BQ-09", "TQ-09.1", 3, "GAP",
    "No degraded mode. If EMBER is down, morning briefing script fails with a curl error and exits. No fallback — the briefing is simply skipped with no notification to the user.",
    evidence="chief_of_staff_morning.py — no error handling beyond print statement")
engine.add_gap("BQ-09", "TQ-09.1",
    "If EMBER is unavailable, the morning briefing sends no Discord message and fails silently. User gets no notification that the briefing failed.",
    severity="medium",
    fix="In chief_of_staff_morning.py: if EMBER query fails, send a fallback Discord message: 'Morning check-in failed — EMBER may be down. Pending tasks: [query ops-monitor /tasks directly].'")

# TQ-09.2 Credential Lifecycle
engine.answer("BQ-09", "TQ-09.2", 0, "GAP",
    "VAULT_SESSION token 'seed-service-81e4a28b9ab3623e580f2881bd19ccaf' was manually inserted into the auth_sessions table with expiry 1 year from creation. No monitoring for expiry. When it expires, all vault writes from CoS skills will silently fail.",
    evidence="seed_ember_vault.py comment: 'Created via INSERT INTO auth_sessions... NOW() + INTERVAL 1 year'")
engine.add_gap("BQ-09", "TQ-09.2",
    "VAULT_SESSION token expires in ~1 year from creation (2026-04) with no expiry monitoring. All vault writes (daily logs, seed ingestion) will silently fail after expiry.",
    severity="high",
    fix="Add a weekly cron check: SELECT expires_at FROM auth_sessions WHERE session_token='seed-service-...'. Alert via Discord if expiry is <30 days away. Alternatively set expiry to 10 years.")

engine.answer("BQ-09", "TQ-09.2", 1, "GAP",
    "Credentials are hardcoded in script source files: EMBER_TOKEN in seed_ember_vault.py and sync_ember_vault.py, VAULT_SESSION in seed_ember_vault.py, sync_ember_vault.py, ops-monitor, and TrueNAS scripts. Discord webhook URL is hardcoded in chief_of_staff_morning.py, chief_of_staff_evening.py, and ops-monitor.",
    evidence="Multiple files contain hardcoded credentials — not reading from env vars consistently")
engine.add_gap("BQ-09", "TQ-09.2",
    "Credentials hardcoded in 6+ source files: EMBER_TOKEN, VAULT_SESSION, Discord webhook URL. Rotating any credential requires finding and updating all occurrences. Risk of accidental exposure if files are shared or committed.",
    severity="high",
    fix="Move all credentials to environment variables. Create a .env file for TrueNAS scripts (sourced by cron via BASH_ENV or wrapper). Use os.environ.get() with no hardcoded fallback for production-critical tokens.")

engine.answer("BQ-09", "TQ-09.2", 2, "PASS",
    "Credentials are not committed to any public git repo. They exist only in script files on TrueNAS (behind firewall) and Windows home machine (private).",
    evidence="No public git repo for these scripts")

engine.answer("BQ-09", "TQ-09.2", 3, "GAP",
    "No credential inventory. To know what credentials exist and when they expire, you must grep all scripts. No centralized record.",
    evidence="No CREDENTIALS.md or secrets manager")
engine.add_gap("BQ-09", "TQ-09.2",
    "No credential inventory for the CoS system. 4+ credentials with no expiry tracking, no rotation schedule, and no central record.",
    severity="medium",
    fix="Create a CREDENTIALS.md (not committed) or EMBER vault entry listing: credential name, where used, expiry date, rotation procedure.")

# TQ-09.3 Vendor Lock-in
engine.answer("BQ-09", "TQ-09.3", 0, "IMPROVE",
    "Discord is the notification channel. Switching to Slack, Telegram, or SMS would require updating 4 scripts + ops-monitor. No notification abstraction layer.",
    evidence="Discord webhook URL scattered across multiple scripts")

engine.answer("BQ-09", "TQ-09.3", 1, "IMPROVE",
    "EMBER is the AI backbone. Replacing it would require rewriting all skill routing. However EMBER itself supports multiple providers (Anthropic, OpenAI, etc.), so the LLM vendor is abstracted.",
    evidence="EMBER provider registry supports fallback")

engine.answer("BQ-09", "TQ-09.3", 2, "PASS",
    "ops-monitor uses standard PostgreSQL (via docker exec psql). Data is in standard SQL tables. No vendor-specific features.",
    evidence="cos_tasks schema — standard ANSI SQL")

# ─── BQ-10: Resilience & Recovery ─────────────────────────────────────────────

# TQ-10.1 Self-Healing
engine.answer("BQ-10", "TQ-10.1", 0, "PASS",
    "ops-monitor restarts automatically via Docker restart: unless-stopped. EMBER containers all have restart policies. TrueNAS cron restarts automatically on each interval.",
    evidence="docker-compose.yml restart policies")

engine.answer("BQ-10", "TQ-10.1", 1, "GAP",
    "If ops-monitor is down when a CoS skill fires (remind-me, my-tasks, daily-summary), the skill's http_request action returns an error and the user gets 'something went wrong'. No retry, no queue, no degraded mode.",
    evidence="EMBER skill executor — http_request returns error dict, no retry logic")
engine.add_gap("BQ-10", "TQ-10.1",
    "CoS skills have no retry on ops-monitor failure. If ops-monitor is restarting (takes ~5s), a remind-me invocation during that window fails permanently — the task is never created.",
    severity="medium",
    fix="Add retry logic to the EMBER http_request executor (1 retry after 2s), OR add a final llm_generate fallback that tells the user to try again if the http_request failed.")

engine.answer("BQ-10", "TQ-10.1", 2, "PASS",
    "ops-monitor self-healing actions (endpoint errors) are logged with full tracebacks via Flask error handling.",
    evidence="agent.py log.error() calls in exception handlers")

engine.answer("BQ-10", "TQ-10.1", 3, "PASS",
    "ops-monitor Docker healthcheck prevents stuck container scenarios. On health failure, Docker can restart the container.",
    evidence="docker-compose.yml healthcheck with retries: 3")

# TQ-10.2 Disaster Recovery
engine.answer("BQ-10", "TQ-10.2", 0, "GAP",
    "If TrueNAS host fails: all TrueNAS-based CoS scripts are lost (not in git). ops-monitor is lost (agent.py changes not in git). EMBER is lost (skill DB changes not migrated). Only Windows-side scripts (sync_ember_vault.py, seed_ember_vault.py) survive.",
    evidence="git status on TrueNAS scripts — not tracked")
engine.add_gap("BQ-10", "TQ-10.2",
    "CoS system has no documented recovery procedure. A TrueNAS failure would require rebuilding all scripts, skill DB changes, and ops-monitor modifications from memory or from this session's conversation.",
    severity="high",
    fix="Document the full CoS rebuild procedure in a CLAUDE.md or memory file. Commit all modified files to git. The ops-monitor agent.py change is the highest risk — it's not in git anywhere.")

engine.answer("BQ-10", "TQ-10.2", 1, "PASS",
    "TrueNAS ZFS pool has daily recursive snapshots (2-week retention) and hourly appdata snapshots (1-day). Script files on /mnt/Main are included in daily snapshots.",
    evidence="MEMORY.md — ZFS snapshot schedule")

engine.answer("BQ-10", "TQ-10.2", 2, "GAP",
    "CoS scripts are NOT version-controlled. ZFS snapshots protect against accidental deletion but not against accidental bad edits (a wrong edit followed by snapshot would capture the bad state).",
    evidence="/mnt/Main/scripts/ — no git repo")

engine.answer("BQ-10", "TQ-10.2", 3, "GAP",
    "No recovery procedure has been tested or documented for the CoS system. If ops-monitor is rebuilt from the original repo, all CoS endpoints would be absent.",
    evidence="ops-monitor git repo does not contain CoS endpoint additions")

# TQ-10.3 Single Points of Failure
engine.answer("BQ-10", "TQ-10.3", 0, "GAP",
    "PostgreSQL (ember-postgres) is a single point of failure for: cos_tasks (task reminders), vault_documents (daily logs, knowledge), and EMBER skills (skill definitions). No replica. A postgres crash stops all CoS functionality.",
    evidence="Single postgres container, no replica defined in docker-compose")
engine.add_gap("BQ-10", "TQ-10.3",
    "ember-postgres is a single point of failure for the entire CoS system. Task creation, task checking, daily logs, and skill routing all depend on it. No replica, no fallback.",
    severity="medium",
    fix="Acceptable risk given home-lab context + ZFS snapshots. Document this as an accepted risk. Mitigation: ensure postgres is in the hourly appdata snapshot scope.")

engine.answer("BQ-10", "TQ-10.3", 1, "PASS",
    "If NullClaw goes down, direct EMBER API calls still work. CoS scripts don't depend on NullClaw — they use EMBER directly or ops-monitor directly.",
    evidence="TrueNAS scripts use curl to EMBER and ops-monitor directly")

engine.answer("BQ-10", "TQ-10.3", 2, "PASS",
    "Disk monitoring: ZFS health check runs every 5 min via cron. Morning briefing includes disk status from EMBER vault context.",
    evidence="EMBER system info cron + morning briefing")

engine.answer("BQ-10", "TQ-10.3", 3, "GAP",
    "EMBER backend failure cascades to: all CoS Discord skills broken, morning/evening briefings broken. But task checker (cos_task_checker.py) talks directly to postgres and ops-monitor — it would survive an EMBER backend failure. This is a partial resilience win but not documented.",
    evidence="cos_task_checker.py uses docker exec psql directly")
engine.add_gap("BQ-10", "TQ-10.3",
    "EMBER backend failure stops 3 of 4 CoS capabilities (skills, morning, evening). Only task checker survives. This partial resilience is not documented and users would not know which capabilities are still operational during an outage.",
    severity="low",
    fix="Document the resilience matrix: which CoS capabilities survive which component failures. Share in EMBER or a memory file.")

# ─── Save ─────────────────────────────────────────────────────────────────────
engine.save(STATE_FILE)
print("Assessment complete and saved.")
m = engine.metrics()
print(f"\nProgress: {m['dqs_answered']}/{m['total_dqs']} DQs answered")
print(f"States:   {m['states']}")
print(f"Gaps:     {len(engine.gaps)}")
print(f"Improvements: {len(engine.improvements)}")
