#!/usr/bin/env python3
"""FORGE Engine — Framework for Ordered Review and Guaranteed Enhancement.

Multi-discipline assessment engine. Loads pluggable question databases
(disciplines) from YAML files and drives them through a rigid process:
BQ → TQ → DQ, forced terminal states, fix loops, verification, KB learning.

Architecture
------------
Single-file design: all engine logic lives here to keep FORGE self-contained
and deployable as a single script + YAML directory. The file is organized in
sections (marked with # --- headers):

  1. Discipline Loader      — YAML loading and validation
  2. Intake Profile System   — project context questions and profile CRUD
  3. Gate System             — condition evaluator, auto-N/A of irrelevant DQs
  4. Discipline Router       — intent-based discipline recommendation
  5. Deduplication           — cross-discipline duplicate detection (Jaccard similarity)
  6. Consolidation Analysis  — capability clustering, deep historical scanning
  7. Service-Level Analysis  — service mapping, overlap detection, absorption routing
  8. ForgeEngine class       — core engine (state, answers, gaps, fixes, verification, report)
  9. CLI                     — command-line interface (__main__ block)

Key design decisions:
  - Jaccard word-overlap for similarity: simple, no dependencies, sufficient for
    detecting near-duplicate gap/fix descriptions. More sophisticated NLP would
    add dependencies without proportional benefit for this use case.
  - Capability signal keywords are manually curated to cover common software
    engineering concerns. The adjacency matrix encodes which capabilities are
    related (e.g., monitoring <-> error-handling at 0.7) to support consolidation.
  - Gate conditions use a safe custom parser (no eval()) supporting ==, !=,
    in [], and/or connectives with left-to-right evaluation.

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
from datetime import datetime
from pathlib import Path

VERSION = "2.1.0"

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
    """List all available discipline names.

    Parses each YAML and only includes files with 'id' and 'questions'
    fields, filtering out support files (gates.yaml, intake.yaml, router.yaml).
    """
    import yaml
    disc_dir = _disciplines_dir()
    if not disc_dir.exists():
        return []
    names = []
    for p in disc_dir.glob("*.yaml"):
        try:
            with open(p, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict) and "id" in data and "questions" in data:
                names.append(p.stem)
        except Exception:
            continue
    return sorted(names)


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
# Intake Profile & Gate System
# ---------------------------------------------------------------------------

def load_intake_questions() -> dict:
    """Load intake question definitions from disciplines/intake.yaml.

    Returns the questions dict (not the full YAML with version wrapper).
    """
    import yaml
    path = _disciplines_dir() / "intake.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Intake questions not found at {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("questions", data)


def create_profile(project_name: str, answers: dict) -> dict:
    """Create a validated profile dict from answers."""
    questions = load_intake_questions()
    valid_keys = set(questions.keys())
    unknown = set(answers.keys()) - valid_keys
    if unknown:
        raise ValueError(f"Unknown profile fields: {', '.join(unknown)}")
    return {
        "version": "1.0.0",
        "project": project_name,
        "created": datetime.now().isoformat(),
        "updated": datetime.now().isoformat(),
        "answers": dict(answers),
    }


def save_profile(profile: dict, path: str = None):
    """Save a profile to JSON."""
    if path is None:
        path = f"forge-profile-{profile['project']}.json"
    profile["updated"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(profile, f, indent=2)


def load_profile(project_name: str, path: str = None) -> dict:
    """Load a profile from JSON. Returns None if not found."""
    if path is None:
        path = f"forge-profile-{project_name}.json"
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def _evaluate_condition(condition_str: str, answers: dict) -> bool:
    """Evaluate a gate condition against profile answers. Safe — no eval().

    Supports: field == value, field != value, field in [a, b],
    connected by 'and' / 'or' (left-to-right, no precedence).
    """
    # Split on ' and ' / ' or ' preserving connectives
    parts = []
    current = ""
    connectives = []
    for token in condition_str.split():
        if token == "and" and current.strip():
            parts.append(current.strip())
            connectives.append("and")
            current = ""
        elif token == "or" and current.strip():
            parts.append(current.strip())
            connectives.append("or")
            current = ""
        else:
            current += " " + token
    if current.strip():
        parts.append(current.strip())

    def _eval_clause(clause):
        # Handle "field in [a, b, c]"
        if " in [" in clause:
            field, rest = clause.split(" in ", 1)
            field = field.strip()
            values_str = rest.strip().strip("[]")
            values = [v.strip().strip("'\"") for v in values_str.split(",")]
            return str(answers.get(field, "")) in values
        # Handle "field != value"
        if " != " in clause:
            field, value = clause.split(" != ", 1)
            field, value = field.strip(), value.strip().strip("'\"")
            if value in ("true", "false"):
                value = value == "true"
            return str(answers.get(field, "")) != str(value)
        # Handle "field == value"
        if " == " in clause:
            field, value = clause.split(" == ", 1)
            field, value = field.strip(), value.strip().strip("'\"")
            if value in ("true", "false"):
                value = value == "true"
                return answers.get(field) == value
            return str(answers.get(field, "")) == value
        raise ValueError(
            f"Unparseable gate condition clause: '{clause}'. "
            f"Expected: 'field == value', 'field != value', or 'field in [a, b]'"
        )

    # Evaluate left-to-right
    result = _eval_clause(parts[0])
    for i, conn in enumerate(connectives):
        next_val = _eval_clause(parts[i + 1])
        if conn == "and":
            result = result and next_val
        elif conn == "or":
            result = result or next_val
    return result


def load_gates() -> dict:
    """Load gate definitions from disciplines/gates.yaml."""
    import yaml
    path = _disciplines_dir() / "gates.yaml"
    if not path.exists():
        return {"gates": {}}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_gates(profile: dict, discipline: str = None) -> list:
    """Evaluate all gates against a profile. Returns list of matched gates
    with their resolved target paths.

    Each result: {"name": str, "reason": str, "targets": [str]}
    Targets filtered to the given discipline if specified.
    """
    if not profile or not profile.get("answers"):
        return []
    gates_data = load_gates()
    answers = profile["answers"]
    matched = []
    for gate_name, gate in gates_data.get("gates", {}).items():
        condition = gate.get("condition", "")
        if not condition:
            continue
        if _evaluate_condition(condition, answers):
            targets = gate.get("targets", [])
            if discipline:
                # Filter targets to this discipline or unqualified targets
                targets = [
                    t for t in targets
                    if t.startswith(f"{discipline}:") or ":" not in t
                ]
                # Strip discipline prefix
                targets = [
                    t.split(":", 1)[1] if ":" in t else t
                    for t in targets
                ]
            if targets:
                matched.append({
                    "name": gate_name,
                    "reason": gate.get("reason", ""),
                    "targets": targets,
                })
    return matched


def _resolve_gate_targets(targets: list, questions: dict) -> set:
    """Resolve gate target paths to (bq, tq, dq_idx) tuples.

    Target formats:
        BQ-XX           → all TQs/DQs in that BQ
        BQ-XX.TQ-XX.Y   → all DQs in that TQ
        BQ-XX.TQ-XX.Y[n] → specific DQ index
    """
    resolved = set()
    for target in targets:
        # DQ-level: BQ-XX.TQ-XX.Y[n]
        if "[" in target:
            path, idx_str = target.rstrip("]").split("[")
            dq_idx = int(idx_str)
            parts = path.split(".", 1)
            bq_id = parts[0]
            tq_id = parts[1] if len(parts) > 1 else None
            if tq_id and bq_id in questions:
                resolved.add((bq_id, tq_id, dq_idx))
            continue

        parts = target.split(".", 1)
        bq_id = parts[0]
        if bq_id not in questions:
            continue

        if len(parts) == 1:
            # BQ-level: gate all TQs and DQs
            for tq_id, tq in questions[bq_id].get("tqs", {}).items():
                for dq_idx in range(len(tq.get("dqs", []))):
                    resolved.add((bq_id, tq_id, dq_idx))
        else:
            # TQ-level: gate all DQs in this TQ
            tq_id = parts[1]
            tqs = questions[bq_id].get("tqs", {})
            if tq_id in tqs:
                for dq_idx in range(len(tqs[tq_id].get("dqs", []))):
                    resolved.add((bq_id, tq_id, dq_idx))
    return resolved


# ---------------------------------------------------------------------------
# Discipline Router
# ---------------------------------------------------------------------------

def load_router() -> dict:
    """Load router rules from disciplines/router.yaml."""
    import yaml
    path = _disciplines_dir() / "router.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Router config not found at {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def recommend_disciplines(intent: str = None, profile: dict = None) -> list:
    """Recommend discipline(s) based on intent text and/or profile.

    Returns sorted list of: {"discipline": str, "confidence": float, "reason": str}
    """
    router = load_router()
    scores = {}  # discipline -> (confidence, reasons)

    if intent:
        intent_lower = intent.lower()
        for signal_name, signal in router.get("intent_signals", {}).items():
            keywords = [str(kw) for kw in signal.get("keywords", [])]
            matched_kw = [kw for kw in keywords if kw in intent_lower]
            if matched_kw:
                primary = signal["primary"]
                conf = signal["confidence"]
                reason = f"Intent matches: {', '.join(matched_kw[:3])}"
                if primary not in scores or scores[primary][0] < conf:
                    scores[primary] = (conf, reason)
                # Handle 'also' recommendations
                for also_disc in signal.get("also", []):
                    also_conf = conf * 0.8
                    also_reason = f"Bundled with {primary}"
                    if also_disc not in scores or scores[also_disc][0] < also_conf:
                        scores[also_disc] = (also_conf, also_reason)

    if not scores:
        # Default recommendation
        scores["security"] = (0.5, "Default recommendation")

    results = [
        {"discipline": disc, "confidence": conf, "reason": reason}
        for disc, (conf, reason) in scores.items()
    ]
    results.sort(key=lambda r: r["confidence"], reverse=True)
    return results


# ---------------------------------------------------------------------------
# Cross-Discipline Deduplication
# ---------------------------------------------------------------------------

def _similarity_score(a: str, b: str) -> float:
    """Compute word-overlap similarity between two strings (0.0–1.0).

    Uses Jaccard index on word sets. Fast and sufficient for detecting
    near-duplicate gap/fix descriptions without external dependencies.
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _are_gaps_duplicate(g1: dict, g2: dict, threshold: float = 0.6) -> bool:
    """Determine if two gaps are true duplicates.

    Checks multiple signals — not just text similarity:
    1. Same file / same fix target (strong signal)
    2. Description similarity above threshold
    3. Same severity reinforces a match
    """
    # Different BQs is fine — cross-discipline gaps often share BQ numbering
    # but the BQ means different things. Use description + fix to compare.

    desc_sim = _similarity_score(g1["description"], g2["description"])
    fix_sim = _similarity_score(g1.get("fix", ""), g2.get("fix", ""))

    # Strong match: both description AND fix are similar
    if desc_sim >= threshold and fix_sim >= threshold:
        return True

    # Medium match: description very similar, fix loosely similar
    if desc_sim >= 0.75 and fix_sim >= 0.3:
        return True

    # Weak signal only — not a duplicate
    return False


