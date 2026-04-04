# FORGE Run: subtitle-pipeline — Results

**Date:** 2026-03-23
**Discipline:** Troubleshooting v1.0.0
**Mode:** full (BQs: BQ-01, BQ-02, BQ-03, BQ-04, BQ-05, BQ-06, BQ-07, BQ-08)
**Version:** FORGE v2.0.0

## Run Metrics

| Metric | Value |
|--------|-------|
| Discipline | Troubleshooting |
| Total DQs evaluated | 113 / 113 |
| ACCEPTED | 0 |
| BLOCKED | 0 |
| GAP | 27 |
| IMPROVE | 3 |
| N/A | 9 |
| PASS | 74 |
| Improvements | 3 |
| Fixes applied | 8 |
| KB entries | 3 |
| Elapsed | 0h 35m |

## Gap Summary

| ID | BQ | Description | Severity | Fix |
|----|-----|-------------|----------|-----|
| G-001 | BQ-01 | opensubtitlescom provider AuthenticationError — largest subtitle source offline | HIGH | Verify/update credentials in Bazarr settings, rese |
| G-002 | BQ-01 | whisperai provider ConnectionError despite Whisper ASR being healthy and reachable | HIGH | Investigate IPv6 vs IPv4 resolution issue, verify  |
| G-003 | BQ-01 | subtitle_automation uses wrong Bazarr API endpoint (/history/series vs /episodes/history) | MEDIUM | Fix API endpoint paths to match Bazarr v1.5.6 API |
| G-004 | BQ-01 | subtitle_auditor not in cron — never runs automatically | HIGH | Add cron entry: e.g. 0 2 * * * python3 /mnt/Main/s |
| G-005 | BQ-01 | 15,028 wanted episodes + 149 wanted movies backlog with only 2 working providers | HIGH | Fix provider auth/connectivity to restore subtitle |
| G-006 | BQ-03 | subtitle_automation config references dead container inop-conversion-queue:5076 in emby_refresh_url | LOW | Remove or update emby_refresh_url in settings.json |
| G-007 | BQ-03 | opensubtitlescom credentials may be expired/invalidated — need to verify on opensubtitles.com website | HIGH | User should log into opensubtitles.com with larro1 |
| G-008 | BQ-03 | Bazarr provider error states persist even after underlying services recover — no auto-reset mechanism | MEDIUM | After fixing root causes, manually reset provider  |
| G-009 | BQ-04 | Error logging in subtitle_automation lacks detail — no URL/response body in error messages | LOW | Add URL and response snippet to bazarr_request() e |
| G-010 | BQ-04 | Health checks are superficial — report healthy when API is broken | MEDIUM | Add Bazarr connectivity check to health endpoint |
| G-011 | BQ-04 | No monitoring/alerting for Bazarr provider status changes | MEDIUM | Add provider status check to EMBER OpsAgent or ser |
| G-012 | BQ-07 | No integration tests between subtitle_automation and Bazarr API | MEDIUM | Add smoke test script that validates all API endpo |
| G-013 | BQ-08 | No automated detection of subtitle pipeline failures - user-reported only | HIGH | Add Bazarr provider status check to EMBER OpsAgent |
| G-014 | BQ-08 | INOP wrapper services have no version compatibility checks with upstream APIs | MEDIUM | Add API version assertion to subtitle_automation s |

## Improvement Opportunities

| ID | BQ | Description | Suggestion |
|----|-----|-------------|------------|
| I-001 | BQ-07 | What is the proposed fix? Describe it sp | Change /health to call Bazarr /api/system/status a |
| I-002 | BQ-08 | What process change would prevent this c | After each run, POST stats (passed/failed/skipped) |
| I-003 | BQ-08 | What technical change would prevent recu | Add /homeserver/subtitles/providers endpoint that  |

## Fixes Applied

| ID | Files | Description | Gaps |
|----|-------|-------------|------|
| F-001 | subtitle_automation.py | Fixed 3 Bazarr API endpoint paths: /history/series -> /episodes/history, /history/movies -> /movies/history | G-003 |
| F-002 | Bazarr container | Cleared throttled_providers.dat and restarted Bazarr. All 4 providers now Good (opensubtitlescom, whisperai, animetosho, yifysubtitles) | G-001, G-002, G-005, G-008 |
| F-003 | subtitle_automation.py | Replaced superficial /health endpoint with deep check that tests Bazarr /api/system/status connectivity | G-010 |
| F-004 | crontab | Added cron entry: 0 2 * * * subtitle_auditor.py --max 50 | G-004 |
| F-006 | subtitle_automation config/settings.json | Removed dead emby_refresh_url referencing non-existent inop-conversion-queue:5076 | G-006 |
| F-007 | ops_agent.py | Added _check_subtitle_pipeline to OpsAgent: monitors Bazarr providers, subtitle_automation health, and auditor freshness | G-011, G-013 |
| F-008 | subtitle_automation.py | Added startup_smoke_test() that validates all 6 Bazarr API endpoints on boot + API version assertion | G-012, G-014 |
| F-009 | subtitle_automation.py | Improved error logging to include HTTP method and endpoint path in error messages | G-009 |

## Accepted Risks

| ID | BQ | Description | Reason |
|----|-----|-------------|--------|
| A-001 | BQ-03 | opensubtitlescom credentials may be expired/invalidated — need to verify on opensubtitles.com website | User verified credentials are valid (F7). Provider now shows Good after throttle state cleared. |

## Verification Pass

### VP-01: Fix Conflict Check — PASS
- [x] no_contradictions
- [x] order_clear

### VP-02: Regression Risk — PASS
- [x] fixes_reference_gaps
- [x] fix_gap_refs_valid
- [x] kb_checked

### VP-03: Security Review of Fixes — PASS
- [x] no_suspicious_fix_patterns
- [x] no_new_dependencies_added

### VP-04: Completeness Check — PASS
- [x] all_bqs_addressed
- [x] all_dqs_answered
- [x] no_unresolved_blocked
- [x] all_gaps_resolved

### VP-05: Acceptance Criteria — PASS
- [x] fixes_have_done_criteria

**Overall: PASS**

## Knowledge Base Entries

### KB-001: API endpoint path mismatch between wrapper code and upstream
- **Category:** api-integration
- **Trigger:** Wrapper service returns Expecting value or JSON decode errors
- **Impact:** Silent failure - wrapper reports healthy but all API calls fail
- **Source:** subtitle-pipeline
- **Discipline:** troubleshooting

### KB-002: Bazarr exponential backoff does not auto-reset when upstream
- **Category:** provider-management
- **Trigger:** Bazarr provider stuck in error state after dependency restored
- **Impact:** Provider stays offline for hours/days even after root cause is fixed
- **Source:** subtitle-pipeline
- **Discipline:** troubleshooting

### KB-003: Write-and-forget deployment gap - script works manually but 
- **Category:** operational
- **Trigger:** Script developed but never added to cron scheduler
- **Impact:** Automated pipeline component never runs, accumulating technical debt silently
- **Source:** subtitle-pipeline
- **Discipline:** troubleshooting
