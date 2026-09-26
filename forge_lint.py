#!/usr/bin/env python3
"""forge_lint.py — Static validation for FORGE's YAML/JSON data files.

Checks, purely offline (no network, no engine.py execution):
  - Discipline YAML schema (required fields on the file / BQ / TQ / KB levels)
  - Duplicate mapping keys within a single YAML file (PyYAML silently keeps
    the *last* value on a duplicate key, so this needs a dedicated loader)
  - Duplicate DQ text within the same TQ
  - triage_presets referencing BQs that exist in the same discipline
  - gates.yaml conditions referencing fields that exist in intake.yaml
  - gates.yaml targets referencing disciplines/BQs/TQs/DQ-indexes that exist
  - router.yaml intent_signals / decision_tree referencing real disciplines
    and real decision_tree nodes
  - forge-profile-*.json matching the schema engine.create_profile() writes,
    and answers referencing real intake fields with valid values

Run: python3 forge_lint.py [--disciplines-dir DIR] [--root DIR]
Exit code is non-zero if any error-level finding is present.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass

import yaml

TARGET_RE = re.compile(r"^([a-z0-9-]+):(BQ-\d+(?:\.\d+)?)(?:\.(TQ-[\d.]+)(?:\[(\d+)\])?)?$")
CONDITION_CLAUSE_RE = re.compile(r"^(\S+)\s+(==|!=|in)\s+(.*)$")


@dataclass
class Finding:
    severity: str  # "error" or "warning"
    source: str
    message: str

    def __str__(self):
        return f"[{self.severity.upper()}] {self.source}: {self.message}"


class _DupKeyLoader(yaml.SafeLoader):
    """SafeLoader that records duplicate mapping keys instead of silently
    overwriting them (PyYAML's default behavior keeps only the last one)."""


def _construct_mapping_check_dups(loader, node, dup_sink):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=False)
        if key in mapping:
            dup_sink.append(key)
        value = loader.construct_object(value_node, deep=False)
        mapping[key] = value
    return mapping


def load_yaml_checking_dups(path: str):
    """Load a YAML file, returning (data, [duplicate_key, ...])."""
    dups = []
    loader_cls = type("_DupKeyLoader", (yaml.SafeLoader,), {})
    loader_cls.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        lambda loader, node: _construct_mapping_check_dups(loader, node, dups),
    )
    with open(path, encoding="utf-8") as f:
        data = yaml.load(f, Loader=loader_cls)
    return data, dups


def _disciplines_dir(root: str) -> str:
    return os.path.join(root, "disciplines")


def _is_discipline_doc(data) -> bool:
    return isinstance(data, dict) and "id" in data and "questions" in data


def lint_discipline_file(path: str, data: dict, dups: list) -> list[Finding]:
    findings = []
    src = os.path.basename(path)

    for key in dups:
        findings.append(Finding("error", src, f"Duplicate key in YAML mapping: '{key}'"))

    for field in ("name", "id", "version", "questions"):
        if field not in data:
            findings.append(Finding("error", src, f"Missing required top-level field '{field}'"))
    if "id" in data:
        stem = os.path.splitext(os.path.basename(path))[0]
        if data["id"] != stem:
            findings.append(
                Finding("error", src, f"id '{data['id']}' does not match filename '{stem}.yaml'")
            )

    questions = data.get("questions") or {}
    if not isinstance(questions, dict) or not questions:
        findings.append(Finding("error", src, "'questions' must be a non-empty mapping of BQ id -> BQ"))
        return findings

    bq_ids = set(questions.keys())

    for bq_id, bq in questions.items():
        if not isinstance(bq, dict):
            findings.append(Finding("error", src, f"{bq_id}: expected a mapping"))
            continue
        if "name" not in bq:
            findings.append(Finding("error", src, f"{bq_id}: missing 'name'"))
        if "tqs" not in bq or not isinstance(bq.get("tqs"), dict) or not bq["tqs"]:
            findings.append(Finding("error", src, f"{bq_id}: missing or empty 'tqs'"))
            continue
        for tq_id, tq in bq["tqs"].items():
            if not isinstance(tq, dict):
                findings.append(Finding("error", src, f"{bq_id}.{tq_id}: expected a mapping"))
                continue
            if "name" not in tq:
                findings.append(Finding("error", src, f"{bq_id}.{tq_id}: missing 'name'"))
            dqs = tq.get("dqs")
            if not isinstance(dqs, list) or not dqs:
                findings.append(Finding("error", src, f"{bq_id}.{tq_id}: missing or empty 'dqs'"))
                continue
            seen = {}
            for i, dq in enumerate(dqs):
                if not isinstance(dq, str) or not dq.strip():
                    findings.append(Finding("error", src, f"{bq_id}.{tq_id}[{i}]: DQ must be a non-empty string"))
                    continue
                if dq in seen:
                    findings.append(
                        Finding(
                            "error", src,
                            f"{bq_id}.{tq_id}: duplicate DQ text (indexes {seen[dq]} and {i}): {dq[:70]!r}",
                        )
                    )
                else:
                    seen[dq] = i

    for preset, bq_list in (data.get("triage_presets") or {}).items():
        for bq_id in bq_list:
            if bq_id not in bq_ids:
                findings.append(
                    Finding("error", src, f"triage_presets.{preset}: references unknown BQ '{bq_id}'")
                )

    if "kb" in data:
        kb = data["kb"] or {}
        if not isinstance(kb, dict):
            findings.append(Finding("error", src, "'kb' must be a mapping of KB id -> entry"))
        else:
            for kb_id, entry in kb.items():
                if not isinstance(entry, dict):
                    findings.append(Finding("error", src, f"kb.{kb_id}: expected a mapping"))
                    continue
                for field in ("title", "body"):
                    if field not in entry:
                        findings.append(Finding("error", src, f"kb.{kb_id}: missing '{field}'"))

    return findings