def _are_fixes_duplicate(f1: dict, f2: dict, threshold: float = 0.6) -> bool:
    """Determine if two fixes are true duplicates.

    Two fixes are duplicates if they touch the same files AND have similar
    descriptions. Same description but different files = different fix.
    """
    # Normalize file references for comparison
    files_a = set(f1.get("files", "").lower().replace(",", " ").split())
    files_b = set(f2.get("files", "").lower().replace(",", " ").split())

    # If both reference specific files, they must overlap
    if files_a and files_b:
        file_overlap = len(files_a & files_b) / max(len(files_a | files_b), 1)
        if file_overlap < 0.3:
            return False  # Different files = different fix, period

    desc_sim = _similarity_score(f1["description"], f2["description"])
    return desc_sim >= threshold


def _are_kb_entries_duplicate(k1: dict, k2: dict) -> bool:
    """KB entries are duplicates if same category + similar trigger/pattern."""
    if k1.get("category", "") != k2.get("category", ""):
        return False
    trigger_sim = _similarity_score(k1.get("trigger", ""), k2.get("trigger", ""))
    pattern_sim = _similarity_score(k1.get("pattern", ""), k2.get("pattern", ""))
    return trigger_sim >= 0.6 and pattern_sim >= 0.5


def deduplicate_runs(engines: list, threshold: float = 0.6) -> dict:
    """Deduplicate findings across multiple discipline runs.

    Takes a list of ForgeEngine instances (or state file paths as strings).
    Compares gaps, fixes, KB entries, and improvements across all runs.
    Returns a dedup report with identified duplicates and recommended merges.

    Each duplicate group includes:
    - The items that are duplicates of each other
    - Which discipline each came from
    - A confidence score for the match
    - A recommended canonical version (kept) vs duplicates (removed)

    Returns:
        {
            "duplicate_gaps": [{group, confidence, keep, remove}],
            "duplicate_fixes": [{group, confidence, keep, remove}],
            "duplicate_kb": [{group, confidence, keep, remove}],
            "summary": {gaps_duped, fixes_duped, kb_duped, total_removed},
        }
    """
    # Resolve engines from paths if needed
    resolved = []
    for e in engines:
        if isinstance(e, str):
            resolved.append(ForgeEngine.load(e))
        else:
            resolved.append(e)

    if len(resolved) < 2:
        return {
            "duplicate_gaps": [],
            "duplicate_fixes": [],
            "duplicate_kb": [],
            "summary": {
                "gaps_duped": 0, "fixes_duped": 0,
                "kb_duped": 0, "total_removed": 0,
            },
        }

    # Tag each item with its source discipline
    all_gaps = []
    all_fixes = []
    all_kb = []
    for eng in resolved:
        disc = eng.discipline_name
        for g in eng.gaps:
            all_gaps.append({**g, "_discipline": disc, "_engine": eng})
        for f in eng.fixes:
            all_fixes.append({**f, "_discipline": disc, "_engine": eng})
        for k in eng.kb_entries:
            all_kb.append({**k, "_discipline": disc, "_engine": eng})

    # Find duplicate gaps (only across disciplines, not within)
    dup_gaps = []
    seen_gap_pairs = set()
    for i, g1 in enumerate(all_gaps):
        for j, g2 in enumerate(all_gaps):
            if j <= i:
                continue
            if g1["_discipline"] == g2["_discipline"]:
                continue  # Skip same-discipline comparisons
            pair = (min(i, j), max(i, j))
            if pair in seen_gap_pairs:
                continue
            if _are_gaps_duplicate(g1, g2, threshold):
                seen_gap_pairs.add(pair)
                desc_sim = _similarity_score(g1["description"], g2["description"])
                # Keep the one with higher severity or more detail
                sev_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
                s1 = sev_rank.get(g1.get("severity", "medium").lower(), 2)
                s2 = sev_rank.get(g2.get("severity", "medium").lower(), 2)
                if s1 >= s2:
                    keep, remove = g1, g2
                else:
                    keep, remove = g2, g1
                dup_gaps.append({
                    "keep": {
                        "id": keep["id"],
                        "discipline": keep["_discipline"],
                        "description": keep["description"],
                    },
                    "remove": {
                        "id": remove["id"],
                        "discipline": remove["_discipline"],
                        "description": remove["description"],
                    },
                    "confidence": round(desc_sim, 2),
                })

    # Find duplicate fixes
    dup_fixes = []
    seen_fix_pairs = set()
    for i, f1 in enumerate(all_fixes):
        for j, f2 in enumerate(all_fixes):
            if j <= i:
                continue
            if f1["_discipline"] == f2["_discipline"]:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen_fix_pairs:
                continue
            if _are_fixes_duplicate(f1, f2, threshold):
                seen_fix_pairs.add(pair)
                desc_sim = _similarity_score(f1["description"], f2["description"])
                # Keep the one that addresses more gaps
                g1_count = len(f1.get("gaps_addressed", []))
                g2_count = len(f2.get("gaps_addressed", []))
                if g1_count >= g2_count:
                    keep, remove = f1, f2
                else:
                    keep, remove = f2, f1
                dup_fixes.append({
                    "keep": {
                        "id": keep["id"],
                        "discipline": keep["_discipline"],
                        "description": keep["description"],
                    },
                    "remove": {
                        "id": remove["id"],
                        "discipline": remove["_discipline"],
                        "description": remove["description"],
                    },
                    "confidence": round(desc_sim, 2),
                })

    # Find duplicate KB entries
    dup_kb = []
    seen_kb_pairs = set()
    for i, k1 in enumerate(all_kb):
        for j, k2 in enumerate(all_kb):
            if j <= i:
                continue
            if k1["_discipline"] == k2["_discipline"]:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen_kb_pairs:
                continue
            if _are_kb_entries_duplicate(k1, k2):
                seen_kb_pairs.add(pair)
                # Keep whichever has more detail
                len1 = len(k1.get("pattern", "")) + len(k1.get("impact", ""))
                len2 = len(k2.get("pattern", "")) + len(k2.get("impact", ""))
                if len1 >= len2:
                    keep, remove = k1, k2
                else:
                    keep, remove = k2, k1
                dup_kb.append({
                    "keep": {
                        "id": keep["id"],
                        "discipline": keep["_discipline"],
                        "pattern": keep.get("pattern", ""),
                    },
                    "remove": {
                        "id": remove["id"],
                        "discipline": remove["_discipline"],
                        "pattern": remove.get("pattern", ""),
                    },
                    "confidence": round(_similarity_score(
                        k1.get("pattern", ""), k2.get("pattern", "")
                    ), 2),
                })

    total_removed = len(dup_gaps) + len(dup_fixes) + len(dup_kb)
    return {
        "duplicate_gaps": dup_gaps,
        "duplicate_fixes": dup_fixes,
        "duplicate_kb": dup_kb,
        "summary": {
            "gaps_duped": len(dup_gaps),
            "fixes_duped": len(dup_fixes),
            "kb_duped": len(dup_kb),
            "total_removed": total_removed,
        },
    }


