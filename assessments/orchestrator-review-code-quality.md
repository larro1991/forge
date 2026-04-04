# Code Quality Review — orchestrator.py

**File:** `orchestrator/orchestrator/orchestrator.py`  
**Date:** 2026-04-04  
**Reviewer:** Claude (automated subtask)

---

## DQ-01: Single Responsibility

**Result:** IMPROVE

**Evidence:** The `Orchestrator` class handles seven distinct concerns:
- Decomposition orchestration (Phase 1 in `run_task`)
- Dependency resolution and parallel dispatch (`_execute_all_subtasks`, `dispatch_ready`)
- Execute/verify/review loop per subtask (`_execute_subtask`)
- Git operations (`_git_commit`, `_git_clean`)
- Notification (`_notify`, `_send_summary`)
- Budget/governor enforcement (lines 117–133)
- Cost tracking integration (`self.costs.*`)

Git operations and notification are orthogonal to orchestration logic and would be cleaner as injected collaborators (e.g., `GitManager`, `Notifier`). As a coordinator class some breadth is expected, but git commit logic (40 lines) embedded in the orchestrator crosses the line.

---

## DQ-02: Error Handling

**Result:** IMPROVE

**Evidence:**

- **Good:** `run_task` has a top-level `except Exception` guard (line 77) that sets task status and notifies.
- **Good:** Individual futures are wrapped in try/except (lines 153–158).
- **Bad:** `_git_clean` (lines 418–419) silently swallows all exceptions with a bare `except: pass` — no logging whatsoever. A failed checkout/clean before a retry is a meaningful event.
- **Mixed:** `_notify` catches all exceptions and only logs at DEBUG (line 470). Acceptable for fire-and-forget, but DEBUG makes silent failures invisible in production.
- **Mixed:** `dispatch_ready` returns `False` for budget/governor stops — a control-flow return that looks like an error return, making call sites ambiguous (line 123, 133 vs line 139).

---

## DQ-03: Thread Safety

**Result:** IMPROVE

**Evidence:**

- `_safe_update` (line 328) acquires `_state_lock` around `state.update_task(task)` — protecting the I/O call.
- **Issue:** Mutations to `task.*` fields (e.g., `task.status`, `task.error`, `task.completed_at`, `task.current_subtask_idx`) happen **outside** the lock before `_safe_update` is called. Worker threads running `_execute_subtask` in parallel all share the same `task` object. Concurrent writes to different `task.*` fields from parallel workers are unprotected.
- **Monkey-patch risk:** `future._subtask_id = subtask.id` (line 136) — setting a non-standard attribute on a `Future` object works but is fragile and undocumented.
- The Python GIL prevents true data corruption for simple attribute writes, but this is not a safe general pattern — particularly if state serialization reads stale intermediate state.

---

## DQ-04: Resource Management

**Result:** PASS

**Evidence:**

- `ThreadPoolExecutor` used as a context manager (`with` block, line 97) — guaranteed cleanup.
- All `subprocess.run` calls have explicit `timeout=10` (lines 358, 365, 378, 388, 407, 413) — prevents hangs.
- No raw file handles or network connections opened directly in this file.
- Pending futures are explicitly cancelled on subtask failure (lines 179–180).

---

## DQ-05: Code Duplication

**Result:** IMPROVE

**Evidence:**

1. **Cascade escalation logic duplicated** at lines 212–218 and lines 255–260. Both blocks do:
   ```python
   if config.cascade_escalate:
       upgraded = cascade.escalate(model)
       if upgraded:
           model/fix_model = upgraded
           subtask.model_used = ...
   ```
   Could be extracted to `_maybe_escalate(model, subtask) -> str`.

2. **`_deps_met` vs `_deps_met_set`** — two methods doing the same dependency check with different signatures (lines 333 and 345). `_deps_met` (the O(n) version) is **never called** anywhere in the codebase. Dead duplication.

3. **Verify → fix → re-verify** pattern appears at lines 242–275 (verify after execute) and lines 303–309 (verify after review fix). Both are structurally identical but inlined separately.

---

## DQ-06: Naming and Readability

**Result:** IMPROVE

**Evidence:**

