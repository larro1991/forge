#!/usr/bin/env python3
"""Tests for FORGE engine.py — v2.0 multi-discipline engine."""

import json
import os
import tempfile
import unittest

from engine import (
    BASE_VALID_STATES,
    FRAMEWORK,
    TRIAGE_PRESETS,
    VALID_STATES,
    VERSION,
    ForgeEngine,
    count_discipline_dqs,
    count_framework_dqs,
    list_disciplines,
    load_discipline,
    validate_framework_sync,
)


class TestDisciplineLoader(unittest.TestCase):
    """Test discipline discovery and loading."""

    def test_list_disciplines_includes_security(self):
        available = list_disciplines()
        self.assertIn("security", available)

    def test_list_disciplines_includes_troubleshooting(self):
        available = list_disciplines()
        self.assertIn("troubleshooting", available)

    def test_load_security_discipline(self):
        disc = load_discipline("security")
        self.assertEqual(disc["id"], "security")
        self.assertEqual(disc["name"], "Security Assessment")
        self.assertIn("questions", disc)

    def test_load_troubleshooting_discipline(self):
        disc = load_discipline("troubleshooting")
        self.assertEqual(disc["id"], "troubleshooting")
        self.assertIn("questions", disc)

    def test_load_nonexistent_discipline(self):
        with self.assertRaises(FileNotFoundError):
            load_discipline("nonexistent-xyz")

    def test_security_has_269_dqs(self):
        disc = load_discipline("security")
        self.assertEqual(count_discipline_dqs(disc), 269)

    def test_troubleshooting_has_8_bqs(self):
        disc = load_discipline("troubleshooting")
        self.assertEqual(len(disc["questions"]), 8)

    def test_troubleshooting_dqs_positive(self):
        disc = load_discipline("troubleshooting")
        self.assertGreater(count_discipline_dqs(disc), 0)

    def test_discipline_has_required_fields(self):
        for name in list_disciplines():
            disc = load_discipline(name)
            self.assertIn("name", disc, f"{name} missing 'name'")
            self.assertIn("id", disc, f"{name} missing 'id'")
            self.assertIn("version", disc, f"{name} missing 'version'")
            self.assertIn("questions", disc, f"{name} missing 'questions'")

    def test_every_discipline_has_valid_structure(self):
        for name in list_disciplines():
            disc = load_discipline(name)
            for bq_id, bq in disc["questions"].items():
                self.assertIn("name", bq, f"{name}:{bq_id} missing 'name'")
                self.assertIn("tqs", bq, f"{name}:{bq_id} missing 'tqs'")
                for tq_id, tq in bq["tqs"].items():
                    self.assertIn("name", tq, f"{name}:{tq_id} missing 'name'")
                    self.assertIn("dqs", tq, f"{name}:{tq_id} missing 'dqs'")
                    self.assertGreater(
                        len(tq["dqs"]), 0, f"{name}:{tq_id} has no DQs"
                    )


class TestBackwardCompat(unittest.TestCase):
    """Test that module-level FRAMEWORK, TRIAGE_PRESETS, etc. still work."""

    def test_framework_has_13_bqs(self):
        self.assertEqual(len(FRAMEWORK), 13)

    def test_framework_contains_bq01(self):
        self.assertIn("BQ-01", FRAMEWORK)

    def test_framework_iterate(self):
        bq_ids = list(FRAMEWORK.keys())
        self.assertEqual(len(bq_ids), 13)
        self.assertEqual(bq_ids[0], "BQ-01")

    def test_framework_get(self):
        bq = FRAMEWORK.get("BQ-01")
        self.assertIsNotNone(bq)
        self.assertEqual(bq["name"], "Purpose & Scope")

    def test_triage_presets_has_security(self):
        self.assertIn("security", TRIAGE_PRESETS)

    def test_triage_presets_full(self):
        full = TRIAGE_PRESETS["full"]
        self.assertEqual(len(full), 13)

    def test_valid_states_has_improve(self):
        self.assertIn("IMPROVE", VALID_STATES)

    def test_count_framework_dqs(self):
        self.assertEqual(count_framework_dqs(), 269)

    def test_framework_sync_with_markdown(self):
        result = validate_framework_sync()
        self.assertTrue(result["ok"], result["details"])


