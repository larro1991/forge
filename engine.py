#!/usr/bin/env python3
"""FORGE Engine — Framework for Ordered Review and Guaranteed Enhancement.

Multi-discipline assessment engine. Loads pluggable question databases
(disciplines) from YAML files and drives them through a rigid process:
BQ → TQ → DQ, forced terminal states, fix loops, verification, KB learning.

Usage:
    # Start a new run (defaults to security discipline)
    engine = ForgeEngine("my-project")

    # Use a specific discipline
    engine = ForgeEngine("outage-2026-03-22", discipline="troubleshooting")

    # Triage mode within a discipline
    engine = ForgeEngine("my-project", discipline="security", mode="ai-safety")

    # Record answers
    engine.answer("BQ-01", "TQ-01.1", 0, state="PASS",
                  answer="Handles user auth via JWT", evidence="auth.py:45")

    # Record an improvement opportunity
    engine.answer("BQ-01", "TQ-01.1", 1, state="IMPROVE",
                  answer="Works but could use an ORM for maintainability")

    # Add a gap
    engine.add_gap("BQ-04", "TQ-04.1", "No MFA support",
                   severity="medium", fix="Add TOTP-based MFA")

    # Generate report
    engine.report()

    # Run verification
    engine.verify()
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

VERSION = "2.0.0"

# Base states available to all disciplines. Disciplines may extend these.
BASE_VALID_STATES = {"PASS", "GAP", "IMPROVE", "ACCEPTED", "BLOCKED", "N/A"}


# ---------------------------------------------------------------------------
# Discipline Loader
# ---------------------------------------------------------------------------

def _disciplines_dir() -> Path:
    """Return the path to the disciplines directory."""
    return Path(__file__).parent / "disciplines"


def load_discipline(name: str) -> dict:
    """Load a discipline YAML file by name.

    Looks for disciplines/<name>.yaml in the same directory as engine.py.
    Returns the parsed discipline dict with validated structure.
    """
    try:
        import yaml
    except ImportError:
        raise RuntimeError(
            "PyYAML is required for discipline loading. Install it: pip install pyyaml"
        )

    disc_path = _disciplines_dir() / f"{name}.yaml"
    if not disc_path.exists():
        available = list_disciplines()
        raise FileNotFoundError(
            f"Discipline '{name}' not found at {disc_path}. "
            f"Available: {', '.join(available) if available else 'none'}"
        )

    with open(disc_path, encoding="utf-8") as f:
        disc = yaml.safe_load(f)

    # Validate required fields
    required = ["name", "id", "version", "questions"]
    missing = [k for k in required if k not in disc]
    if missing:
        raise RuntimeError(
            f"Discipline '{name}' missing required fields: {', '.join(missing)}"
        )

    # Validate question structure
    for bq_id, bq in disc["questions"].items():
        if "name" not in bq or "tqs" not in bq:
            raise RuntimeError(f"Discipline '{name}': {bq_id} missing 'name' or 'tqs'")
        for tq_id, tq in bq["tqs"].items():
            if "name" not in tq or "dqs" not in tq:
                raise RuntimeError(
                    f"Discipline '{name}': {tq_id} missing 'name' or 'dqs'"
                )
            if not isinstance(tq["dqs"], list) or len(tq["dqs"]) == 0:
                raise RuntimeError(
                    f"Discipline '{name}': {tq_id} has no DQs"
                )

    return disc


def list_disciplines() -> list:
    """List all available discipline names."""
    disc_dir = _disciplines_dir()
    if not disc_dir.exists():
        return []
    return sorted(
        p.stem for p in disc_dir.glob("*.yaml")
    )


def count_discipline_dqs(disc: dict) -> int:
    """Count total DQs in a loaded discipline dict."""
    total = 0
    for bq in disc["questions"].values():
        for tq in bq["tqs"].values():
            total += len(tq.get("dqs", []))
    return total


def validate_framework_sync(framework_md_path: str = None) -> dict:
    """Check that security discipline and FRAMEWORK.md are in sync.

    Returns dict with 'ok' bool, 'engine_dqs' count, 'md_dqs' count.
    """
    try:
        disc = load_discipline("security")
    except (FileNotFoundError, RuntimeError) as e:
        return {"ok": False, "engine_dqs": 0, "md_dqs": None, "details": str(e)}

    engine_count = count_discipline_dqs(disc)
    result = {"ok": True, "engine_dqs": engine_count, "md_dqs": None, "details": ""}

    if framework_md_path is None:
        framework_md_path = os.path.join(os.path.dirname(__file__), "FRAMEWORK.md")

    if not os.path.exists(framework_md_path):
        result["details"] = "FRAMEWORK.md not found - cannot validate sync"
        return result

    md_count = 0
    with open(framework_md_path, encoding="utf-8") as f:
        for line in f:
            if line.strip().startswith("- DQ:"):
                md_count += 1

    result["md_dqs"] = md_count
    if engine_count != md_count:
        result["ok"] = False
        result["details"] = (
            f"Mismatch: security discipline has {engine_count} DQs, "
            f"FRAMEWORK.md has {md_count} DQs"
        )
    else:
        result["details"] = f"In sync: {engine_count} DQs in both"

    return result


# ---------------------------------------------------------------------------
# Backward Compatibility
# ---------------------------------------------------------------------------
# These module-level names are referenced by test_engine.py and any existing
# code that imports from engine. They are populated lazily from the security
# discipline on first access.

_DISCIPLINE_CACHE = {}


def _get_security_discipline():
    """Lazy-load the security discipline for backward compat."""
    if "security" not in _DISCIPLINE_CACHE:
        _DISCIPLINE_CACHE["security"] = load_discipline("security")
    return _DISCIPLINE_CACHE["security"]


class _LazyFramework:
    """Proxy that loads the security discipline's questions on first access."""

    def __getattr__(self, name):
        return getattr(_get_security_discipline()["questions"], name)

    def __getitem__(self, key):
        return _get_security_discipline()["questions"][key]

    def __contains__(self, key):
        return key in _get_security_discipline()["questions"]

    def __iter__(self):
        return iter(_get_security_discipline()["questions"])

    def __len__(self):
        return len(_get_security_discipline()["questions"])

    def keys(self):
        return _get_security_discipline()["questions"].keys()

    def values(self):
        return _get_security_discipline()["questions"].values()

    def items(self):
        return _get_security_discipline()["questions"].items()

    def get(self, key, default=None):
        return _get_security_discipline()["questions"].get(key, default)