- `_deps_met` vs `_deps_met_set`: names don't communicate the meaningful difference (set-based vs task-scan-based). One is dead; the other's name gives no hint why it takes a `set` parameter.
- `dispatch_ready` (line 100) returns `True`/`False` but the name reads as a void action. `_dispatch_ready_subtasks() -> bool` is ambiguous; something like `_submit_ready_subtasks() -> bool` would be clearer.
- `phase = "execute"` / `phase = "fix"` at lines 209, 220 are inline magic strings not tied to any enum.
- `future._subtask_id` (line 136) is an undocumented attribute injection — a reader unfamiliar with the pattern won't expect it.
- Overall structure with phased comments (`# Phase 1`, `# Phase 2`) is readable and well-organised.

---

## DQ-07: Logging

**Result:** PASS

**Evidence:**

- Module-level logger (line 22) — correct pattern.
- Appropriate level usage: `logger.info` for normal flow, `logger.warning` for soft failures, `logger.exception` for unexpected errors.
- Long strings are truncated before logging (`[:80]`, `[:200]`) to prevent log bloat — good defensive practice.
- `logger.exception("Orchestrator error")` (line 78) is minimal but acceptable since the full exception chain is captured automatically by `exception()`.
- `logger.debug("Notification failed (non-critical)")` (line 470) — correctly deprioritised.

---

## DQ-08: Dead Code

**Result:** FAIL

**Evidence:**

Two private methods are defined but never called anywhere in the codebase (confirmed by searching all `.py` files under `/c/Dev/active/orchestrator/`):

1. **`_deps_met`** (line 345–351): Superseded by `_deps_met_set` which is called at line 107. This O(n) variant is unreachable dead code.
2. **`_git_clean`** (line 403–419): Implemented to clean uncommitted changes before retry, but never invoked. The retry loop in `_execute_subtask` does not call it, so dirty state from a failed execution is carried into the next attempt.

The absence of `_git_clean` from the retry loop may be a functional bug, not just dead code — failed executions could leave partial file changes that corrupt the retry.

---

## DQ-09: Magic Values

**Result:** IMPROVE

**Evidence:**

- `time.sleep(0.5)` (line 148) — polling interval hardcoded with no config reference.
- `[:12]` (line 394) — SHA truncation length with no explanation (standard short SHA is 7–12 chars).
- `[:200]` appears three times (lines 175, 235, 396) — consistent but unexplained truncation constant.
- `[:80]` (line 53) — log truncation, different from the 200 used elsewhere.
- `timeout=10` in all subprocess calls (lines 358, 365, 378, 388, 407, 413) — not pulled from config.

These are low-severity but would benefit from named constants or config references.

---

## DQ-10: Dependency Injection

**Result:** IMPROVE

**Evidence:**

Only `state` and `runner` are injectable via constructor (lines 28–34). Six other collaborators are instantiated directly:

```python
self.decomposer = Decomposer()
self.executor = Executor(self.runner)
self.local_executor = LocalExecutor()
self.verifier = Verifier()
self.reviewer = Reviewer()
self.costs = CostTracker()
```

This makes unit-testing the orchestration logic hard — you cannot inject mock collaborators to simulate decomposer failures, verifier rejections, or cost limits without patching. The `state` and `runner` injection shows the pattern is understood; it's just not applied consistently.

---

## Summary

| DQ | Topic | Result |
|----|-------|--------|
| DQ-01 | Single Responsibility | IMPROVE |
| DQ-02 | Error Handling | IMPROVE |
| DQ-03 | Thread Safety | IMPROVE |
| DQ-04 | Resource Management | PASS |
| DQ-05 | Code Duplication | IMPROVE |
| DQ-06 | Naming and Readability | IMPROVE |
| DQ-07 | Logging | PASS |
| DQ-08 | Dead Code | FAIL |
| DQ-09 | Magic Values | IMPROVE |
| DQ-10 | Dependency Injection | IMPROVE |

**Overall:** 2 PASS, 1 FAIL, 7 IMPROVE. No critical defects; the code is functional and readable. The FAIL (dead code including the unhooked `_git_clean`) is the highest-priority finding because its absence may cause subtask retries to operate on dirty state.