def lint_intake(path: str, data: dict, dups: list) -> tuple[list[Finding], dict]:
    findings = []
    src = os.path.basename(path)
    for key in dups:
        findings.append(Finding("error", src, f"Duplicate key in YAML mapping: '{key}'"))

    questions = data.get("questions") or {}
    if not isinstance(questions, dict) or not questions:
        findings.append(Finding("error", src, "'questions' must be a non-empty mapping"))
        return findings, {}

    for field_id, q in questions.items():
        if not isinstance(q, dict):
            findings.append(Finding("error", src, f"{field_id}: expected a mapping"))
            continue
        if "prompt" not in q:
            findings.append(Finding("error", src, f"{field_id}: missing 'prompt'"))
        if "type" not in q:
            findings.append(Finding("error", src, f"{field_id}: missing 'type'"))
        elif q["type"] not in ("bool", "choice"):
            findings.append(Finding("error", src, f"{field_id}: unknown type '{q['type']}'"))
        elif q["type"] == "choice" and not q.get("options"):
            findings.append(Finding("error", src, f"{field_id}: choice field missing 'options'"))

    return findings, questions


def lint_gates(path: str, data: dict, dups: list, disciplines: dict, intake_fields: dict) -> list[Finding]:
    findings = []
    src = os.path.basename(path)
    for key in dups:
        findings.append(Finding("error", src, f"Duplicate key in YAML mapping: '{key}'"))

    gates = data.get("gates") or {}
    if not isinstance(gates, dict) or not gates:
        findings.append(Finding("error", src, "'gates' must be a non-empty mapping"))
        return findings

    for gate_name, gate in gates.items():
        if not isinstance(gate, dict):
            findings.append(Finding("error", src, f"gates.{gate_name}: expected a mapping"))
            continue
        for field in ("condition", "reason", "targets"):
            if field not in gate:
                findings.append(Finding("error", src, f"gates.{gate_name}: missing '{field}'"))
        if "reason" in gate and not str(gate["reason"]).strip():
            findings.append(Finding("error", src, f"gates.{gate_name}: 'reason' is empty"))

        condition = gate.get("condition", "")
        for clause in re.split(r"\s+(?:and|or)\s+", condition.strip()):
            m = CONDITION_CLAUSE_RE.match(clause.strip())
            if not m:
                findings.append(Finding("error", src, f"gates.{gate_name}: unparseable condition clause '{clause}'"))
                continue
            field = m.group(1)
            if field not in intake_fields:
                findings.append(
                    Finding("error", src, f"gates.{gate_name}: condition references unknown intake field '{field}'")
                )

        for target in gate.get("targets") or []:
            m = TARGET_RE.match(target)
            if not m:
                findings.append(Finding("error", src, f"gates.{gate_name}: malformed target '{target}'"))
                continue
            disc_id, bq_id, tq_id, idx = m.groups()
            if disc_id not in disciplines:
                findings.append(Finding("error", src, f"gates.{gate_name}: target '{target}' references unknown discipline '{disc_id}'"))
                continue
            disc = disciplines[disc_id]
            bqs = disc.get("questions", {})
            if bq_id not in bqs:
                findings.append(Finding("error", src, f"gates.{gate_name}: target '{target}' references unknown BQ '{bq_id}' in '{disc_id}'"))
                continue
            if tq_id:
                tqs = bqs[bq_id].get("tqs", {})
                if tq_id not in tqs:
                    findings.append(Finding("error", src, f"gates.{gate_name}: target '{target}' references unknown TQ '{tq_id}' in '{disc_id}:{bq_id}'"))
                    continue
                if idx is not None:
                    dq_count = len(tqs[tq_id].get("dqs", []))
                    if int(idx) >= dq_count:
                        findings.append(
                            Finding(
                                "error", src,
                                f"gates.{gate_name}: target '{target}' DQ index {idx} out of range (only {dq_count} DQs)",
                            )
                        )
    return findings