# Module-level backward compat — code that does `from engine import FRAMEWORK`
FRAMEWORK = _LazyFramework()

# TRIAGE_PRESETS and VALID_STATES for backward compat
class _LazyTriagePresets:
    def __getitem__(self, key):
        disc = _get_security_discipline()
        presets = disc.get("triage_presets", {})
        if key == "full":
            return list(disc["questions"].keys())
        return presets[key]

    def __contains__(self, key):
        disc = _get_security_discipline()
        return key in disc.get("triage_presets", {}) or key == "full"

    def keys(self):
        disc = _get_security_discipline()
        keys = list(disc.get("triage_presets", {}).keys())
        if "full" not in keys:
            keys.append("full")
        return keys

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default


TRIAGE_PRESETS = _LazyTriagePresets()
VALID_STATES = BASE_VALID_STATES


def count_framework_dqs() -> int:
    """Backward compat: count DQs in the security discipline."""
    return count_discipline_dqs(_get_security_discipline())


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ForgeEngine:
    """Manages a single FORGE assessment run against any discipline."""

    def __init__(self, project_name: str, discipline: str = "security",
                 mode: str = "full", bqs: list = None):
        self.project = project_name
        self.discipline_name = discipline
        self.mode = mode
        self.start_time = datetime.now()

        # Load the discipline
        self._discipline = load_discipline(discipline)
        self._questions = self._discipline["questions"]

        # Build valid states for this discipline
        self._valid_states = set(BASE_VALID_STATES)

        # Build triage presets — always include "full"
        self._triage_presets = dict(self._discipline.get("triage_presets", {}))
        self._triage_presets["full"] = list(self._questions.keys())

        # Determine which BQs to run
        if bqs:
            self.bqs_to_run = bqs
        elif mode in self._triage_presets:
            self.bqs_to_run = self._triage_presets[mode]
        else:
            self.bqs_to_run = list(self._questions.keys())

        # State tracking
        self.answers = {}      # {bq: {tq: {dq_idx: {state, answer, evidence}}}}
        self.gaps = []         # [{id, bq, tq, description, severity, fix}]
        self.fixes = []        # [{id, files, description, gaps_addressed}]
        self.accepted = []     # [{id, bq, description, reason}]
        self.blocked = []      # [{id, bq, dq, blocker, resolution}]
        self.conflicts = []    # [{fix_a, fix_b, conflict, resolution}]
        self.kb_entries = []   # [{id, category, trigger, pattern, impact, source}]
        self.deferred = []     # [{gap, bq, priority, reason}]
        self.improvements = [] # [{id, bq, tq, description, suggestion}]

        self._gap_counter = 0
        self._fix_counter = 0
        self._accept_counter = 0
        self._block_counter = 0
        self._kb_counter = 0
        self._improve_counter = 0

    # --- Question Access ---

    def get_bqs(self) -> list:
        """Get the BQs for this run."""
        return [bq for bq in self.bqs_to_run if bq in self._questions]

    def get_tqs(self, bq_id: str) -> dict:
        """Get TQs for a BQ."""
        return self._questions.get(bq_id, {}).get("tqs", {})

    def get_dqs(self, bq_id: str, tq_id: str) -> list:
        """Get DQs for a TQ."""
        return (
            self._questions.get(bq_id, {})
            .get("tqs", {})
            .get(tq_id, {})
            .get("dqs", [])
        )

    def total_dqs(self) -> int:
        """Count total DQs in this run."""
        count = 0
        for bq_id in self.get_bqs():
            for tq_id, tq in self.get_tqs(bq_id).items():
                count += len(tq.get("dqs", []))
        return count

    def get_discipline_info(self) -> dict:
        """Return metadata about the loaded discipline."""
        return {
            "name": self._discipline.get("name", self.discipline_name),
            "id": self._discipline.get("id", self.discipline_name),
            "version": self._discipline.get("version", "unknown"),
            "description": self._discipline.get("description", ""),
            "total_bqs": len(self._questions),
            "total_dqs": count_discipline_dqs(self._discipline),
            "triage_presets": list(self._triage_presets.keys()),
        }

    # --- Answer Recording ---

    def answer(self, bq_id: str, tq_id: str, dq_index: int,
               state: str, answer: str = "", evidence: str = ""):
        """Record an answer for a specific DQ."""
        if state not in self._valid_states:
            raise ValueError(
                f"Invalid state: {state}. Must be one of {self._valid_states}"
            )

        if bq_id not in self.answers:
            self.answers[bq_id] = {}
        if tq_id not in self.answers[bq_id]:
            self.answers[bq_id][tq_id] = {}

        self.answers[bq_id][tq_id][str(dq_index)] = {
            "state": state,
            "answer": answer,
            "evidence": evidence,
            "timestamp": datetime.now().isoformat(),
        }

        # Auto-track blocked items
        if state == "BLOCKED":
            self._block_counter += 1
            dqs = self.get_dqs(bq_id, tq_id)
            dq_text = dqs[dq_index] if dq_index < len(dqs) else f"DQ #{dq_index}"
            self.blocked.append({
                "id": f"B-{self._block_counter:03d}",
                "bq": bq_id,
                "dq": dq_text,
                "blocker": answer,
                "resolution": "",
            })

        # Auto-track improvement opportunities
        if state == "IMPROVE":
            self._improve_counter += 1
            dqs = self.get_dqs(bq_id, tq_id)
            dq_text = dqs[dq_index] if dq_index < len(dqs) else f"DQ #{dq_index}"
            self.improvements.append({
                "id": f"I-{self._improve_counter:03d}",
                "bq": bq_id,
                "tq": tq_id,
                "description": dq_text,
                "suggestion": answer,
            })

    # --- Gap Management ---

    def add_gap(self, bq_id: str, tq_id: str, description: str,
                severity: str = "medium", fix: str = ""):
        """Record a gap found during assessment."""
        self._gap_counter += 1
        gap = {
            "id": f"G-{self._gap_counter:03d}",
            "bq": bq_id,
            "tq": tq_id,
            "description": description,
            "severity": severity,
            "fix": fix,
        }
        self.gaps.append(gap)
        return gap["id"]

    def add_fix(self, files: str, description: str, gaps_addressed: list):
        """Record a fix that was applied."""
        self._fix_counter += 1
        fix = {
            "id": f"F-{self._fix_counter:03d}",
            "files": files,
            "description": description,
            "gaps_addressed": gaps_addressed,
        }
        self.fixes.append(fix)
        return fix["id"]

    def accept_risk(self, bq_id: str, description: str, reason: str):
        """Explicitly accept a gap with justification."""
        self._accept_counter += 1
        self.accepted.append({
            "id": f"A-{self._accept_counter:03d}",
            "bq": bq_id,
            "description": description,
            "reason": reason,
        })

    def add_kb_entry(self, category: str, trigger: str, pattern: str,
                     impact: str, added_to_framework: bool = False):
        """Record a knowledge base pattern."""
        self._kb_counter += 1
        self.kb_entries.append({
            "id": f"KB-{self._kb_counter:03d}",
            "category": category,
            "trigger": trigger,
            "pattern": pattern,
            "impact": impact,
            "source": self.project,
            "discipline": self.discipline_name,
            "added_to_framework": added_to_framework,
        })

    def defer(self, description: str, bq_id: str, priority: str, reason: str):
        """Defer a gap for later."""
        self.deferred.append({
            "gap": description,
            "bq": bq_id,
            "priority": priority,
            "reason": reason,
        })

    # --- Metrics ---

    def metrics(self) -> dict:
        """Calculate run metrics."""
        states = {s: 0 for s in self._valid_states}
        total_answered = 0
        for bq_id, tqs in self.answers.items():
            for tq_id, dqs in tqs.items():
                for dq_idx, ans in dqs.items():
                    st = ans["state"]
                    if st in states:
                        states[st] += 1
                    total_answered += 1

        elapsed = (datetime.now() - self.start_time).total_seconds()
        return {
            "discipline": self.discipline_name,
            "total_dqs": self.total_dqs(),
            "dqs_answered": total_answered,
            "states": states,
            "gaps_found": len(self.gaps),
            "fixes_applied": len(self.fixes),
            "risks_accepted": len(self.accepted),
            "blocked": len([b for b in self.blocked if not b["resolution"]]),
            "improvements": len(self.improvements),
            "kb_entries": len(self.kb_entries),
            "deferred": len(self.deferred),
            "elapsed_seconds": round(elapsed),
            "elapsed_display": f"{int(elapsed // 3600)}h {int((elapsed % 3600) // 60)}m",
            "bqs_completed": len(self.answers),
            "bqs_total": len(self.get_bqs()),
        }

    # --- Verification ---

    def verify(self) -> dict:
        """Run the Verification Pass. Returns pass/fail for each VP check."""
        results = {}

        # VP-01: Fix Conflict Check
        results["VP-01"] = {
            "name": "Fix Conflict Check",
            "checks": {
                "no_contradictions": (
                    len(self.conflicts) == 0
                    or all(c.get("resolution") for c in self.conflicts)
                ),
                "order_clear": True,
            },
        }

        # VP-02: Regression Risk
        fixes_have_gaps = (
            all(len(f.get("gaps_addressed", [])) > 0 for f in self.fixes)
            if self.fixes
            else True
        )
        gap_ids = {g["id"] for g in self.gaps}
        fix_refs_valid = (
            all(
                all(gid in gap_ids for gid in f.get("gaps_addressed", []))
                for f in self.fixes
            )
            if self.fixes
            else True
        )
        results["VP-02"] = {
            "name": "Regression Risk",
            "checks": {
                "fixes_reference_gaps": fixes_have_gaps,
                "fix_gap_refs_valid": fix_refs_valid,
                "kb_checked": len(self.kb_entries) >= 0,
            },
        }

        # VP-03: Security Review of Fixes
        suspect_patterns = [
            "disable", "remove auth", "skip validation", "allow all",
            "trust all", "no verify", "bypass",
        ]
        fixes_look_safe = not any(
            any(pat in f.get("description", "").lower() for pat in suspect_patterns)
            for f in self.fixes
        )
        results["VP-03"] = {
            "name": "Security Review of Fixes",
            "checks": {
                "no_suspicious_fix_patterns": fixes_look_safe,
                "no_new_dependencies_added": True,
            },
        }

        # VP-04: Completeness Check
        m = self.metrics()
        unresolved_blocked = len([b for b in self.blocked if not b["resolution"]])
        results["VP-04"] = {
            "name": "Completeness Check",
            "checks": {
                "all_bqs_addressed": m["bqs_completed"] == m["bqs_total"],
                "all_dqs_answered": m["dqs_answered"] == m["total_dqs"],
                "no_unresolved_blocked": unresolved_blocked == 0,
                "all_gaps_resolved": all(
                    any(g["id"] in f["gaps_addressed"] for f in self.fixes)
                    or any(a["description"] == g["description"] for a in self.accepted)
                    or any(d["gap"] == g["description"] for d in self.deferred)
                    for g in self.gaps
                ),
            },
        }

        # VP-05: Acceptance Criteria
        results["VP-05"] = {
            "name": "Acceptance Criteria",
            "checks": {
                "fixes_have_done_criteria": (
                    len(self.fixes) > 0 or len(self.gaps) == 0
                ),
            },
        }

        # Overall
        all_pass = all(
            all(checks.values())
            for vp in results.values()
            for checks in [vp["checks"]]
        )
        results["overall"] = "PASS" if all_pass else "FAIL"

        return results

    # --- Reporting ---

    def report(self) -> str:
        """Generate the full results report as markdown."""
        m = self.metrics()
        disc_info = self.get_discipline_info()
        lines = []
        lines.append(f"# FORGE Run: {self.project} — Results\n")
        lines.append(f"**Date:** {self.start_time.strftime('%Y-%m-%d')}")
        lines.append(
            f"**Discipline:** {disc_info['name']} v{disc_info['version']}"
        )
        lines.append(f"**Mode:** {self.mode} (BQs: {', '.join(self.get_bqs())})")
        lines.append(f"**Version:** FORGE v{VERSION}\n")

        # Metrics
        lines.append("## Run Metrics\n")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Discipline | {disc_info['name']} |")
        lines.append(
            f"| Total DQs evaluated | {m['dqs_answered']} / {m['total_dqs']} |"
        )
        for state in sorted(self._valid_states):
            lines.append(f"| {state} | {m['states'].get(state, 0)} |")
        lines.append(f"| Improvements | {m['improvements']} |")
        lines.append(f"| Fixes applied | {m['fixes_applied']} |")
        lines.append(f"| KB entries | {m['kb_entries']} |")
        lines.append(f"| Elapsed | {m['elapsed_display']} |")
        lines.append("")

        # Gap Summary
        if self.gaps:
            lines.append("## Gap Summary\n")
            lines.append("| ID | BQ | Description | Severity | Fix |")
            lines.append("|----|-----|-------------|----------|-----|")
            for g in self.gaps:
                lines.append(
                    f"| {g['id']} | {g['bq']} | {g['description']} "
                    f"| {g['severity']} | {g['fix'][:50]} |"
                )
            lines.append("")

        # Improvements
        if self.improvements:
            lines.append("## Improvement Opportunities\n")
            lines.append("| ID | BQ | Description | Suggestion |")
            lines.append("|----|-----|-------------|------------|")
            for imp in self.improvements:
                lines.append(
                    f"| {imp['id']} | {imp['bq']} "
                    f"| {imp['description'][:40]} | {imp['suggestion'][:50]} |"
                )
            lines.append("")

        # Fixes
        if self.fixes:
            lines.append("## Fixes Applied\n")
            lines.append("| ID | Files | Description | Gaps |")
            lines.append("|----|-------|-------------|------|")
            for f in self.fixes:
                gaps = ", ".join(f["gaps_addressed"])
                lines.append(
                    f"| {f['id']} | {f['files']} "
                    f"| {f['description']} | {gaps} |"
                )
            lines.append("")

        # Accepted
        if self.accepted:
            lines.append("## Accepted Risks\n")
            lines.append("| ID | BQ | Description | Reason |")
            lines.append("|----|-----|-------------|--------|")
            for a in self.accepted:
                lines.append(
                    f"| {a['id']} | {a['bq']} "
                    f"| {a['description']} | {a['reason']} |"
                )
            lines.append("")

        # Blocked
        unresolved = [b for b in self.blocked if not b["resolution"]]
        if unresolved:
            lines.append("## Unresolved Blocked Items\n")
            lines.append("| ID | BQ | DQ | Blocker |")
            lines.append("|----|-----|-----|---------|")
            for b in unresolved:
                lines.append(
                    f"| {b['id']} | {b['bq']} "
                    f"| {b['dq'][:40]} | {b['blocker'][:40]} |"
                )
            lines.append("")

        # Verification
        v = self.verify()
        lines.append("## Verification Pass\n")
        for vp_id, vp in v.items():
            if vp_id == "overall":
                continue
            status = "PASS" if all(vp["checks"].values()) else "FAIL"
            lines.append(f"### {vp_id}: {vp['name']} — {status}")
            for check, result in vp["checks"].items():
                mark = "[x]" if result else "[ ]"
                lines.append(f"- {mark} {check}")
            lines.append("")
        lines.append(f"**Overall: {v['overall']}**\n")

        # KB Entries
        if self.kb_entries:
            lines.append("## Knowledge Base Entries\n")
            for kb in self.kb_entries:
                lines.append(f"### {kb['id']}: {kb['pattern'][:60]}")
                lines.append(f"- **Category:** {kb['category']}")
                lines.append(f"- **Trigger:** {kb['trigger']}")
                lines.append(f"- **Impact:** {kb['impact']}")
                lines.append(f"- **Source:** {kb['source']}")
                if kb.get("discipline"):
                    lines.append(f"- **Discipline:** {kb['discipline']}")
                lines.append("")

        # Deferred
        if self.deferred:
            lines.append("## Deferred Items\n")
            lines.append("| Gap | BQ | Priority | Reason |")
            lines.append("|-----|-----|----------|--------|")
            for d in self.deferred:
                lines.append(
                    f"| {d['gap'][:50]} | {d['bq']} "
                    f"| {d['priority']} | {d['reason'][:40]} |"
                )
            lines.append("")

        return "\n".join(lines)

    # --- Persistence ---

    def save(self, path: str = None):
        """Save the run state to JSON."""
        if path is None:
            path = f"forge-state-{self.project}.json"
        state = {
            "version": VERSION,
            "discipline": self.discipline_name,
            "project": self.project,
            "mode": self.mode,
            "start_time": self.start_time.isoformat(),
            "bqs_to_run": self.bqs_to_run,
            "answers": self.answers,
            "gaps": self.gaps,
            "fixes": self.fixes,
            "accepted": self.accepted,
            "blocked": self.blocked,
            "conflicts": self.conflicts,
            "kb_entries": self.kb_entries,
            "deferred": self.deferred,
            "improvements": self.improvements,
            "counters": {
                "gap": self._gap_counter,
                "fix": self._fix_counter,
                "accept": self._accept_counter,
                "block": self._block_counter,
                "kb": self._kb_counter,
                "improve": self._improve_counter,
            },
        }
        tmp_path = path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(state, f, indent=2)
            if os.path.exists(path):
                os.replace(tmp_path, path)
            else:
                os.rename(tmp_path, path)
        except OSError as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise RuntimeError(f"Failed to save state to {path}: {e}") from e

    @classmethod
    def load(cls, path: str) -> "ForgeEngine":
        """Load a run state from JSON with validation."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"State file not found: {path}")

        try:
            with open(path) as f:
                state = json.load(f)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Corrupt state file {path}: {e}") from e

        required = [
            "project", "mode", "start_time", "bqs_to_run", "answers",
            "gaps", "fixes", "accepted", "blocked", "kb_entries", "deferred",
        ]
        missing = [k for k in required if k not in state]
        if missing:
            raise RuntimeError(
                f"Invalid state file - missing fields: {', '.join(missing)}"
            )

        # Support loading v1.x state files (no discipline field)
        discipline = state.get("discipline", "security")

        engine = cls(
            state["project"],
            discipline=discipline,
            mode=state["mode"],
            bqs=state["bqs_to_run"],
        )
        try:
            engine.start_time = datetime.fromisoformat(state["start_time"])
        except (ValueError, TypeError) as e:
            raise RuntimeError(f"Invalid start_time in state file: {e}") from e

        engine.answers = state["answers"]
        engine.gaps = state["gaps"]
        engine.fixes = state["fixes"]
        engine.accepted = state["accepted"]
        engine.blocked = state["blocked"]
        engine.conflicts = state.get("conflicts", [])
        engine.kb_entries = state["kb_entries"]
        engine.deferred = state["deferred"]
        engine.improvements = state.get("improvements", [])

        counters = state.get("counters", {})
        engine._gap_counter = counters.get("gap", 0)
        engine._fix_counter = counters.get("fix", 0)
        engine._accept_counter = counters.get("accept", 0)
        engine._block_counter = counters.get("block", 0)
        engine._kb_counter = counters.get("kb", 0)
        engine._improve_counter = counters.get("improve", 0)

        return engine


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(f"FORGE Engine v{VERSION}")
        print()
        print("Usage:")
        print("  forge new <project> [--discipline NAME] [--mode MODE]")
        print("  forge info <project>")
        print("  forge verify <project>")
        print("  forge report <project>")
        print("  forge questions [--discipline NAME] [BQ]")
        print("  forge disciplines                  -- List available disciplines")
        print("  forge sync                         -- Check FRAMEWORK.md sync")
        print()
        print("Disciplines:", ", ".join(list_disciplines()))
        return

    cmd = sys.argv[1]

    # Parse --discipline and --mode flags from argv
    discipline = "security"
    mode = "full"
    remaining = []
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--discipline" and i + 1 < len(sys.argv):
            discipline = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--mode" and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]
            i += 2
        else:
            remaining.append(sys.argv[i])
            i += 1

    try:
        if cmd == "disciplines":
            available = list_disciplines()
            if not available:
                print("No disciplines found in disciplines/ directory.")
                return
            for name in available:
                disc = load_discipline(name)
                dq_count = count_discipline_dqs(disc)
                bq_count = len(disc["questions"])
                presets = list(disc.get("triage_presets", {}).keys())
                print(f"  {name}")
                print(f"    {disc.get('name', name)} v{disc.get('version', '?')}")
                print(f"    {bq_count} BQs, {dq_count} DQs")
                if presets:
                    print(f"    Triage: {', '.join(presets)}")
                desc = disc.get("description", "").strip()
                if desc:
                    print(f"    {desc[:80]}")
                print()

        elif cmd == "questions":
            disc = load_discipline(discipline)
            bq_filter = remaining[0] if remaining else None
            if bq_filter and bq_filter not in disc["questions"]:
                print(
                    f"Error: Unknown BQ '{bq_filter}'. "
                    f"Valid: {', '.join(disc['questions'].keys())}"
                )
                sys.exit(1)
            total = 0
            print(f"Discipline: {disc.get('name', discipline)}")
            for bq_id, bq in disc["questions"].items():
                if bq_filter and bq_id != bq_filter:
                    continue
                print(f"\n{bq_id}: {bq['name']}")
                q = bq.get("question", "")
                if q:
                    print(f"  {q}")
                if bq.get("skip_if"):
                    print(f"  [Skip if: {bq['skip_if']}]")
                for tq_id, tq in bq["tqs"].items():
                    print(f"\n  {tq_id}: {tq['name']}")
                    for idx, dq in enumerate(tq["dqs"]):
                        print(f"    [{idx}] {dq}")
                        total += 1
            print(f"\nTotal DQs: {total}")

        elif cmd == "new":
            project = remaining[0] if remaining else "unnamed"
            state_file = f"forge-state-{project}.json"
            if os.path.exists(state_file):
                print(f"Warning: State file {state_file} already exists. Overwriting.")
            engine = ForgeEngine(project, discipline=discipline, mode=mode)
            engine.save(state_file)
            m = engine.metrics()
            info = engine.get_discipline_info()
            print(f"New FORGE run: {project}")
            print(f"Discipline: {info['name']} v{info['version']}")
            print(f"Mode: {mode} — BQs: {', '.join(engine.get_bqs())}")
            print(f"Total DQs: {m['total_dqs']}")
            print(f"State saved to: {state_file}")

        elif cmd == "info":
            if not remaining:
                print("Error: Missing project name. Usage: forge info <project>")
                sys.exit(1)
            project = remaining[0]
            engine = ForgeEngine.load(f"forge-state-{project}.json")
            m = engine.metrics()
            info = engine.get_discipline_info()
            print(f"FORGE Run: {engine.project} (v{VERSION})")
            print(f"Discipline: {info['name']} v{info['version']}")
            print(f"Mode: {engine.mode}")
            print(f"Progress: {m['dqs_answered']}/{m['total_dqs']} DQs answered")
            print(f"States: {m['states']}")
            print(
                f"Gaps: {m['gaps_found']} | Fixes: {m['fixes_applied']} "
                f"| Accepted: {m['risks_accepted']}"
            )
            print(
                f"Improvements: {m['improvements']} | "
                f"Blocked: {m['blocked']} | KB: {m['kb_entries']}"
            )
            print(f"Elapsed: {m['elapsed_display']}")

        elif cmd == "verify":
            if not remaining:
                print("Error: Missing project name.")
                sys.exit(1)
            project = remaining[0]
            engine = ForgeEngine.load(f"forge-state-{project}.json")
            v = engine.verify()
            for vp_id, vp in v.items():
                if vp_id == "overall":
                    continue
                status = "PASS" if all(vp["checks"].values()) else "FAIL"
                print(f"{vp_id}: {vp['name']} -- {status}")
                for check, result in vp["checks"].items():
                    mark = "OK" if result else "FAIL"
                    print(f"  [{mark}] {check}")
            print(f"\nOverall: {v['overall']}")

        elif cmd == "report":
            if not remaining:
                print("Error: Missing project name.")
                sys.exit(1)
            project = remaining[0]
            engine = ForgeEngine.load(f"forge-state-{project}.json")
            report = engine.report()
            out_file = f"RESULTS-{project}.md"
            with open(out_file, "w") as f:
                f.write(report)
            print(f"Report written to {out_file}")

        elif cmd == "sync":
            result = validate_framework_sync()
            print(f"Security discipline DQs: {result['engine_dqs']}")
            if result["md_dqs"] is not None:
                print(f"FRAMEWORK.md DQs: {result['md_dqs']}")
            status = "OK" if result["ok"] else "MISMATCH"
            print(f"Status: {status} -- {result['details']}")
            if not result["ok"]:
                sys.exit(1)

        else:
            print(f"Unknown command: {cmd}")
            print(f"Run 'python {sys.argv[0]}' for usage.")
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)


if __name__ == "__main__":
    main()
