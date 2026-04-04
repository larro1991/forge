# FORGE Assessment: portable-claude
**Date**: 2026-03-28
**Disciplines**: Security (triage: BQ-04, BQ-05, BQ-10, BQ-13) + Architecture Review (quick: BQ-01, BQ-03, BQ-08)
**Scope**: `C:\Users\larro\portable-claude\` (PowerShell scripts) + `C:\Github\claude-toolkit\` (Python MCP server)

---

## Run Metrics
| Metric | Value |
|---|---|
| DQs evaluated | 68 |
| PASS | 44 |
| GAP | 7 |
| ACCEPTED | 3 |
| N/A | 14 |
| Fixes applied | 5 |
| Accepted risks | 3 |

---

## Gaps

| ID | BQ | Severity | Description | Fix |
|---|---|---|---|---|
| G-001 | BQ-05 | **HIGH** | Server names from `plugin-config.json` used raw in path construction. `$srv` containing `..\..\Windows\System32` causes `Push-Location` + `uv sync` to execute in attacker-controlled directory. | Allowlist regex `^[a-zA-Z0-9][a-zA-Z0-9-]*$` before use in paths |
| G-002 | BQ-10 | **HIGH** | SSH key copied to drive without verifying it has a passphrase. stage.ps1 only printed a reminder — not enforced. | Check passphrase via `ssh-keygen -y -P ""` before copy; exit 1 if unprotected |
| G-003 | BQ-04 | **MEDIUM** | `winget install` silently fails on machines without admin rights. User left with no uv and no instructions. | Check `IsInRole(Administrator)` before winget; show manual install instructions if non-admin |
| G-004 | BQ-03 | **MEDIUM** | `mcp.json` not backed up before merge. If existing JSON fails to parse, catch block discards the full file (including crucible SSE entry and other servers). | `Copy-Item $mcpPath $mcpBackup -Force` before any modification |
| G-005 | BQ-04 | **MEDIUM** | No plug-in authentication. Stolen unlocked drive → anyone runs plug-in.ps1 → MCP tools (shell exec, file read/write, screen control) activate on their machine under their user account. | Optional PIN (SHA256 hash stored in plugin-config.json). Set via set-pin.ps1. |
| G-006 | BQ-08 | **LOW** | No version field in plugin-config.json. Can't detect stale plug-in state when portable-claude is updated. | Add `version` field to plugin-config.json; plug-in.ps1 can warn on mismatch |
| G-007 | BQ-03 | **LOW** | Drive removal mid-session silently crashes all MCP server processes. Claude Code session loses tools mid-conversation with no diagnostic. | Architectural limit of USB; document as known behavior. Mitigate: unplug.ps1 reminder. |

---

## Fixes Applied

| ID | Fix | Gaps Addressed | Files |
|---|---|---|---|
| F-001 | Allowlist regex `^[a-zA-Z0-9][a-zA-Z0-9-]*$` on server names before path construction | G-001 | `plug-in.ps1` |
| F-002 | SSH key passphrase check in stage.ps1 (`ssh-keygen -y -P ""`); blocks staging if unprotected | G-002 | `stage.ps1` |
| F-003 | Admin check before winget; user-level install instructions shown if non-admin | G-003 | `plug-in.ps1` |
| F-004 | mcp.json backed up to `mcp.json.portable-bak` before any modification; backup preserved on parse failure | G-004 | `plug-in.ps1` |
| F-005 | Optional PIN prompt (SHA256 hash in plugin-config.json). New `set-pin.ps1` to configure. | G-005 | `plug-in.ps1`, `set-pin.ps1` (new) |
| F-006 | `version` field added to plugin-config.json template | G-006 | `stage.ps1` |

---

## Accepted Risks

| ID | Gap | Rationale |
|---|---|---|
| A-001 | `exec_run` executes arbitrary shell commands on the host | By design — this is a tool. User controls Claude Code permissions. Accepted. |
| A-002 | `file_read` can access any file the OS user can access | By design. User controls Claude Code permissions. Accepted. |
| A-003 | G-007: Drive removal = MCP process crash | Architectural limit of running executables from USB. Mitigated by unplug.ps1 reminder. Accepted. |

---

## Architecture Findings (BQ-01, BQ-03, BQ-08)

**BQ-01 — Problem Definition**: Well-defined. Single user, Windows-primary, clear in/out-of-scope. Non-functional gap: no admin guarantee on host (mitigated by F-003).

**BQ-03 — Failure Domains**: Each MCP server is independent — one failure doesn't cascade. The mcp.json merge is now safe with backup (F-004). The remaining design gap is that all servers die on drive removal; this is an accepted limit.

**BQ-08 — Irreversible Decisions**: The drive folder structure (`servers/{name}/.venv/Scripts/{name}.exe`) is baked into plug-in.ps1. If server names change, all deployed plug-in.ps1 scripts on other machines need updating. Mitigated by version field (F-006) which enables detection. Consider: version the scripts alongside config.

---

## Verification

- [x] G-001 fix does not break legitimate server names (claude-toolkit, desktop-copilot, test-harness all pass `^[a-zA-Z0-9][a-zA-Z0-9-]*$`)
- [x] G-002 fix: `ssh-keygen -y -P ""` returns non-zero on passphrase-protected keys — confirmed behavior
- [x] G-003 fix: manual uv install URL shown is the official astral.sh installer
- [x] G-004 fix: backup written before merge; on failure, backup preserved, fresh file written
- [x] G-005 fix: SHA256 hash only stored (not PIN itself); PIN cleared from memory after hash
- [x] No regression on existing plug-in flow for users without PIN set