class TestForgeEngineSecurityDefault(unittest.TestCase):
    """Test ForgeEngine with default (security) discipline."""

    def setUp(self):
        self.engine = ForgeEngine("test-project", mode="full")

    def test_init_defaults_to_security(self):
        self.assertEqual(self.engine.discipline_name, "security")
        self.assertEqual(self.engine.project, "test-project")
        self.assertEqual(self.engine.mode, "full")
        self.assertEqual(len(self.engine.get_bqs()), 13)

    def test_triage_mode(self):
        engine = ForgeEngine("test", mode="security")
        self.assertEqual(engine.get_bqs(), ["BQ-04", "BQ-05", "BQ-10", "BQ-13"])

    def test_total_dqs(self):
        self.assertEqual(self.engine.total_dqs(), 269)

    def test_answer_valid_states(self):
        for state in BASE_VALID_STATES:
            self.engine.answer("BQ-01", "TQ-01.1", 0, state=state, answer="test")

    def test_answer_invalid_state(self):
        with self.assertRaises(ValueError):
            self.engine.answer("BQ-01", "TQ-01.1", 0, state="INVALID")

    def test_answer_blocked_auto_tracks(self):
        self.engine.answer("BQ-01", "TQ-01.1", 0, state="BLOCKED", answer="No access")
        self.assertEqual(len(self.engine.blocked), 1)
        self.assertEqual(self.engine.blocked[0]["id"], "B-001")

    def test_answer_improve_auto_tracks(self):
        self.engine.answer(
            "BQ-01", "TQ-01.1", 0, state="IMPROVE",
            answer="Works but could use an ORM"
        )
        self.assertEqual(len(self.engine.improvements), 1)
        self.assertEqual(self.engine.improvements[0]["id"], "I-001")
        self.assertIn("ORM", self.engine.improvements[0]["suggestion"])

    def test_add_gap(self):
        gid = self.engine.add_gap("BQ-01", "TQ-01.1", "Missing docs", severity="medium")
        self.assertEqual(gid, "G-001")
        self.assertEqual(len(self.engine.gaps), 1)

    def test_add_fix(self):
        fid = self.engine.add_fix("engine.py", "Added error handling", ["G-001"])
        self.assertEqual(fid, "F-001")

    def test_accept_risk(self):
        self.engine.accept_risk("BQ-04", "No MFA", "Single user system")
        self.assertEqual(len(self.engine.accepted), 1)

    def test_add_kb_entry(self):
        self.engine.add_kb_entry("BQ-10", "Multi-file project", "Duplicated secrets", "Key leak")
        self.assertEqual(len(self.engine.kb_entries), 1)
        self.assertEqual(self.engine.kb_entries[0]["discipline"], "security")

    def test_defer(self):
        self.engine.defer("No arch diagram", "BQ-02", "low", "Not needed yet")
        self.assertEqual(len(self.engine.deferred), 1)

    def test_metrics(self):
        self.engine.answer("BQ-01", "TQ-01.1", 0, state="PASS", answer="ok")
        self.engine.answer("BQ-01", "TQ-01.1", 1, state="GAP", answer="missing")
        self.engine.answer("BQ-01", "TQ-01.1", 2, state="IMPROVE", answer="could be better")
        m = self.engine.metrics()
        self.assertEqual(m["dqs_answered"], 3)
        self.assertEqual(m["states"]["PASS"], 1)
        self.assertEqual(m["states"]["GAP"], 1)
        self.assertEqual(m["states"]["IMPROVE"], 1)
        self.assertEqual(m["discipline"], "security")

    def test_verify_empty_run(self):
        v = self.engine.verify()
        self.assertIn("overall", v)
        self.assertFalse(v["VP-04"]["checks"]["all_bqs_addressed"])

    def test_report_generates_markdown(self):
        self.engine.answer("BQ-01", "TQ-01.1", 0, state="PASS", answer="ok")
        report = self.engine.report()
        self.assertIn("# FORGE Run: test-project", report)
        self.assertIn("## Run Metrics", report)
        self.assertIn(VERSION, report)
        self.assertIn("Security Assessment", report)

    def test_report_includes_improvements(self):
        self.engine.answer(
            "BQ-01", "TQ-01.1", 0, state="IMPROVE",
            answer="Could use structured logging"
        )
        report = self.engine.report()
        self.assertIn("Improvement Opportunities", report)

    def test_discipline_info(self):
        info = self.engine.get_discipline_info()
        self.assertEqual(info["id"], "security")
        self.assertEqual(info["total_dqs"], 269)
        self.assertIn("full", info["triage_presets"])


class TestForgeEngineTroubleshooting(unittest.TestCase):
    """Test ForgeEngine with the troubleshooting discipline."""

    def setUp(self):
        self.engine = ForgeEngine(
            "outage-001", discipline="troubleshooting", mode="full"
        )

    def test_init(self):
        self.assertEqual(self.engine.discipline_name, "troubleshooting")
        self.assertEqual(len(self.engine.get_bqs()), 8)

    def test_triage_mode(self):
        engine = ForgeEngine(
            "outage", discipline="troubleshooting", mode="quick-triage"
        )
        self.assertEqual(engine.get_bqs(), ["BQ-01", "BQ-02", "BQ-05"])

    def test_total_dqs(self):
        self.assertGreater(self.engine.total_dqs(), 0)

    def test_answer_and_metrics(self):
        self.engine.answer("BQ-01", "TQ-01.1", 0, state="PASS", answer="API 500s")
        m = self.engine.metrics()
        self.assertEqual(m["dqs_answered"], 1)
        self.assertEqual(m["discipline"], "troubleshooting")

    def test_discipline_info(self):
        info = self.engine.get_discipline_info()
        self.assertEqual(info["id"], "troubleshooting")
        self.assertEqual(info["total_bqs"], 8)

    def test_report_shows_discipline(self):
        self.engine.answer("BQ-01", "TQ-01.1", 0, state="PASS", answer="ok")
        report = self.engine.report()
        self.assertIn("Troubleshooting", report)


