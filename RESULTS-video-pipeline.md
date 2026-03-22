# FORGE Run: Video Pipeline — Results

**Date:** 2026-03-21
**Target:** `/mnt/Main/inop/video-pipeline/` (tracker.py, controller.py, staging_api.py, intake_agent.py)
**Total DQs evaluated:** ~200
**Total gaps found:** 123
**Gaps accepted (risk-acknowledged):** ~50
**Gaps fixed:** 27
**Gaps deferred:** ~46 (documented, lower priority)

---

## Fixes Applied

### Security (Batch 1-2)
| Fix | Files Changed | Gap |
|-----|--------------|-----|
| API keys moved to env vars | staging_api.py, controller.py, tracker.py, docker-compose.yml | BQ-10: Hardcoded credentials |
| Discord webhook externalized | video_pipeline_monitor.py + /mnt/Main/scripts/config/discord_webhook.txt | BQ-10: Hardcoded secrets |
| Flask error handlers (500, 404) | staging_api.py | BQ-06: Error responses leak internals |
| Config file permissions (0600) | discord_webhook.txt | BQ-10: Credential protection |

### Resilience (Batch 3-4)
| Fix | Files Changed | Gap |
|-----|--------------|-----|
| ffprobe timeout (30s) on all calls | controller.py | BQ-06/11: Blocking operations without timeout |
| approve-all timeout 60s → 600s | staging_api.py | BQ-11: Performance bottleneck |
| Startup consistency check | controller.py (new method) | BQ-06: No recovery after crash |
| Events table cleanup (30-day retention) | controller.py (new method) | BQ-03/11: Unbounded table growth |
| Disk space check before operations | controller.py (new method) | BQ-03/06: No disk full handling |

### Input Safety (Batch 5)
| Fix | Files Changed | Gap |
|-----|--------------|-----|
| Path safety validator (_safe_path) | controller.py | BQ-05: Path traversal, null byte injection |

---

## Accepted Risks (not fixing)

| Category | Reason |
|----------|--------|
| Full auth/RBAC/MFA (BQ-04) | Single-user system, private LAN, Docker network isolation |
| CSRF/security headers (BQ-05) | API-only, no browser UI |
| Full test suite (BQ-08) | Disproportionate effort for personal pipeline |
| Compliance (BQ-10) | Personal media, no regulatory requirements |
| Load testing (BQ-11) | Single host, known scale |
| Staging environment (BQ-09) | Personal project, files bind-mounted for hot-reload |
| Audit trail/tamper-resistance (BQ-07) | Single user |
| Zero-downtime deploys (BQ-09) | Seconds of downtime acceptable |
| Horizontal scaling (BQ-11) | Single SQLite DB, by design |
| Style guide/contribution guide (BQ-12) | Solo developer |

---

## Deferred (worth doing, lower priority)

| Gap | BQ | Priority |
|-----|-----|----------|
| No architectural diagram | BQ-02 | Low |
| No requirements.txt / pinned deps | BQ-02 | Medium |
| No image tagging / version tracking | BQ-02 | Medium |
| No file type validation on intake | BQ-03 | Medium |
| No empty/zero-byte file check | BQ-03 | Medium |
| Post-conversion output not validated | BQ-03 | Medium |
| Inconsistent error handling patterns | BQ-06 | Medium |
| No retry logic for external calls | BQ-06 | Low |
| Structured logging (JSON) | BQ-07 | Low |
| No request correlation IDs | BQ-07 | Low |
| Logs lost on container rebuild | BQ-07 | Medium — volume mount would fix |
| No debug log level toggle | BQ-07 | Low |
| API endpoint documentation | BQ-12 | Medium |
| Tight coupling staging_api → controller | BQ-12 | Low |
| Rate limiting on API | BQ-04 | Low |
| Config externalization (paths/thresholds) | BQ-09 | Medium |
| Cron entries not codified | BQ-09 | Medium |
| No disaster recovery test | BQ-09 | Medium |
| String-formatted SQL in some paths | BQ-05 | Medium |
| No central validation layer | BQ-05 | Low |

---

## Knowledge Base Entries Generated

### KB-001: Hardcoded Secrets in Docker Compose
- **Category:** BQ-10
- **Trigger:** Docker-based service with API integrations
- **Pattern:** API keys hardcoded in source files and docker-compose.yml
- **Impact:** Keys visible in version control, can't rotate without code change
- **Source:** Video pipeline (Radarr/Sonarr/Anthropic keys)
- **Added to Framework:** No — already covered by DQ in TQ-10.1

### KB-002: approve-all Performance Cliff
- **Category:** BQ-11
- **Trigger:** Batch operation that runs ffprobe per file
- **Pattern:** O(n) subprocess spawns with fixed timeout = timeout at scale
- **Impact:** 705 files × ffprobe = exceeded 60s timeout, files stuck in staged
- **Source:** Video pipeline approve-all
- **Added to Framework:** Yes — new DQ under TQ-11.1: "Are batch operations bounded by time or count?"

### KB-003: Three Files, One Secret
- **Category:** BQ-10
- **Trigger:** Multi-file codebase with shared configuration
- **Pattern:** Same API key hardcoded in 3 different files (staging_api, controller, tracker)
- **Impact:** Fix one, miss two. Keys leak through the files you forgot.
- **Source:** Video pipeline
- **Added to Framework:** Yes — new DQ under TQ-10.1: "Is each secret defined in exactly one place?"

---

## Framework Improvements Identified

1. **Add DQ to TQ-11.1:** "Are batch operations bounded by time or count? What happens when input doubles?"
2. **Add DQ to TQ-10.1:** "Is each secret defined in exactly one place, or duplicated across files?"
3. **Add DQ to TQ-02.3:** "Are there build/runtime files (docker-compose, .env) that contain secrets? Are they gitignored?"
4. **Consider BQ-13:** AI/ML-specific questions (this pipeline uses Claude Haiku for intake classification — no questions covered prompt injection, hallucination handling, or token cost)