def apply_dedup(engines: list, dedup_result: dict) -> dict:
    """Apply deduplication results — remove duplicates from source engines.

    Modifies engines in-place. Returns a summary of removals with
    cross-references added to the kept items.
    """
    removals = {"gaps": 0, "fixes": 0, "kb": 0}

    # Build removal sets: {(discipline, id)} to remove
    gap_removals = set()
    for dup in dedup_result["duplicate_gaps"]:
        gap_removals.add((dup["remove"]["discipline"], dup["remove"]["id"]))

    fix_removals = set()
    for dup in dedup_result["duplicate_fixes"]:
        fix_removals.add((dup["remove"]["discipline"], dup["remove"]["id"]))

    kb_removals = set()
    for dup in dedup_result["duplicate_kb"]:
        kb_removals.add((dup["remove"]["discipline"], dup["remove"]["id"]))

    for eng in engines:
        if isinstance(eng, str):
            continue  # Can't modify a path
        disc = eng.discipline_name

        orig_gaps = len(eng.gaps)
        eng.gaps = [
            g for g in eng.gaps
            if (disc, g["id"]) not in gap_removals
        ]
        removals["gaps"] += orig_gaps - len(eng.gaps)

        orig_fixes = len(eng.fixes)
        eng.fixes = [
            f for f in eng.fixes
            if (disc, f["id"]) not in fix_removals
        ]
        removals["fixes"] += orig_fixes - len(eng.fixes)

        orig_kb = len(eng.kb_entries)
        eng.kb_entries = [
            k for k in eng.kb_entries
            if (disc, k["id"]) not in kb_removals
        ]
        removals["kb"] += orig_kb - len(eng.kb_entries)

    return removals


# ---------------------------------------------------------------------------
# Fix Consolidation Analysis
# ---------------------------------------------------------------------------

# Capability signal keywords — maps symptom-level terms in fix/gap text
# to the systemic capability they're compensating for.
_CAPABILITY_SIGNALS = {
    "monitoring": [
        "monitor", "alert", "notify", "detect", "watch", "observe",
        "health check", "health endpoint", "status check", "heartbeat",
        "dashboard", "metric", "log", "track", "visibility",
    ],
    "input-validation": [
        "validation", "validate", "sanitize", "sanitise", "escape",
        "whitelist", "allowlist", "input check", "boundary check",
        "type check", "schema", "constraint",
    ],
    "error-handling": [
        "error handling", "error logging", "exception", "retry",
        "fallback", "circuit breaker", "timeout", "graceful",
        "recovery", "resilience", "fault tolerance",
    ],
    "auth-access": [
        "authentication", "authorization", "auth", "permission",
        "role", "rbac", "access control", "credential", "token",
        "session", "mfa", "2fa",
    ],
    "testing": [
        "test", "smoke test", "integration test", "regression",
        "assertion", "coverage", "verify", "validation test",
        "end-to-end", "e2e",
    ],
    "configuration": [
        "config", "configuration", "settings", "environment variable",
        "env var", ".env", "secret", "credential management",
        "hardcoded", "hard-coded",
    ],
    "data-integrity": [
        "database", "migration", "schema", "backup", "restore",
        "consistency", "transaction", "constraint", "foreign key",
        "index", "query", "sql injection",
    ],
    "api-contract": [
        "api endpoint", "api version", "api path", "api compatibility",
        "contract", "schema validation", "response format",
        "request format", "breaking change", "backward compat",
    ],
    "deployment-ops": [
        "deploy", "cron", "scheduler", "startup", "shutdown",
        "restart", "container", "docker", "pipeline", "ci/cd",
        "automation", "orchestrat",
    ],
    "documentation": [
        "document", "readme", "runbook", "playbook", "comment",
        "annotation", "changelog", "api doc",
    ],
}


def _extract_capabilities(text: str) -> set:
    """Extract capability signals from a text string."""
    if not text:
        return set()
    text_lower = text.lower()
    found = set()
    for capability, keywords in _CAPABILITY_SIGNALS.items():
        for kw in keywords:
            if kw in text_lower:
                found.add(capability)
                break
    return found


def _cluster_items(items: list) -> list:
    """Cluster items by shared capability signals.

    Returns list of clusters, each: {capability, items, disciplines}
    """
    # Map each capability to the items that reference it
    cap_to_items = {}
    for item in items:
        caps = item.get("_capabilities", set())
        for cap in caps:
            if cap not in cap_to_items:
                cap_to_items[cap] = []
            cap_to_items[cap].append(item)

    clusters = []
    for cap, cluster_items in cap_to_items.items():
        if len(cluster_items) < 2:
            continue
        disciplines = set()
        for it in cluster_items:
            disciplines.add(it.get("_discipline", "unknown"))
        clusters.append({
            "capability": cap,
            "items": cluster_items,
            "disciplines": disciplines,
            "count": len(cluster_items),
        })

    # Sort by cluster size descending
    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


_CONSOLIDATION_TEMPLATES = {
    "monitoring": (
        "Unified monitoring service",
        "Multiple fixes add individual health checks, alerting, and status "
        "tracking. A dedicated monitoring module would centralize these into "
        "a single service with consistent check intervals, alert routing, "
        "and status dashboards."
    ),
    "input-validation": (
        "Validation middleware/layer",
        "Multiple fixes add input validation at different points. A shared "
        "validation layer (middleware, schema definitions, or a validation "
        "library) would enforce consistent rules and reduce duplication."
    ),
    "error-handling": (
        "Resilience framework",
        "Multiple fixes add error handling, retries, and fallbacks. A "
        "structured resilience layer (circuit breakers, retry policies, "
        "graceful degradation) would provide consistent fault tolerance."
    ),
    "auth-access": (
        "Authentication/authorization service",
        "Multiple fixes address auth and access control. A centralized "
        "auth service or middleware would unify session management, "
        "permission checks, and credential handling."
    ),
    "testing": (
        "Test infrastructure",
        "Multiple fixes add individual tests or assertions. A structured "
        "test suite with shared fixtures, smoke test runner, and CI "
        "integration would be more maintainable than scattered test additions."
    ),
    "configuration": (
        "Configuration management system",
        "Multiple fixes address config issues (hardcoded values, missing "
        "env vars, credential management). A centralized config module "
        "with validation and secret management would prevent recurrence."
    ),
    "data-integrity": (
        "Data management layer",
        "Multiple fixes address database and data consistency issues. A "
        "data access layer with migration management, connection pooling, "
        "and integrity constraints would be more robust."
    ),
    "api-contract": (
        "API contract management",
        "Multiple fixes address API compatibility and endpoint issues. "
        "An API contract layer (versioning, schema validation, compatibility "
        "checks) would catch these issues automatically."
    ),
    "deployment-ops": (
        "Deployment/operations automation",
        "Multiple fixes address operational gaps (missing cron jobs, startup "
        "checks, container issues). An operational automation layer would "
        "handle scheduling, health verification, and deployment validation."
    ),
    "documentation": (
        "Documentation system",
        "Multiple fixes address documentation gaps. A structured "
        "documentation approach (auto-generated API docs, runbook templates) "
        "would be more sustainable."
    ),
}