class TestPersistence(unittest.TestCase):
    """Test save/load including discipline field."""

    def test_save_and_load_security(self):
        engine = ForgeEngine("persist-test", mode="security")
        engine.answer("BQ-04", "TQ-04.1", 0, state="PASS", answer="JWT auth")
        engine.add_gap("BQ-05", "TQ-05.1", "SQL injection risk", severity="high")
        engine.add_kb_entry("BQ-10", "trigger", "pattern", "impact")
        engine.answer("BQ-04", "TQ-04.1", 1, state="IMPROVE", answer="Could add MFA")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            engine.save(path)
            loaded = ForgeEngine.load(path)

            self.assertEqual(loaded.project, "persist-test")
            self.assertEqual(loaded.discipline_name, "security")
            self.assertEqual(loaded.mode, "security")
            self.assertEqual(len(loaded.gaps), 1)
            self.assertEqual(len(loaded.kb_entries), 1)
            self.assertEqual(len(loaded.improvements), 1)
            self.assertEqual(
                loaded.answers["BQ-04"]["TQ-04.1"]["0"]["state"], "PASS"
            )
        finally:
            os.unlink(path)

    def test_save_and_load_troubleshooting(self):
        engine = ForgeEngine(
            "outage-persist", discipline="troubleshooting", mode="full"
        )
        engine.answer("BQ-01", "TQ-01.1", 0, state="PASS", answer="API 500s")

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            engine.save(path)
            loaded = ForgeEngine.load(path)

            self.assertEqual(loaded.discipline_name, "troubleshooting")
            self.assertEqual(len(loaded.get_bqs()), 8)
        finally:
            os.unlink(path)

    def test_load_v1_state_defaults_to_security(self):
        """v1.x state files have no 'discipline' field — should default to security."""
        state = {
            "version": "1.2.1",
            "project": "legacy",
            "mode": "full",
            "start_time": "2026-03-21T10:00:00",
            "bqs_to_run": ["BQ-01"],
            "answers": {},
            "gaps": [],
            "fixes": [],
            "accepted": [],
            "blocked": [],
            "kb_entries": [],
            "deferred": [],
        }
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            json.dump(state, f)
            path = f.name

        try:
            loaded = ForgeEngine.load(path)
            self.assertEqual(loaded.discipline_name, "security")
        finally:
            os.unlink(path)

    def test_load_nonexistent(self):
        with self.assertRaises(FileNotFoundError):
            ForgeEngine.load("nonexistent.json")

    def test_load_corrupt(self):
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            f.write("not valid json{{{")
            path = f.name
        try:
            with self.assertRaises(RuntimeError):
                ForgeEngine.load(path)
        finally:
            os.unlink(path)

    def test_load_missing_fields(self):
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            json.dump({"project": "test"}, f)
            path = f.name
        try:
            with self.assertRaises(RuntimeError):
                ForgeEngine.load(path)
        finally:
            os.unlink(path)


class TestVerification(unittest.TestCase):
    """Test VP checks do real validation."""

    def test_vp02_catches_invalid_gap_refs(self):
        engine = ForgeEngine("vp-test")
        engine.add_gap("BQ-01", "TQ-01.1", "test gap")
        engine.add_fix("test.py", "fix", ["G-999"])
        v = engine.verify()
        self.assertFalse(v["VP-02"]["checks"]["fix_gap_refs_valid"])

    def test_vp02_passes_valid_refs(self):
        engine = ForgeEngine("vp-test")
        gid = engine.add_gap("BQ-01", "TQ-01.1", "test gap")
        engine.add_fix("test.py", "fix", [gid])
        v = engine.verify()
        self.assertTrue(v["VP-02"]["checks"]["fix_gap_refs_valid"])

    def test_vp03_flags_suspicious_fixes(self):
        engine = ForgeEngine("vp-test")
        engine.add_fix("auth.py", "disable authentication for speed", ["G-001"])
        v = engine.verify()
        self.assertFalse(v["VP-03"]["checks"]["no_suspicious_fix_patterns"])


if __name__ == "__main__":
    unittest.main()