def lint_router(path: str, data: dict, dups: list, disciplines: dict) -> list[Finding]:
    findings = []
    src = os.path.basename(path)
    for key in dups:
        findings.append(Finding("error", src, f"Duplicate key in YAML mapping: '{key}'"))

    for name, sig in (data.get("intent_signals") or {}).items():
        if not isinstance(sig, dict):
            findings.append(Finding("error", src, f"intent_signals.{name}: expected a mapping"))
            continue
        primary = sig.get("primary")
        if primary is None:
            findings.append(Finding("error", src, f"intent_signals.{name}: missing 'primary'"))
        elif primary not in disciplines:
            findings.append(Finding("error", src, f"intent_signals.{name}: unknown discipline '{primary}' in 'primary'"))
        for also in sig.get("also", []) or []:
            if also not in disciplines:
                findings.append(Finding("error", src, f"intent_signals.{name}: unknown discipline '{also}' in 'also'"))

    tree = data.get("decision_tree") or {}
    node_names = set(tree.keys())
    for node_name, node in tree.items():
        for opt in node.get("options", []) or []:
            for r in opt.get("result", []) or []:
                if r not in disciplines:
                    findings.append(Finding("error", src, f"decision_tree.{node_name}: unknown discipline '{r}' in 'result'"))
            if "next" in opt and opt["next"] not in node_names:
                findings.append(Finding("error", src, f"decision_tree.{node_name}: 'next' references unknown node '{opt['next']}'"))
    return findings


def lint_profile(path: str, intake_fields: dict) -> list[Finding]:
    findings = []
    src = os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return [Finding("error", src, f"invalid JSON: {e}")]

    for field in ("version", "project", "created", "updated", "answers"):
        if field not in data:
            findings.append(Finding("error", src, f"missing required field '{field}'"))
    answers = data.get("answers")
    if not isinstance(answers, dict):
        findings.append(Finding("error", src, "'answers' must be a mapping"))
        return findings

    for field, value in answers.items():
        if field not in intake_fields:
            findings.append(Finding("error", src, f"answers references unknown intake field '{field}'"))
            continue
        q = intake_fields[field]
        if q.get("type") == "bool":
            if value is not None and not isinstance(value, bool):
                findings.append(Finding("error", src, f"answers.{field}: expected bool, got {value!r}"))
        elif q.get("type") == "choice":
            options = q.get("options") or []
            if value is not None and value not in options:
                findings.append(Finding("error", src, f"answers.{field}: value {value!r} not in options {options}"))
    return findings


def run_lint(root: str) -> list[Finding]:
    findings: list[Finding] = []
    disc_dir = _disciplines_dir(root)

    disciplines = {}
    other_docs = {}
    for path in sorted(glob.glob(os.path.join(disc_dir, "*.yaml"))):
        try:
            data, dups = load_yaml_checking_dups(path)
        except yaml.YAMLError as e:
            findings.append(Finding("error", os.path.basename(path), f"YAML parse error: {e}"))
            continue
        if _is_discipline_doc(data):
            disciplines[data["id"]] = data
            findings.extend(lint_discipline_file(path, data, dups))
        else:
            other_docs[os.path.basename(path)] = (path, data, dups)

    intake_fields = {}
    if "intake.yaml" in other_docs:
        path, data, dups = other_docs["intake.yaml"]
        intake_findings, intake_fields = lint_intake(path, data or {}, dups)
        findings.extend(intake_findings)
    else:
        findings.append(Finding("error", "disciplines/", "intake.yaml not found"))

    if "gates.yaml" in other_docs:
        path, data, dups = other_docs["gates.yaml"]
        findings.extend(lint_gates(path, data or {}, dups, disciplines, intake_fields))
    else:
        findings.append(Finding("error", "disciplines/", "gates.yaml not found"))

    if "router.yaml" in other_docs:
        path, data, dups = other_docs["router.yaml"]
        findings.extend(lint_router(path, data or {}, dups, disciplines))
    else:
        findings.append(Finding("error", "disciplines/", "router.yaml not found"))

    for path in sorted(glob.glob(os.path.join(root, "forge-profile-*.json"))):
        findings.extend(lint_profile(path, intake_fields))

    return findings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)))
    args = parser.parse_args(argv)

    findings = run_lint(args.root)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for f in findings:
        print(f)

    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