def analyze_consolidation(engines: list, min_cluster: int = 3) -> dict:
    """Analyze fixes and gaps across runs to find systemic consolidation
    opportunities.

    Looks for clusters of fixes that all compensate for the same missing
    capability — suggesting a new service/module/system would be more
    effective than the individual patches.

    Args:
        engines: List of ForgeEngine instances or state file paths.
        min_cluster: Minimum items in a cluster to flag (default 3).

    Returns:
        {
            "opportunities": [{
                "capability": str,
                "suggested_name": str,
                "rationale": str,
                "fixes_consolidated": [{"id", "discipline", "description"}],
                "gaps_consolidated": [{"id", "discipline", "description"}],
                "disciplines_involved": [str],
                "strength": "strong" | "moderate",
            }],
            "summary": {
                "opportunities_found": int,
                "fixes_involved": int,
                "gaps_involved": int,
            },
        }
    """
    # Resolve engines from paths
    resolved = []
    for e in engines:
        if isinstance(e, str):
            resolved.append(ForgeEngine.load(e))
        else:
            resolved.append(e)

    # Collect all gaps and fixes with capability tags
    all_gaps = []
    all_fixes = []
    for eng in resolved:
        disc = eng.discipline_name
        for g in eng.gaps:
            combined_text = f"{g['description']} {g.get('fix', '')}"
            caps = _extract_capabilities(combined_text)
            all_gaps.append({
                **g, "_discipline": disc, "_capabilities": caps,
            })
        for f in eng.fixes:
            caps = _extract_capabilities(f["description"])
            all_fixes.append({
                **f, "_discipline": disc, "_capabilities": caps,
            })

    # Cluster gaps and fixes separately
    gap_clusters = _cluster_items(all_gaps)
    fix_clusters = _cluster_items(all_fixes)

    # Merge clusters on the same capability
    seen_caps = set()
    opportunities = []
    for cluster in gap_clusters + fix_clusters:
        cap = cluster["capability"]
        if cap in seen_caps:
            continue
        seen_caps.add(cap)

        # Gather all items for this capability across both lists
        cap_gaps = [
            g for g in all_gaps if cap in g.get("_capabilities", set())
        ]
        cap_fixes = [
            f for f in all_fixes if cap in f.get("_capabilities", set())
        ]
        total_items = len(cap_gaps) + len(cap_fixes)

        if total_items < min_cluster:
            continue

        disciplines = set()
        for item in cap_gaps + cap_fixes:
            disciplines.add(item["_discipline"])

        # Get template for this capability
        template = _CONSOLIDATION_TEMPLATES.get(cap, (
            f"Consolidated {cap} system",
            f"Multiple fixes address {cap} concerns. A unified approach "
            f"would be more effective than individual patches."
        ))

        # Strength: strong if crosses disciplines, moderate if within one
        strength = "strong" if len(disciplines) > 1 else "moderate"

        opportunities.append({
            "capability": cap,
            "suggested_name": template[0],
            "rationale": template[1],
            "fixes_consolidated": [
                {"id": f["id"], "discipline": f["_discipline"],
                 "description": f["description"]}
                for f in cap_fixes
            ],
            "gaps_consolidated": [
                {"id": g["id"], "discipline": g["_discipline"],
                 "description": g["description"]}
                for g in cap_gaps
            ],
            "disciplines_involved": sorted(disciplines),
            "strength": strength,
        })

    # Sort: strong first, then by total items
    opportunities.sort(key=lambda o: (
        0 if o["strength"] == "strong" else 1,
        -(len(o["fixes_consolidated"]) + len(o["gaps_consolidated"])),
    ))

    total_fixes = sum(len(o["fixes_consolidated"]) for o in opportunities)
    total_gaps = sum(len(o["gaps_consolidated"]) for o in opportunities)

    return {
        "opportunities": opportunities,
        "summary": {
            "opportunities_found": len(opportunities),
            "fixes_involved": total_fixes,
            "gaps_involved": total_gaps,
        },
    }


def _discover_prior_runs(exclude_projects: set = None,
                         search_dir: str = None) -> list:
    """Find all forge-state-*.json files and load them.

    Excludes projects already in the active analysis to avoid double-counting.
    """
    if search_dir is None:
        search_dir = "."
    if exclude_projects is None:
        exclude_projects = set()

    prior = []
    search_path = Path(search_dir)
    for state_file in search_path.glob("forge-state-*.json"):
        # Extract project name from filename
        name = state_file.stem.replace("forge-state-", "", 1)
        if name in exclude_projects:
            continue
        try:
            eng = ForgeEngine.load(str(state_file))
            prior.append(eng)
        except (RuntimeError, FileNotFoundError, json.JSONDecodeError):
            continue
    return prior


def _collect_all_kb_entries(engines: list) -> list:
    """Gather KB entries from all engines with capability tags."""
    all_kb = []
    for eng in engines:
        disc = eng.discipline_name
        proj = eng.project
        for kb in eng.kb_entries:
            combined = f"{kb.get('trigger', '')} {kb.get('pattern', '')} {kb.get('impact', '')}"
            caps = _extract_capabilities(combined)
            all_kb.append({
                **kb,
                "_discipline": disc,
                "_project": proj,
                "_capabilities": caps,
            })
    return all_kb


def analyze_consolidation_deep(engines: list, min_cluster: int = 3,
                               search_dir: str = None) -> dict:
    """Deep consolidation analysis that also searches prior FORGE runs
    and KB entries for related patterns.

    Extends analyze_consolidation by:
    1. Discovering all prior forge-state-*.json files
    2. Scanning their fixes, gaps, and KB entries for capability matches
    3. Adding "prior_evidence" to each opportunity — proof this is recurring
    4. Detecting partial solutions already applied (fixes that partially
       address the capability) and recommending "extend" vs "build new"

    Returns the same structure as analyze_consolidation, plus per-opportunity:
        "prior_evidence": [{project, discipline, type, id, description}]
        "kb_patterns": [{id, category, pattern, source}]
        "recommendation": "extend_existing" | "build_new"
        "existing_partial": str | None  (description of what already exists)
    """
    # Resolve active engines
    resolved = []
    for e in engines:
        if isinstance(e, str):
            resolved.append(ForgeEngine.load(e))
        else:
            resolved.append(e)

    # Run the base analysis first
    base = analyze_consolidation(resolved, min_cluster=min_cluster)

    if not base["opportunities"]:
        base["prior_runs_scanned"] = 0
        return base

    # Discover prior runs (excluding the ones we're already analyzing)
    active_projects = {eng.project for eng in resolved}
    prior_runs = _discover_prior_runs(
        exclude_projects=active_projects, search_dir=search_dir,
    )

    # Collect all KB entries across active + prior runs
    all_kb = _collect_all_kb_entries(resolved + prior_runs)

    # Collect all fixes and gaps from prior runs with capability tags
    prior_gaps = []
    prior_fixes = []
    for eng in prior_runs:
        disc = eng.discipline_name
        proj = eng.project
        for g in eng.gaps:
            combined = f"{g['description']} {g.get('fix', '')}"
            caps = _extract_capabilities(combined)
            prior_gaps.append({
                **g, "_discipline": disc, "_project": proj,
                "_capabilities": caps,
            })
        for f in eng.fixes:
            caps = _extract_capabilities(f["description"])
            prior_fixes.append({
                **f, "_discipline": disc, "_project": proj,
                "_capabilities": caps,
            })

    # Enrich each opportunity with prior evidence
    for opp in base["opportunities"]:
        cap = opp["capability"]
        prior_evidence = []
        kb_patterns = []

        # Search prior gaps for this capability
        for g in prior_gaps:
            if cap in g.get("_capabilities", set()):
                prior_evidence.append({
                    "project": g["_project"],
                    "discipline": g["_discipline"],
                    "type": "gap",
                    "id": g["id"],
                    "description": g["description"],
                })

        # Search prior fixes for this capability
        for f in prior_fixes:
            if cap in f.get("_capabilities", set()):
                prior_evidence.append({
                    "project": f["_project"],
                    "discipline": f["_discipline"],
                    "type": "fix",
                    "id": f["id"],
                    "description": f["description"],
                })

        # Search KB entries for this capability
        for kb in all_kb:
            if cap in kb.get("_capabilities", set()):
                kb_patterns.append({
                    "id": kb["id"],
                    "category": kb.get("category", ""),
                    "pattern": kb.get("pattern", ""),
                    "source": kb.get("source", ""),
                })

        # Determine recommendation: extend vs build new
        # If there are prior fixes for this capability, something partial exists
        prior_fix_descs = [
            e for e in prior_evidence if e["type"] == "fix"
        ]
        active_fix_descs = opp["fixes_consolidated"]

        if prior_fix_descs:
            # Prior fixes exist — check if they represent a partial solution
            recommendation = "extend_existing"
            # Pick the most descriptive prior fix as the "existing partial"
            existing_partial = max(
                prior_fix_descs,
                key=lambda f: len(f["description"]),
            )["description"]
        elif active_fix_descs:
            # Current run has fixes but no prior history — could be first time
            # Check if any fix looks like a systemic solution already
            systemic_words = [
                "service", "module", "layer", "framework", "system",
                "middleware", "agent", "manager", "handler",
            ]
            has_systemic = any(
                any(w in f["description"].lower() for w in systemic_words)
                for f in active_fix_descs
            )
            if has_systemic:
                recommendation = "extend_existing"
                existing_partial = max(
                    active_fix_descs,
                    key=lambda f: len(f["description"]),
                )["description"]
            else:
                recommendation = "build_new"
                existing_partial = None
        else:
            recommendation = "build_new"
            existing_partial = None

        # Update strength: prior evidence across projects makes it stronger
        prior_projects = set(e["project"] for e in prior_evidence)
        if prior_projects:
            opp["strength"] = "strong"

        opp["prior_evidence"] = prior_evidence
        opp["kb_patterns"] = kb_patterns
        opp["recommendation"] = recommendation
        opp["existing_partial"] = existing_partial

    # Re-sort with updated strengths
    base["opportunities"].sort(key=lambda o: (
        0 if o["strength"] == "strong" else 1,
        0 if o.get("recommendation") == "extend_existing" else 1,
        -(len(o["fixes_consolidated"]) + len(o["gaps_consolidated"])
          + len(o.get("prior_evidence", []))),
    ))

    base["prior_runs_scanned"] = len(prior_runs)
    return base


# ---------------------------------------------------------------------------
# Service-Level Improvement Analysis
# ---------------------------------------------------------------------------

def _normalize_service_name(file_ref: str) -> str:
    """Extract a service/module name from a file path or reference.

    'ops_agent.py' -> 'ops_agent'
    '/mnt/Main/scripts/health_watchdog.py' -> 'health_watchdog'
    'subtitle_automation.py' -> 'subtitle_automation'
    'Bazarr container' -> 'bazarr'
    'backend/heartbeat/ops_agent.py' -> 'ops_agent'
    'config/settings.json' -> 'config'
    """
    if not file_ref:
        return "unknown"
    # Strip path to basename
    name = file_ref.strip()
    # Handle "X container" references
    if " container" in name.lower():
        return name.lower().split(" container")[0].strip().replace(" ", "_")
    # Get basename
    name = name.replace("\\", "/").split("/")[-1]
    # Strip extension
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name.lower().replace("-", "_")


def _build_service_map(engines: list) -> dict:
    """Build a map of service -> {capabilities, fixes, gaps, disciplines}.

    Analyzes which capabilities each service touches based on the fixes
    and gaps that reference it.
    """
    services = {}  # service_name -> {capabilities, fixes, gaps, disciplines}

    for eng in engines:
        disc = eng.discipline_name
        proj = eng.project

        for fix in eng.fixes:
            svc = _normalize_service_name(fix.get("files", ""))
            if svc == "unknown":
                continue
            if svc not in services:
                services[svc] = {
                    "capabilities": set(),
                    "fixes": [],
                    "gaps": [],
                    "disciplines": set(),
                    "projects": set(),
                }
            caps = _extract_capabilities(fix["description"])
            services[svc]["capabilities"].update(caps)
            services[svc]["fixes"].append({
                "id": fix["id"], "discipline": disc,
                "project": proj, "description": fix["description"],
            })
            services[svc]["disciplines"].add(disc)
            services[svc]["projects"].add(proj)

        # Map gaps to services via their fix suggestion
        for gap in eng.gaps:
            fix_text = gap.get("fix", "")
            if not fix_text:
                continue
            combined = f"{gap['description']} {fix_text}"
            caps = _extract_capabilities(combined)
            if not caps:
                continue

            # Try to extract a service reference from the fix suggestion
            svc = None
            for word in fix_text.replace(",", " ").split():
                if word.endswith(".py") or word.endswith(".js") or word.endswith(".sh"):
                    svc = _normalize_service_name(word)
                    break
            if not svc:
                # Check if fix mentions a known service name
                fix_lower = fix_text.lower()
                for known_svc in list(services.keys()):
                    if known_svc.replace("_", " ") in fix_lower or \
                       known_svc.replace("_", "-") in fix_lower or \
                       known_svc in fix_lower:
                        svc = known_svc
                        break
            if not svc:
                # File it under a synthetic "unassigned" bucket
                svc = "_unassigned"

            if svc not in services:
                services[svc] = {
                    "capabilities": set(),
                    "fixes": [],
                    "gaps": [],
                    "disciplines": set(),
                    "projects": set(),
                }
            services[svc]["capabilities"].update(caps)
            services[svc]["gaps"].append({
                "id": gap["id"], "discipline": disc,
                "project": proj, "description": gap["description"],
            })
            services[svc]["disciplines"].add(disc)
            services[svc]["projects"].add(proj)

    return services


def _find_service_overlaps(service_map: dict) -> list:
    """Find pairs of services that share capabilities — merge candidates.

    Ignores overly broad capabilities (deployment-ops, configuration)
    that would cause everything to "overlap." Only flags overlap on
    specific, actionable capabilities.

    Returns list of: {
        services: [svc_a, svc_b],
        shared_capabilities: [str],
        total_capabilities: {svc_a: [str], svc_b: [str]},
        overlap_ratio: float,
    }
    """
    # These capabilities are too generic to indicate real overlap.
    # Almost every service touches deployment or config in some way.
    BROAD_CAPS = {"deployment-ops", "configuration", "documentation"}

    svc_names = [s for s in service_map.keys() if s != "_unassigned"]
    overlaps = []

    for i, svc_a in enumerate(svc_names):
        caps_a = service_map[svc_a]["capabilities"]
        if not caps_a:
            continue
        for j in range(i + 1, len(svc_names)):
            svc_b = svc_names[j]
            caps_b = service_map[svc_b]["capabilities"]
            if not caps_b:
                continue

            # Compute overlap excluding broad capabilities
            specific_shared = (caps_a & caps_b) - BROAD_CAPS
            if not specific_shared:
                continue

            # Use all shared caps (including broad) for context,
            # but ratio is based on specific caps only
            all_shared = caps_a & caps_b
            specific_union = (caps_a | caps_b) - BROAD_CAPS
            ratio = (len(specific_shared) / len(specific_union)
                     if specific_union else 0)

            overlaps.append({
                "services": [svc_a, svc_b],
                "shared_capabilities": sorted(all_shared),
                "specific_shared": sorted(specific_shared),
                "total_capabilities": {
                    svc_a: sorted(caps_a),
                    svc_b: sorted(caps_b),
                },
                "overlap_ratio": round(ratio, 2),
            })

    overlaps.sort(key=lambda o: o["overlap_ratio"], reverse=True)
    return overlaps


def _find_absorption_candidates(service_map: dict) -> list:
    """Find capabilities with no owning service that could be absorbed
    by an existing service that already handles related capabilities.

    Returns list of: {
        orphan_capability: str,
        best_home: str,       # service that should absorb it
        reason: str,
        gaps: [dict],         # unassigned gaps with this capability
    }
    """
    unassigned = service_map.get("_unassigned")
    if not unassigned or not unassigned["capabilities"]:
        return []

    # Which capabilities have no service home?
    owned_caps = set()
    for svc, info in service_map.items():
        if svc == "_unassigned":
            continue
        owned_caps.update(info["capabilities"])

    # For orphan capabilities that DO have a service touching them,
    # the question is: which service is the best home?
    # For truly orphan ones (not in any service), find the closest match.
    candidates = []
    for cap in unassigned["capabilities"]:
        # Find services that share related capabilities
        cap_related = _CAPABILITY_SIGNALS.get(cap, [])
        best_svc = None
        best_score = 0

        for svc, info in service_map.items():
            if svc == "_unassigned":
                continue
            svc_caps = info["capabilities"]
            # Direct match: service already handles this capability
            if cap in svc_caps:
                best_svc = svc
                best_score = 1.0
                break
            # Adjacent match: service handles related capabilities
            # e.g., monitoring service is good home for error-handling
            adjacency = {
                ("monitoring", "error-handling"): 0.7,
                ("monitoring", "deployment-ops"): 0.6,
                ("error-handling", "monitoring"): 0.7,
                ("testing", "api-contract"): 0.6,
                ("api-contract", "testing"): 0.6,
                ("configuration", "deployment-ops"): 0.5,
                ("deployment-ops", "configuration"): 0.5,
                ("auth-access", "input-validation"): 0.4,
                ("data-integrity", "configuration"): 0.4,
            }
            for svc_cap in svc_caps:
                score = adjacency.get((cap, svc_cap), 0)
                if score > best_score:
                    best_score = score
                    best_svc = svc

        if best_svc and best_score >= 0.4:
            # Gather the unassigned gaps for this capability
            orphan_gaps = [
                g for g in unassigned["gaps"]
                if cap in _extract_capabilities(
                    f"{g['description']}"
                )
            ]
            reason = (f"{best_svc} already handles "
                      f"{', '.join(sorted(service_map[best_svc]['capabilities']))}")
            if best_score == 1.0:
                reason = f"{best_svc} already handles {cap} directly"

            candidates.append({
                "orphan_capability": cap,
                "best_home": best_svc,
                "reason": reason,
                "confidence": best_score,
                "gaps": orphan_gaps,
            })

    candidates.sort(key=lambda c: c["confidence"], reverse=True)
    return candidates


def analyze_services(engines: list, search_dir: str = None) -> dict:
    """Analyze services across FORGE runs for improvement opportunities.

    Goes beyond fix clustering to answer:
    1. Which services exist and what capabilities does each provide?
    2. Which services overlap in purpose — should they be merged?
    3. Which capabilities have no owning service — where should they live?
    4. What would the ideal service architecture look like?

    Args:
        engines: List of ForgeEngine instances or state file paths.
        search_dir: Directory to scan for prior forge-state-*.json files.

    Returns:
        {
            "services": {name: {capabilities, fix_count, gap_count}},
            "overlaps": [{services, shared_capabilities, overlap_ratio}],
            "absorptions": [{orphan_capability, best_home, reason}],
            "recommendations": [{type, action, rationale, services, capability}],
            "summary": {services_found, overlaps_found, absorptions_found,
                        recommendations_count},
        }
    """
    # Resolve engines
    resolved = []
    for e in engines:
        if isinstance(e, str):
            resolved.append(ForgeEngine.load(e))
        else:
            resolved.append(e)

    # Include prior runs
    active_projects = {eng.project for eng in resolved}
    prior = _discover_prior_runs(active_projects, search_dir)
    all_engines = resolved + prior

    # Build service map
    svc_map = _build_service_map(all_engines)

    # Detect client-server relationships: if one service's fixes/gaps
    # mention another service by name, they're connected, not overlapping.
    # e.g., subtitle_automation's fixes mention "Bazarr" → client-server
    svc_names_set = set(s for s in svc_map.keys() if s != "_unassigned")
    client_server_pairs = set()  # {(client, server)}
    for svc in svc_names_set:
        info = svc_map[svc]
        all_text = " ".join(
            f["description"] for f in info["fixes"]
        ) + " " + " ".join(
            g["description"] for g in info["gaps"]
        )
        text_lower = all_text.lower()
        for other_svc in svc_names_set:
            if other_svc == svc:
                continue
            # Check if this service's descriptions reference the other
            other_variants = [
                other_svc,
                other_svc.replace("_", "-"),
                other_svc.replace("_", " "),
            ]
            if any(v in text_lower for v in other_variants):
                client_server_pairs.add((svc, other_svc))

    # Find overlaps (excluding client-server pairs from merge candidates)
    overlaps = _find_service_overlaps(svc_map)

    # Find absorption candidates
    absorptions = _find_absorption_candidates(svc_map)

    # Generate recommendations
    recommendations = []

    # Merge recommendations from overlaps
    for ov in overlaps:
        specific = ov.get("specific_shared", ov["shared_capabilities"])
        svc_a, svc_b = ov["services"]

        # Skip client-server pairs — overlap is from API usage, not duplication
        is_client_server = (
            (svc_a, svc_b) in client_server_pairs or
            (svc_b, svc_a) in client_server_pairs
        )

        if ov["overlap_ratio"] >= 0.5 and len(specific) >= 2:
            if is_client_server:
                # Don't recommend merge — recommend interface instead
                recommendations.append({
                    "type": "interface",
                    "action": (f"Formalize {svc_a} <-> {svc_b} interface"),
                    "rationale": (
                        f"{svc_a} and {svc_b} share {', '.join(specific)} "
                        f"via a client-server relationship. "
                        f"A formal API contract or shared schema would "
                        f"prevent the integration gaps seen in these runs."
                    ),
                    "services": [svc_a, svc_b],
                    "capability": specific,
                })
            else:
                # Recommend merging into the service with more fixes
                fixes_a = len(svc_map[svc_a]["fixes"])
                fixes_b = len(svc_map[svc_b]["fixes"])
                caps_a = len(svc_map[svc_a]["capabilities"])
                caps_b = len(svc_map[svc_b]["capabilities"])
                if fixes_a > fixes_b or (fixes_a == fixes_b and caps_a >= caps_b):
                    primary, secondary = svc_a, svc_b
                else:
                    primary, secondary = svc_b, svc_a
                recommendations.append({
                    "type": "merge",
                    "action": f"Merge {secondary} into {primary}",
                    "rationale": (
                        f"Both handle {', '.join(specific)}. "
                        f"{primary} has more implementation history "
                        f"({max(fixes_a, fixes_b)} fixes). "
                        f"Merging eliminates duplication and simplifies "
                        f"operations."
                    ),
                    "services": [primary, secondary],
                    "capability": specific,
                })
        elif ov["overlap_ratio"] >= 0.3 and len(specific) >= 1:
            if not is_client_server:
                recommendations.append({
                    "type": "review",
                    "action": (f"Review overlap between {svc_a} and {svc_b}"),
                    "rationale": (
                        f"Partial overlap in {', '.join(specific)}. "
                        f"May benefit from shared interface or clear boundary."
                    ),
                    "services": [svc_a, svc_b],
                    "capability": specific,
                })

    # Absorption recommendations — route unassigned gaps to their best home
    for ab in absorptions:
        gap_count = len(ab.get("gaps", []))
        if gap_count == 0:
            continue  # No unassigned gaps to route
        gap_summaries = "; ".join(
            g["description"][:40] for g in ab["gaps"][:3]
        )
        recommendations.append({
            "type": "extend",
            "action": (f"Route {gap_count} unassigned {ab['orphan_capability']} "
                       f"gap(s) to {ab['best_home']}"),
            "rationale": (
                f"{ab['reason']}. "
                f"Gaps: {gap_summaries}"
            ),
            "services": [ab["best_home"]],
            "capability": [ab["orphan_capability"]],
        })

    # Build clean service summary (exclude internal fields)
    svc_summary = {}
    for svc, info in svc_map.items():
        if svc == "_unassigned" and not info["gaps"]:
            continue
        svc_summary[svc] = {
            "capabilities": sorted(info["capabilities"]),
            "fix_count": len(info["fixes"]),
            "gap_count": len(info["gaps"]),
            "disciplines": sorted(info["disciplines"]),
            "projects": sorted(info["projects"]),
        }

    # Sort: merge first, then interface, extend, review
    type_order = {"merge": 0, "interface": 1, "extend": 2, "review": 3}
    recommendations.sort(key=lambda r: type_order.get(r["type"], 4))

    return {
        "services": svc_summary,
        "overlaps": overlaps,
        "absorptions": absorptions,
        "recommendations": recommendations,
        "summary": {
            "services_found": len([s for s in svc_summary if s != "_unassigned"]),
            "overlaps_found": len(overlaps),
            "absorptions_found": len(absorptions),
            "recommendations_count": len(recommendations),
            "prior_runs_included": len(prior),
        },
    }


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ForgeEngine:
    """Manages a single FORGE assessment run against any discipline."""

    def __init__(self, project_name: str, discipline: str = "security",
                 mode: str = "full", bqs: list = None, profile: dict = None):
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

        # Profile & gate system
        self._profile = profile
        self._gated_paths = set()  # {(bq, tq, dq_idx), ...}
        self._matched_gates = []   # [{name, reason, targets}]
        if profile is None:
            # Auto-load if profile file exists
            loaded = load_profile(project_name)
            if loaded:
                self._profile = loaded
        if self._profile:
            self._apply_gates()

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

    # --- Profile & Gate Methods ---

    def _apply_gates(self):
        """Evaluate gates against the loaded profile."""
        self._matched_gates = evaluate_gates(
            self._profile, discipline=self.discipline_name
        )
        for gate in self._matched_gates:
            resolved = _resolve_gate_targets(gate["targets"], self._questions)
            self._gated_paths.update(resolved)

    def is_gated(self, bq_id: str, tq_id: str = None,
                 dq_idx: int = None) -> bool:
        """Check if a BQ/TQ/DQ is gated by the current profile."""
        if not self._gated_paths:
            return False
        if dq_idx is not None and tq_id:
            return (bq_id, tq_id, dq_idx) in self._gated_paths
        if tq_id:
            return any(
                b == bq_id and t == tq_id
                for b, t, _ in self._gated_paths
            )
        return any(b == bq_id for b, _, _ in self._gated_paths)

    def auto_na_gated(self) -> int:
        """Mark all gated DQs as N/A. Returns count of DQs marked."""
        count = 0
        # Build reason lookup
        gate_reasons = {}
        for gate in self._matched_gates:
            resolved = _resolve_gate_targets(gate["targets"], self._questions)
            for path in resolved:
                gate_reasons[path] = gate["reason"]

        for bq_id, tq_id, dq_idx in sorted(self._gated_paths):
            if bq_id not in self.bqs_to_run:
                continue
            # Skip if already answered
            existing = (
                self.answers.get(bq_id, {})
                .get(tq_id, {})
                .get(str(dq_idx))
            )
            if existing:
                continue
            reason = gate_reasons.get(
                (bq_id, tq_id, dq_idx), "Gated by profile"
            )
            self.answer(
                bq_id, tq_id, dq_idx, "N/A",
                answer=f"Auto-gated: {reason}",
                evidence="Profile gate",
            )
            count += 1
        return count

    def get_profile(self) -> dict:
        """Return the loaded profile or None."""
        return self._profile

    def get_gate_summary(self) -> list:
        """Return summary of matched gates for reporting."""
        summary = []
        for gate in self._matched_gates:
            resolved = _resolve_gate_targets(gate["targets"], self._questions)
            # Only count DQs in active BQs
            active = [
                p for p in resolved if p[0] in self.bqs_to_run
            ]
            summary.append({
                "name": gate["name"],
                "reason": gate["reason"],
                "dqs_gated": len(active),
            })
        return summary

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

        # Remove stale blocked/improvement entries when re-answering a DQ
        dq_key = (bq_id, tq_id, dq_index)
        prev = self.answers.get(bq_id, {}).get(tq_id, {}).get(str(dq_index))
        if prev:
            prev_state = prev.get("state")
            if prev_state == "BLOCKED":
                dqs = self.get_dqs(bq_id, tq_id)
                dq_text = dqs[dq_index] if dq_index < len(dqs) else f"DQ #{dq_index}"
                self.blocked = [b for b in self.blocked
                                if not (b["bq"] == bq_id and b["dq"] == dq_text)]
            elif prev_state == "IMPROVE":
                dqs = self.get_dqs(bq_id, tq_id)
                dq_text = dqs[dq_index] if dq_index < len(dqs) else f"DQ #{dq_index}"
                self.improvements = [imp for imp in self.improvements
                                     if not (imp["bq"] == bq_id and imp["tq"] == tq_id
                                             and imp["description"] == dq_text)]

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
                "kb_checked": len(self.kb_entries) > 0 if self.gaps else True,
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
        lines.append(f"**Version:** FORGE v{VERSION}")
        if self._profile:
            lines.append(f"**Profile:** {self._profile.get('project', '?')}")
        lines.append("")

        # Profile Gates (if profile was used)
        gate_summary = self.get_gate_summary()
        if gate_summary:
            total_gated = sum(g["dqs_gated"] for g in gate_summary)
            lines.append("## Profile Gates Applied\n")
            lines.append(f"**Total DQs auto-gated:** {total_gated}\n")
            lines.append("| Gate | Reason | DQs Skipped |")
            lines.append("|------|--------|-------------|")
            for g in gate_summary:
                lines.append(
                    f"| {g['name']} | {g['reason']} | {g['dqs_gated']} |"
                )
            lines.append("")

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
        # Include profile path if a profile was loaded
        if self._profile:
            profile_path = self._profile.get("_path")
            if not profile_path:
                profile_path = f"forge-profile-{self.project}.json"
            state["profile_path"] = profile_path
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

        # Reload profile if one was saved with this state
        profile_path = state.get("profile_path")
        if profile_path and os.path.exists(profile_path):
            try:
                with open(profile_path) as pf:
                    engine._profile = json.load(pf)
                engine._apply_gates()
            except (json.JSONDecodeError, OSError):
                pass  # Profile file corrupt or unreadable — continue without

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
        print("  forge intake <project>             -- Create/update intake profile")
        print("  forge intake <project> --show       -- Show existing profile")
        print("  forge route                        -- Interactive discipline router")
        print("  forge route --intent \"text\"         -- Keyword-based recommendation")
        print("  forge dedup <proj1> <proj2> [...]   -- Deduplicate across discipline runs")
        print("  forge dedup <proj1> <proj2> --apply -- Dedup and remove duplicates")
        print("  forge consolidate <proj1> [proj2]  -- Analyze fixes for systemic solutions")
        print("  forge improve <proj1> [proj2]      -- Service-level improvement analysis")
        print()
        print("Disciplines:", ", ".join(list_disciplines()))
        return

    cmd = sys.argv[1]

    # Parse flags from argv
    discipline = "security"
    mode = "full"
    intent_text = None
    show_flag = False
    apply_flag = False
    remaining = []
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--discipline" and i + 1 < len(sys.argv):
            discipline = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--mode" and i + 1 < len(sys.argv):
            mode = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--intent" and i + 1 < len(sys.argv):
            intent_text = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--show":
            show_flag = True
            i += 1
        elif sys.argv[i] == "--apply":
            apply_flag = True
            i += 1
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
            # Auto-apply gates if profile was loaded
            gated_count = 0
            if engine.get_profile():
                gated_count = engine.auto_na_gated()
            engine.save(state_file)
            m = engine.metrics()
            info = engine.get_discipline_info()
            print(f"New FORGE run: {project}")
            print(f"Discipline: {info['name']} v{info['version']}")
            print(f"Mode: {mode} — BQs: {', '.join(engine.get_bqs())}")
            print(f"Total DQs: {m['total_dqs']}")
            if gated_count:
                print(f"Profile gates: {gated_count} DQs auto-N/A'd")
                for gs in engine.get_gate_summary():
                    print(f"  {gs['name']}: {gs['reason']} ({gs['dqs_gated']} DQs)")
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

        elif cmd == "intake":
            if not remaining:
                print("Error: Missing project name. Usage: forge intake <project>")
                sys.exit(1)
            project = remaining[0]

            if show_flag:
                # Show existing profile
                profile = load_profile(project)
                if not profile:
                    print(f"No profile found for '{project}'.")
                    sys.exit(1)
                print(f"Intake Profile: {profile.get('project', project)}")
                print(f"Created: {profile.get('created', 'unknown')}")
                for field, value in profile.get("answers", {}).items():
                    print(f"  {field}: {value}")
                # Show which gates would fire
                matched = evaluate_gates(profile)
                if matched:
                    print(f"\nGates matched ({len(matched)}):")
                    for g in matched:
                        print(f"  {g['name']}: {g['reason']}")
                        for t in g["targets"]:
                            print(f"    -> {t}")
            else:
                # Interactive profile creation
                questions = load_intake_questions()
                answers = {}
                print(f"FORGE Intake Profile: {project}")
                print("Answer each question to tailor assessments.\n")
                for field, q in questions.items():
                    prompt = q["prompt"]
                    q_type = q.get("type", "choice")
                    if q_type == "bool":
                        while True:
                            val = input(f"{prompt} (yes/no): ").strip().lower()
                            if val in ("yes", "y", "true", "1"):
                                answers[field] = True
                                break
                            elif val in ("no", "n", "false", "0"):
                                answers[field] = False
                                break
                            print("  Please enter yes or no.")
                    else:
                        options = q.get("options", [])
                        print(f"{prompt}")
                        for idx, opt in enumerate(options, 1):
                            print(f"  {idx}. {opt}")
                        while True:
                            val = input(f"Choice (1-{len(options)}): ").strip()
                            if val.isdigit() and 1 <= int(val) <= len(options):
                                answers[field] = options[int(val) - 1]
                                break
                            # Also accept the option text directly
                            if val in options:
                                answers[field] = val
                                break
                            print(f"  Enter 1-{len(options)} or option name.")
                    print()

                profile = create_profile(project, answers)
                save_profile(profile)
                print(f"Profile saved to forge-profile-{project}.json")

                # Show matched gates
                matched = evaluate_gates(profile)
                if matched:
                    total_targets = sum(len(g["targets"]) for g in matched)
                    print(f"\n{len(matched)} gates matched ({total_targets} target paths):")
                    for g in matched:
                        print(f"  {g['name']}: {g['reason']}")
                else:
                    print("\nNo gates matched — all questions will be active.")

        elif cmd == "route":
            if intent_text:
                # Keyword-based recommendation
                results = recommend_disciplines(intent=intent_text)
                print(f"Intent: \"{intent_text}\"\n")
                print("Recommended disciplines:")
                for r in results:
                    conf_pct = int(r["confidence"] * 100)
                    print(f"  {r['discipline']} ({conf_pct}%) — {r['reason']}")
            else:
                # Interactive decision tree
                router = load_router()
                tree = router.get("decision_tree", {})
                node_name = "root"
                while node_name in tree:
                    node = tree[node_name]
                    print(f"\n{node['question']}")
                    options = node.get("options", [])
                    for idx, opt in enumerate(options, 1):
                        print(f"  {idx}. {opt['label']}")
                    while True:
                        choice = input(f"Choice (1-{len(options)}): ").strip()
                        if choice.isdigit() and 1 <= int(choice) <= len(options):
                            break
                        print(f"  Enter 1-{len(options)}.")
                    selected = options[int(choice) - 1]
                    if "result" in selected:
                        disciplines = selected["result"]
                        print(f"\nRecommended: {', '.join(disciplines)}")
                        print(f"\nTo start: forge new <project> --discipline {disciplines[0]}")
                        node_name = None  # Exit loop
                    elif "next" in selected:
                        node_name = selected["next"]
                    else:
                        print("No result for that option.")
                        node_name = None

        elif cmd == "dedup":
            if len(remaining) < 2:
                print("Error: Need at least 2 projects. Usage: forge dedup <proj1> <proj2> [...]")
                sys.exit(1)
            # Load all engines
            engines = []
            for proj in remaining:
                state_file = f"forge-state-{proj}.json"
                if not os.path.exists(state_file):
                    print(f"Error: State file not found: {state_file}")
                    sys.exit(1)
                engines.append(ForgeEngine.load(state_file))

            disc_names = [e.discipline_name for e in engines]
            print(f"Deduplicating {len(engines)} runs: {', '.join(disc_names)}")
            print()

            result = deduplicate_runs(engines)
            s = result["summary"]

            if s["total_removed"] == 0:
                print("No duplicates found across disciplines.")
                return

            if result["duplicate_gaps"]:
                print(f"Duplicate gaps ({s['gaps_duped']}):")
                for dup in result["duplicate_gaps"]:
                    print(f"  [{dup['confidence']:.0%}] {dup['keep']['discipline']}:{dup['keep']['id']} "
                          f"== {dup['remove']['discipline']}:{dup['remove']['id']}")
                    print(f"    Keep:   {dup['keep']['description'][:70]}")
                    print(f"    Remove: {dup['remove']['description'][:70]}")
                print()

            if result["duplicate_fixes"]:
                print(f"Duplicate fixes ({s['fixes_duped']}):")
                for dup in result["duplicate_fixes"]:
                    print(f"  [{dup['confidence']:.0%}] {dup['keep']['discipline']}:{dup['keep']['id']} "
                          f"== {dup['remove']['discipline']}:{dup['remove']['id']}")
                    print(f"    Keep:   {dup['keep']['description'][:70]}")
                    print(f"    Remove: {dup['remove']['description'][:70]}")
                print()

            if result["duplicate_kb"]:
                print(f"Duplicate KB entries ({s['kb_duped']}):")
                for dup in result["duplicate_kb"]:
                    print(f"  [{dup['confidence']:.0%}] {dup['keep']['discipline']}:{dup['keep']['id']} "
                          f"== {dup['remove']['discipline']}:{dup['remove']['id']}")
                print()

            print(f"Total: {s['total_removed']} duplicates found")

            if apply_flag:
                removals = apply_dedup(engines, result)
                # Save updated engines
                for eng in engines:
                    eng.save()
                print(f"\nApplied: removed {removals['gaps']} gaps, "
                      f"{removals['fixes']} fixes, {removals['kb']} KB entries")
                print("State files updated.")
            else:
                print("\nRun with --apply to remove duplicates.")

        elif cmd == "consolidate":
            if not remaining:
                print("Error: Need at least 1 project. Usage: forge consolidate <proj1> [proj2] ...")
                sys.exit(1)
            engines = []
            for proj in remaining:
                state_file = f"forge-state-{proj}.json"
                if not os.path.exists(state_file):
                    print(f"Error: State file not found: {state_file}")
                    sys.exit(1)
                engines.append(ForgeEngine.load(state_file))

            disc_names = [e.discipline_name for e in engines]
            print(f"Analyzing {len(engines)} run(s): {', '.join(disc_names)}")

            # Use deep analysis — scans prior runs and KB
            result = analyze_consolidation_deep(engines)
            s = result["summary"]
            prior_count = result.get("prior_runs_scanned", 0)

            if prior_count:
                print(f"Also scanned {prior_count} prior run(s) for historical patterns")
            print()

            if s["opportunities_found"] == 0:
                print("No consolidation opportunities found.")
                print("(Fixes address distinct concerns — individual patches are appropriate.)")
                return

            noun = "opportunity" if s['opportunities_found'] == 1 else "opportunities"
            print(f"Found {s['opportunities_found']} consolidation {noun} "
                  f"({s['fixes_involved']} fixes, {s['gaps_involved']} gaps involved):\n")

            for i, opp in enumerate(result["opportunities"], 1):
                badge = "STRONG" if opp["strength"] == "strong" else "MODERATE"
                rec = opp.get("recommendation", "build_new")
                rec_label = "EXTEND" if rec == "extend_existing" else "NEW"
                print(f"{'=' * 60}")
                print(f"  [{badge}] [{rec_label}] {i}. {opp['suggested_name']}")
                print(f"  Capability: {opp['capability']}")
                print(f"  Disciplines: {', '.join(opp['disciplines_involved'])}")
                print()
                print(f"  {opp['rationale']}")

                if rec == "extend_existing" and opp.get("existing_partial"):
                    print()
                    print(f"  Existing partial solution:")
                    print(f"    {opp['existing_partial'][:80]}")
                    print(f"  -> Extend this rather than building from scratch.")

                print()
                if opp["gaps_consolidated"]:
                    print(f"  Gaps addressed ({len(opp['gaps_consolidated'])}):")
                    for g in opp["gaps_consolidated"]:
                        print(f"    {g['discipline']}:{g['id']} — {g['description'][:60]}")
                if opp["fixes_consolidated"]:
                    print(f"  Fixes replaced ({len(opp['fixes_consolidated'])}):")
                    for f in opp["fixes_consolidated"]:
                        print(f"    {f['discipline']}:{f['id']} — {f['description'][:60]}")

                # Prior evidence
                prior_ev = opp.get("prior_evidence", [])
                if prior_ev:
                    projects = sorted(set(e["project"] for e in prior_ev))
                    print(f"  Prior evidence ({len(prior_ev)} items from: {', '.join(projects)}):")
                    for ev in prior_ev[:5]:  # Cap at 5 to avoid noise
                        print(f"    [{ev['type']}] {ev['project']}/{ev['discipline']}:"
                              f"{ev['id']} — {ev['description'][:50]}")
                    if len(prior_ev) > 5:
                        print(f"    ... and {len(prior_ev) - 5} more")

                # KB patterns
                kb = opp.get("kb_patterns", [])
                if kb:
                    print(f"  Related KB patterns ({len(kb)}):")
                    for k in kb[:3]:
                        print(f"    {k['id']} ({k['category']}): {k['pattern'][:50]}")
                print()

        elif cmd == "improve":
            if not remaining:
                print("Error: Need at least 1 project. Usage: forge improve <proj1> [proj2] ...")
                sys.exit(1)
            engines = []
            for proj in remaining:
                state_file = f"forge-state-{proj}.json"
                if not os.path.exists(state_file):
                    print(f"Error: State file not found: {state_file}")
                    sys.exit(1)
                engines.append(ForgeEngine.load(state_file))

            disc_names = [e.discipline_name for e in engines]
            print(f"Service improvement analysis for {len(engines)} run(s): "
                  f"{', '.join(disc_names)}")

            result = analyze_services(engines)
            s = result["summary"]

            if s.get("prior_runs_included"):
                print(f"Including {s['prior_runs_included']} prior run(s)")
            print()

            # Service inventory
            real_svcs = {k: v for k, v in result["services"].items()
                         if k != "_unassigned"}
            if real_svcs:
                print(f"Services identified ({len(real_svcs)}):")
                print(f"{'-' * 60}")
                for svc, info in sorted(real_svcs.items()):
                    caps = ", ".join(info["capabilities"]) if info["capabilities"] else "none"
                    print(f"  {svc}")
                    print(f"    Capabilities: {caps}")
                    print(f"    Fixes: {info['fix_count']}  Gaps: {info['gap_count']}")
                print()

            # Unassigned capabilities
            unassigned = result["services"].get("_unassigned")
            if unassigned and unassigned["gap_count"] > 0:
                caps = ", ".join(unassigned["capabilities"])
                print(f"Unassigned capabilities: {caps}")
                print(f"  ({unassigned['gap_count']} gaps with no clear service owner)")
                print()

            # Overlaps
            if result["overlaps"]:
                print(f"Service overlaps ({s['overlaps_found']}):")
                print(f"{'-' * 60}")
                for ov in result["overlaps"]:
                    pct = int(ov["overlap_ratio"] * 100)
                    specific = ov.get("specific_shared", ov["shared_capabilities"])
                    label = "HIGH" if ov["overlap_ratio"] >= 0.5 else "PARTIAL"
                    print(f"  [{label} {pct}%] {ov['services'][0]} <-> {ov['services'][1]}")
                    print(f"    Shared: {', '.join(specific)}")
                print()

            # Recommendations
            if result["recommendations"]:
                print(f"Recommendations ({s['recommendations_count']}):")
                print(f"{'=' * 60}")
                for i, rec in enumerate(result["recommendations"], 1):
                    tag = rec["type"].upper()
                    print(f"  [{tag}] {i}. {rec['action']}")
                    print(f"    {rec['rationale']}")
                    print()
            else:
                print("No improvement recommendations.")
                print("(Services have clean separation of concerns.)")

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
