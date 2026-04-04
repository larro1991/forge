#!/usr/bin/env python3
"""Tests for FORGE Intake Profile System and Discipline Router."""

import json
import os
import tempfile
import unittest

from engine import (
    ForgeEngine,
    _evaluate_condition,
    _extract_capabilities,
    _normalize_service_name,
    _similarity_score,
    analyze_consolidation,
    analyze_consolidation_deep,
    analyze_services,
    apply_dedup,
    create_profile,
    deduplicate_runs,
    evaluate_gates,
    load_gates,
    load_intake_questions,
    load_profile,
    load_router,
    recommend_disciplines,
    save_profile,
)


class TestIntakeQuestions(unittest.TestCase):
    """Test intake question loading."""

    def test_load_questions(self):
        questions = load_intake_questions()
        self.assertIsInstance(questions, dict)
        self.assertGreater(len(questions), 0)

    def test_expected_fields_present(self):
        questions = load_intake_questions()
        expected = [
            "environment", "users", "data_sensitivity", "architecture",
            "has_auth", "has_ai_ml", "has_database", "has_external_apis",
        ]
        for field in expected:
            self.assertIn(field, questions, f"Missing intake field: {field}")

    def test_each_question_has_prompt(self):
        questions = load_intake_questions()
        for field, q in questions.items():
            self.assertIn("prompt", q, f"{field} missing prompt")
            self.assertIn("type", q, f"{field} missing type")

    def test_bool_questions(self):
        questions = load_intake_questions()
        bool_fields = [f for f, q in questions.items() if q["type"] == "bool"]
        self.assertGreater(len(bool_fields), 0)
        for field in bool_fields:
            self.assertNotIn("options", questions[field])

    def test_choice_questions_have_options(self):
        questions = load_intake_questions()
        for field, q in questions.items():
            if q["type"] == "choice":
                self.assertIn("options", q, f"{field} missing options")
                self.assertGreater(len(q["options"]), 1)


class TestProfileCRUD(unittest.TestCase):
    """Test profile creation, saving, and loading."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.answers = {
            "environment": "personal-homelab",
            "users": "single-user",
            "data_sensitivity": "none",
            "architecture": "monolith",
            "has_auth": False,
            "has_ai_ml": False,
            "has_database": True,
            "has_external_apis": False,
        }

    def tearDown(self):
        # Clean up temp files
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_create_profile(self):
        profile = create_profile("test-proj", self.answers)
        self.assertEqual(profile["project"], "test-proj")
        self.assertEqual(profile["answers"], self.answers)
        self.assertIn("created", profile)

    def test_save_and_load_profile(self):
        profile = create_profile("test-proj", self.answers)
        path = os.path.join(self.tmpdir, "forge-profile-test-proj.json")
        save_profile(profile, path=path)
        self.assertTrue(os.path.exists(path))

        loaded = load_profile("test-proj", path=path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["project"], "test-proj")
        self.assertEqual(loaded["answers"], self.answers)

    def test_load_nonexistent_profile(self):
        result = load_profile("nonexistent-xyz-project")
        self.assertIsNone(result)

    def test_create_profile_with_partial_answers(self):
        partial = {"environment": "personal-homelab", "has_auth": True}
        profile = create_profile("partial-proj", partial)
        self.assertEqual(profile["answers"], partial)


class TestConditionEvaluator(unittest.TestCase):
    """Test the safe condition evaluator."""

    def setUp(self):
        self.answers = {
            "environment": "personal-homelab",
            "users": "single-user",
            "data_sensitivity": "none",
            "architecture": "monolith",
            "has_auth": False,
            "has_ai_ml": False,
            "has_database": True,
            "has_external_apis": False,
        }

    def test_equals_string(self):
        self.assertTrue(_evaluate_condition("environment == personal-homelab", self.answers))
        self.assertFalse(_evaluate_condition("environment == production-saas", self.answers))

    def test_equals_bool_false(self):
        self.assertTrue(_evaluate_condition("has_ai_ml == false", self.answers))
        self.assertFalse(_evaluate_condition("has_ai_ml == true", self.answers))

    def test_equals_bool_true(self):
        self.assertTrue(_evaluate_condition("has_database == true", self.answers))
        self.assertFalse(_evaluate_condition("has_database == false", self.answers))

    def test_not_equals(self):
        self.assertTrue(_evaluate_condition("environment != production-saas", self.answers))
        self.assertFalse(_evaluate_condition("environment != personal-homelab", self.answers))

    def test_in_list(self):
        self.assertTrue(_evaluate_condition("data_sensitivity in [none, internal]", self.answers))
        self.assertFalse(_evaluate_condition("data_sensitivity in [pii, regulated]", self.answers))

    def test_and_connector(self):
        self.assertTrue(_evaluate_condition(
            "users == single-user and environment == personal-homelab",
            self.answers
        ))
        self.assertFalse(_evaluate_condition(
            "users == single-user and environment == production-saas",
            self.answers
        ))

    def test_or_connector(self):
        self.assertTrue(_evaluate_condition(
            "environment == production-saas or has_ai_ml == false",
            self.answers
        ))
        self.assertFalse(_evaluate_condition(
            "environment == production-saas or has_ai_ml == true",
            self.answers
        ))

    def test_missing_field(self):
        self.assertFalse(_evaluate_condition("nonexistent == true", self.answers))

    def test_in_list_single_value(self):
        self.assertTrue(_evaluate_condition("architecture in [monolith]", self.answers))

    def test_invalid_syntax_raises(self):
        with self.assertRaises(ValueError):
            _evaluate_condition("just_a_word", self.answers)
        with self.assertRaises(ValueError):
            _evaluate_condition("field > value", self.answers)

    def test_empty_condition_raises(self):
        """Empty string condition should raise an error (no valid clause)."""
        with self.assertRaises(Exception):
            _evaluate_condition("", self.answers)

    def test_condition_with_all_connectives(self):
        """Test 'a == x and b == y or c == z' evaluates left-to-right."""
        # True and True or (irrelevant) => True and True = True, True or anything = True
        self.assertTrue(_evaluate_condition(
            "environment == personal-homelab and users == single-user or has_ai_ml == true",
            self.answers,
        ))
        # False and True or True => False, then or True => True
        self.assertTrue(_evaluate_condition(
            "environment == production-saas and users == single-user or has_database == true",
            self.answers,
        ))
        # True and False or False => False, then or False => False
        self.assertFalse(_evaluate_condition(
            "environment == personal-homelab and has_ai_ml == true or has_auth == true",
            self.answers,
        ))


class TestGateSystem(unittest.TestCase):
    """Test gate loading and evaluation."""

    def setUp(self):
        self.homelab_profile = {
            "project": "test",
            "answers": {
                "environment": "personal-homelab",
                "users": "single-user",
                "data_sensitivity": "none",
                "architecture": "monolith",
                "has_auth": False,
                "has_ai_ml": False,
                "has_database": True,
                "has_external_apis": False,
            },
        }

    def test_load_gates(self):
        gates = load_gates()
        self.assertIn("gates", gates)
        self.assertGreater(len(gates["gates"]), 0)

    def test_expected_gates_exist(self):
        gates = load_gates()
        expected = ["no_ai_ml", "no_auth", "no_compliance", "single_user",
                     "no_database", "simple_architecture", "no_external_apis"]
        for name in expected:
            self.assertIn(name, gates["gates"], f"Missing gate: {name}")

    def test_homelab_gates_fire(self):
        matched = evaluate_gates(self.homelab_profile)
        names = [g["name"] for g in matched]
        # Homelab with no auth, no AI, no external APIs, simple arch should match
        self.assertIn("no_ai_ml", names)
        self.assertIn("no_auth", names)
        self.assertIn("no_compliance", names)
        self.assertIn("single_user", names)
        self.assertIn("simple_architecture", names)
        self.assertIn("no_external_apis", names)

    def test_no_database_gate_does_not_fire_when_has_database(self):
        matched = evaluate_gates(self.homelab_profile)
        names = [g["name"] for g in matched]
        self.assertNotIn("no_database", names)  # has_database is True

    def test_production_profile_fewer_gates(self):
        prod_profile = {
            "project": "prod",
            "answers": {
                "environment": "production-saas",
                "users": "public",
                "data_sensitivity": "regulated",
                "architecture": "distributed",
                "has_auth": True,
                "has_ai_ml": True,
                "has_database": True,
                "has_external_apis": True,
            },
        }
        matched = evaluate_gates(prod_profile)
        # Production SaaS with everything enabled — no gates should fire
        self.assertEqual(len(matched), 0)

    def test_discipline_filtering(self):
        matched_all = evaluate_gates(self.homelab_profile)
        matched_sec = evaluate_gates(self.homelab_profile, discipline="security")
        # Security-filtered should have strictly fewer total targets
        # (homelab profile fires multi-discipline gates with non-security targets)
        total_all = sum(len(g["targets"]) for g in matched_all)
        total_sec = sum(len(g["targets"]) for g in matched_sec)
        self.assertLess(total_sec, total_all)

    def test_empty_profile_no_gates(self):
        self.assertEqual(evaluate_gates(None), [])
        self.assertEqual(evaluate_gates({}), [])
        self.assertEqual(evaluate_gates({"answers": {}}), [])

    def test_each_gate_has_reason(self):
        gates = load_gates()
        for name, gate in gates["gates"].items():
            self.assertIn("reason", gate, f"Gate {name} missing reason")
            self.assertIn("condition", gate, f"Gate {name} missing condition")
            self.assertIn("targets", gate, f"Gate {name} missing targets")


class TestEngineProfileIntegration(unittest.TestCase):
    """Test ForgeEngine integration with profiles and gates."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.profile = {
            "project": "test-int",
            "answers": {
                "environment": "personal-homelab",
                "users": "single-user",
                "data_sensitivity": "none",
                "architecture": "monolith",
                "has_auth": False,
                "has_ai_ml": False,
                "has_database": True,
                "has_external_apis": False,
            },
        }

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_engine_with_profile(self):
        engine = ForgeEngine("test-int", profile=self.profile)
        self.assertIsNotNone(engine.get_profile())
        self.assertEqual(engine.get_profile()["project"], "test-int")

    def test_engine_is_gated(self):
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        # BQ-13 should be gated (no_ai_ml gate)
        self.assertTrue(engine.is_gated("BQ-13"))

    def test_engine_auto_na_gated(self):
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        count = engine.auto_na_gated()
        self.assertGreater(count, 0)
        # Verify that gated DQs are now N/A
        for bq_id, tq_id, dq_idx in engine._gated_paths:
            if bq_id in engine.bqs_to_run:
                ans = engine.answers.get(bq_id, {}).get(tq_id, {}).get(str(dq_idx))
                self.assertIsNotNone(ans, f"Gated DQ {bq_id}.{tq_id}[{dq_idx}] not answered")
                self.assertEqual(ans["state"], "N/A")

    def test_gate_summary(self):
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        summary = engine.get_gate_summary()
        self.assertGreater(len(summary), 0)
        for item in summary:
            self.assertIn("name", item)
            self.assertIn("reason", item)
            self.assertIn("dqs_gated", item)

    def test_engine_without_profile(self):
        engine = ForgeEngine("no-profile-test")
        self.assertIsNone(engine.get_profile())
        self.assertEqual(len(engine._gated_paths), 0)

    def test_save_load_with_profile(self):
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        engine.auto_na_gated()

        # Save profile and state
        profile_path = os.path.join(self.tmpdir, "forge-profile-test-int.json")
        save_profile(self.profile, path=profile_path)
        self.profile["_path"] = profile_path

        engine2 = ForgeEngine("test-int", discipline="security", profile=self.profile)
        state_path = os.path.join(self.tmpdir, "forge-state-test-int.json")
        engine2.auto_na_gated()
        engine2.save(state_path)

        # Load and verify profile survives
        loaded = ForgeEngine.load(state_path)
        self.assertIsNotNone(loaded.get_profile())

    def test_report_includes_gates(self):
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        engine.auto_na_gated()
        report = engine.report()
        self.assertIn("Profile Gates Applied", report)

    def test_reanswer_improve_no_duplicate(self):
        """Re-answering a DQ as IMPROVE should not duplicate the improvement entry."""
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        engine.answer("BQ-01", "TQ-01.1", 0, state="IMPROVE",
                      answer="Could be better")
        self.assertEqual(len(engine.improvements), 1)
        # Re-answer same DQ
        engine.answer("BQ-01", "TQ-01.1", 0, state="IMPROVE",
                      answer="Updated suggestion")
        self.assertEqual(len(engine.improvements), 1)
        self.assertEqual(engine.improvements[0]["suggestion"], "Updated suggestion")

    def test_reanswer_clears_old_state(self):
        """Changing a DQ from IMPROVE to PASS should remove the improvement entry."""
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        engine.answer("BQ-01", "TQ-01.1", 0, state="IMPROVE",
                      answer="Could be better")
        self.assertEqual(len(engine.improvements), 1)
        engine.answer("BQ-01", "TQ-01.1", 0, state="PASS",
                      answer="Actually fine")
        self.assertEqual(len(engine.improvements), 0)

    def test_save_load_profile_roundtrip(self):
        """Create engine with profile, save state + profile, load, verify profile
        survives the roundtrip and gates still work."""
        engine = ForgeEngine("test-int", discipline="security", profile=self.profile)
        engine.auto_na_gated()
        gated_before = set(engine._gated_paths)

        # Save both profile and engine state
        profile_path = os.path.join(self.tmpdir, "forge-profile-test-int.json")
        save_profile(self.profile, path=profile_path)
        self.profile["_path"] = profile_path

        engine2 = ForgeEngine("test-int", discipline="security", profile=self.profile)
        state_path = os.path.join(self.tmpdir, "forge-state-test-int.json")
        engine2.auto_na_gated()
        engine2.save(state_path)

        # Load from state file
        loaded = ForgeEngine.load(state_path)
        self.assertIsNotNone(loaded.get_profile())
        self.assertEqual(loaded.get_profile()["project"], "test-int")
        # Gates should still be resolved after load
        self.assertEqual(loaded._gated_paths, gated_before)
        # Gated BQ should still report as gated
        self.assertTrue(loaded.is_gated("BQ-13"))


class TestRouter(unittest.TestCase):
    """Test discipline router."""

    def test_load_router(self):
        router = load_router()
        self.assertIn("intent_signals", router)
        self.assertIn("decision_tree", router)

    def test_recommend_broken(self):
        results = recommend_disciplines(intent="something is broken and crashing")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["discipline"], "troubleshooting")

    def test_recommend_security(self):
        results = recommend_disciplines(intent="security audit before deploy")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["discipline"], "security")

    def test_recommend_code_review(self):
        results = recommend_disciplines(intent="review this PR")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["discipline"], "code-review")

    def test_recommend_migration(self):
        results = recommend_disciplines(intent="migrate from old system")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["discipline"], "migration-planning")

    def test_recommend_testing(self):
        results = recommend_disciplines(intent="write test cases for coverage")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["discipline"], "test-specification")

    def test_recommend_architecture(self):
        results = recommend_disciplines(intent="design a new system")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["discipline"], "architecture-review")

    def test_recommend_performance_review(self):
        results = recommend_disciplines(intent="performance review and OKR discussion")
        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["discipline"], "performance-review")

    def test_recommend_default_when_no_match(self):
        results = recommend_disciplines(intent="xyzzy qwerty foobar")
        self.assertGreater(len(results), 0)
        # Should return a default recommendation
        self.assertEqual(results[0]["discipline"], "security")
        self.assertLess(results[0]["confidence"], 0.6)

    def test_bundled_recommendations(self):
        results = recommend_disciplines(intent="full comprehensive assessment")
        disciplines = [r["discipline"] for r in results]
        self.assertIn("security", disciplines)
        self.assertIn("code-review", disciplines)

    def test_result_format(self):
        results = recommend_disciplines(intent="test something")
        for r in results:
            self.assertIn("discipline", r)
            self.assertIn("confidence", r)
            self.assertIn("reason", r)
            self.assertIsInstance(r["confidence"], float)

    def test_decision_tree_structure(self):
        router = load_router()
        tree = router["decision_tree"]
        self.assertIn("root", tree)
        root = tree["root"]
        self.assertIn("question", root)
        self.assertIn("options", root)
        for opt in root["options"]:
            self.assertIn("label", opt)
            self.assertTrue(
                "result" in opt or "next" in opt,
                f"Option '{opt['label']}' has neither result nor next"
            )


class TestSimilarityScore(unittest.TestCase):
    """Test the word-overlap similarity function."""

    def test_identical(self):
        self.assertAlmostEqual(_similarity_score("hello world", "hello world"), 1.0)

    def test_no_overlap(self):
        self.assertAlmostEqual(_similarity_score("hello world", "foo bar"), 0.0)

    def test_partial_overlap(self):
        score = _similarity_score("no input validation on API", "no input validation on form")
        # Jaccard: {no,input,validation,on} / {no,input,validation,on,api,form} = 4/6
        self.assertAlmostEqual(score, 4 / 6)

    def test_empty_strings(self):
        self.assertAlmostEqual(_similarity_score("", "hello"), 0.0)
        self.assertAlmostEqual(_similarity_score("hello", ""), 0.0)
        self.assertAlmostEqual(_similarity_score("", ""), 1.0)

    def test_whitespace_only_strings(self):
        """Strings containing only spaces should behave like empty word sets."""
        self.assertAlmostEqual(_similarity_score("   ", "hello"), 0.0)
        self.assertAlmostEqual(_similarity_score("hello", "   "), 0.0)
        # Two whitespace-only strings: both split to empty word sets
        self.assertAlmostEqual(_similarity_score("   ", "   "), 0.0)

    def test_identical_strings(self):
        """Identical non-trivial strings should return exactly 1.0."""
        self.assertAlmostEqual(
            _similarity_score("input validation check", "input validation check"),
            1.0,
        )


class TestDeduplication(unittest.TestCase):
    """Test cross-discipline deduplication."""

    def _make_engine(self, discipline, gaps=None, fixes=None, kb_entries=None):
        """Helper to create an engine with pre-populated findings."""
        engine = ForgeEngine("dedup-test", discipline=discipline)
        if gaps:
            for g in gaps:
                engine.add_gap(
                    g.get("bq", "BQ-01"), g.get("tq", "TQ-01.1"),
                    g["description"],
                    severity=g.get("severity", "medium"),
                    fix=g.get("fix", ""),
                )
        if fixes:
            for f in fixes:
                engine.add_fix(
                    f.get("files", "app.py"),
                    f["description"],
                    f.get("gaps_addressed", []),
                )
        if kb_entries:
            for k in kb_entries:
                engine.add_kb_entry(
                    k.get("category", "general"),
                    k.get("trigger", ""),
                    k.get("pattern", ""),
                    k.get("impact", ""),
                )
        return engine

    def test_no_duplicates_single_engine(self):
        eng = self._make_engine("security", gaps=[
            {"description": "No input validation", "fix": "Add validation"},
        ])
        result = deduplicate_runs([eng])
        self.assertEqual(result["summary"]["total_removed"], 0)

    def test_duplicate_gaps_detected(self):
        eng1 = self._make_engine("security", gaps=[
            {"description": "No input validation on user forms",
             "fix": "Add server-side input validation"},
        ])
        eng2 = self._make_engine("code-review", gaps=[
            {"description": "No input validation on user forms",
             "fix": "Add server-side input validation to forms"},
        ])
        result = deduplicate_runs([eng1, eng2])
        self.assertEqual(result["summary"]["gaps_duped"], 1)
        self.assertEqual(result["duplicate_gaps"][0]["keep"]["discipline"], "security")

    def test_different_gaps_not_flagged(self):
        eng1 = self._make_engine("security", gaps=[
            {"description": "No input validation on user forms",
             "fix": "Add server-side input validation"},
        ])
        eng2 = self._make_engine("code-review", gaps=[
            {"description": "Database connection pool exhaustion under load",
             "fix": "Add connection pool limits and timeout"},
        ])
        result = deduplicate_runs([eng1, eng2])
        self.assertEqual(result["summary"]["gaps_duped"], 0)

    def test_same_discipline_not_compared(self):
        eng1 = self._make_engine("security", gaps=[
            {"description": "No input validation on user forms",
             "fix": "Add server-side input validation"},
            {"description": "No input validation on user forms",
             "fix": "Add server-side input validation"},
        ])
        eng2 = self._make_engine("code-review", gaps=[
            {"description": "Something completely different",
             "fix": "Different fix"},
        ])
        result = deduplicate_runs([eng1, eng2])
        # Same-discipline duplicates are NOT flagged (that's a within-run issue)
        self.assertEqual(result["summary"]["gaps_duped"], 0)

    def test_duplicate_fixes_detected(self):
        eng1 = self._make_engine("security", fixes=[
            {"description": "Added input validation to API endpoint",
             "files": "api.py", "gaps_addressed": ["G-001"]},
        ])
        eng2 = self._make_engine("code-review", fixes=[
            {"description": "Added input validation to API endpoint",
             "files": "api.py", "gaps_addressed": ["G-002"]},
        ])
        result = deduplicate_runs([eng1, eng2])
        self.assertEqual(result["summary"]["fixes_duped"], 1)

    def test_different_files_not_duplicate_fix(self):
        eng1 = self._make_engine("security", fixes=[
            {"description": "Added input validation",
             "files": "api.py", "gaps_addressed": ["G-001"]},
        ])
        eng2 = self._make_engine("code-review", fixes=[
            {"description": "Added input validation",
             "files": "frontend.js", "gaps_addressed": ["G-001"]},
        ])
        result = deduplicate_runs([eng1, eng2])
        # Same description but different files = different fix
        self.assertEqual(result["summary"]["fixes_duped"], 0)

    def test_duplicate_kb_detected(self):
        eng1 = self._make_engine("security", kb_entries=[
            {"category": "api-integration",
             "trigger": "API returns unexpected JSON format",
             "pattern": "API endpoint path mismatch with upstream",
             "impact": "Silent failure"},
        ])
        eng2 = self._make_engine("code-review", kb_entries=[
            {"category": "api-integration",
             "trigger": "API returns unexpected JSON format",
             "pattern": "API endpoint path mismatch with upstream service",
             "impact": "Requests fail silently"},
        ])
        result = deduplicate_runs([eng1, eng2])
        self.assertEqual(result["summary"]["kb_duped"], 1)

    def test_different_category_kb_not_duplicate(self):
        eng1 = self._make_engine("security", kb_entries=[
            {"category": "api-integration",
             "trigger": "API returns unexpected format",
             "pattern": "Endpoint mismatch",
             "impact": "Failure"},
        ])
        eng2 = self._make_engine("code-review", kb_entries=[
            {"category": "performance",
             "trigger": "API returns unexpected format",
             "pattern": "Endpoint mismatch",
             "impact": "Failure"},
        ])
        result = deduplicate_runs([eng1, eng2])
        self.assertEqual(result["summary"]["kb_duped"], 0)

    def test_apply_dedup_removes_items(self):
        eng1 = self._make_engine("security", gaps=[
            {"description": "No input validation on user forms",
             "fix": "Add server-side input validation"},
        ])
        eng2 = self._make_engine("code-review", gaps=[
            {"description": "No input validation on user forms",
             "fix": "Add server-side input validation to forms"},
        ])
        result = deduplicate_runs([eng1, eng2])
        self.assertEqual(len(eng1.gaps) + len(eng2.gaps), 2)

        removals = apply_dedup([eng1, eng2], result)
        self.assertEqual(removals["gaps"], 1)
        # Total gaps across both engines should now be 1
        self.assertEqual(len(eng1.gaps) + len(eng2.gaps), 1)

    def test_higher_severity_kept(self):
        eng1 = self._make_engine("security", gaps=[
            {"description": "No input validation on forms",
             "severity": "high",
             "fix": "Add server-side validation"},
        ])
        eng2 = self._make_engine("code-review", gaps=[
            {"description": "No input validation on forms",
             "severity": "low",
             "fix": "Add server-side validation"},
        ])
        result = deduplicate_runs([eng1, eng2])
        # The high-severity one should be kept
        self.assertEqual(result["duplicate_gaps"][0]["keep"]["discipline"], "security")
        self.assertEqual(result["duplicate_gaps"][0]["remove"]["discipline"], "code-review")

    def test_three_engines(self):
        eng1 = self._make_engine("security", gaps=[
            {"description": "No input validation on forms",
             "fix": "Add server-side validation"},
        ])
        eng2 = self._make_engine("code-review", gaps=[
            {"description": "No input validation on forms",
             "fix": "Add server-side validation"},
        ])
        eng3 = self._make_engine("test-specification", gaps=[
            {"description": "No input validation on forms",
             "fix": "Add server-side validation"},
        ])
        result = deduplicate_runs([eng1, eng2, eng3])
        # Should find duplicates across all 3 pairs
        self.assertGreaterEqual(result["summary"]["gaps_duped"], 2)

    def test_dedup_result_format(self):
        eng1 = self._make_engine("security", gaps=[
            {"description": "Test gap", "fix": "Test fix"},
        ])
        eng2 = self._make_engine("code-review", gaps=[
            {"description": "Test gap", "fix": "Test fix"},
        ])
        result = deduplicate_runs([eng1, eng2])
        self.assertIn("duplicate_gaps", result)
        self.assertIn("duplicate_fixes", result)
        self.assertIn("duplicate_kb", result)
        self.assertIn("summary", result)
        for dup in result["duplicate_gaps"]:
            self.assertIn("keep", dup)
            self.assertIn("remove", dup)
            self.assertIn("confidence", dup)
            self.assertIn("id", dup["keep"])
            self.assertIn("discipline", dup["keep"])

    def test_single_engine_no_duplicates(self):
        """A single engine should produce no cross-discipline duplicates."""
        eng = self._make_engine("security", gaps=[
            {"description": "Missing rate limiting", "fix": "Add rate limiter"},
            {"description": "No CSRF protection", "fix": "Add CSRF tokens"},
        ])
        result = deduplicate_runs([eng])
        self.assertEqual(result["summary"]["total_removed"], 0)
        self.assertEqual(result["summary"]["gaps_duped"], 0)
        self.assertEqual(result["summary"]["fixes_duped"], 0)
        self.assertEqual(result["summary"]["kb_duped"], 0)

    def test_empty_engines_list(self):
        """Empty engine list should return empty results with zero counts."""
        result = deduplicate_runs([])
        self.assertEqual(result["summary"]["total_removed"], 0)
        self.assertEqual(result["summary"]["gaps_duped"], 0)
        self.assertEqual(len(result["duplicate_gaps"]), 0)
        self.assertEqual(len(result["duplicate_fixes"]), 0)
        self.assertEqual(len(result["duplicate_kb"]), 0)


class TestCapabilityExtraction(unittest.TestCase):
    """Test capability signal detection from text."""

    def test_monitoring_detected(self):
        caps = _extract_capabilities("Add health check endpoint for API monitoring")
        self.assertIn("monitoring", caps)

    def test_validation_detected(self):
        caps = _extract_capabilities("Add input validation to form handler")
        self.assertIn("input-validation", caps)

    def test_multiple_capabilities(self):
        caps = _extract_capabilities(
            "Add authentication check and input validation to API endpoint"
        )
        self.assertIn("auth-access", caps)
        self.assertIn("input-validation", caps)

    def test_empty_string(self):
        caps = _extract_capabilities("")
        self.assertEqual(len(caps), 0)

    def test_no_match(self):
        caps = _extract_capabilities("refactored variable names for clarity")
        self.assertEqual(len(caps), 0)

    def test_deployment_ops_detected(self):
        caps = _extract_capabilities("Added cron entry for automated scheduler")
        self.assertIn("deployment-ops", caps)

    def test_error_handling_detected(self):
        caps = _extract_capabilities("Improved error handling with retry logic and circuit breaker")
        self.assertIn("error-handling", caps)


class TestConsolidationAnalysis(unittest.TestCase):
    """Test fix consolidation analysis."""

    def _make_engine(self, discipline, gaps=None, fixes=None):
        engine = ForgeEngine("consol-test", discipline=discipline)
        if gaps:
            for g in gaps:
                engine.add_gap(
                    g.get("bq", "BQ-01"), g.get("tq", "TQ-01.1"),
                    g["description"],
                    severity=g.get("severity", "medium"),
                    fix=g.get("fix", ""),
                )
        if fixes:
            for f in fixes:
                engine.add_fix(
                    f.get("files", "app.py"),
                    f["description"],
                    f.get("gaps_addressed", []),
                )
        return engine

    def test_monitoring_cluster_detected(self):
        """Multiple monitoring-related fixes should cluster together."""
        eng1 = self._make_engine("security", gaps=[
            {"description": "No monitoring for provider status changes",
             "fix": "Add provider status check to monitoring agent"},
            {"description": "Health checks are superficial",
             "fix": "Add connectivity check to health endpoint"},
            {"description": "No automated detection of pipeline failures",
             "fix": "Add pipeline status check to monitoring agent"},
        ])
        result = analyze_consolidation([eng1], min_cluster=2)
        self.assertGreater(result["summary"]["opportunities_found"], 0)
        caps = [o["capability"] for o in result["opportunities"]]
        self.assertIn("monitoring", caps)

    def test_cross_discipline_is_strong(self):
        """Cluster spanning multiple disciplines should be 'strong'."""
        eng1 = self._make_engine("security", fixes=[
            {"description": "Added health check for API monitoring"},
            {"description": "Added alerting for failed health checks"},
        ])
        eng2 = self._make_engine("code-review", fixes=[
            {"description": "Added status dashboard for monitoring"},
        ])
        result = analyze_consolidation([eng1, eng2], min_cluster=2)
        monitoring_opps = [
            o for o in result["opportunities"]
            if o["capability"] == "monitoring"
        ]
        self.assertEqual(len(monitoring_opps), 1)
        self.assertEqual(monitoring_opps[0]["strength"], "strong")

    def test_single_discipline_is_moderate(self):
        """Cluster within one discipline should be 'moderate'."""
        eng1 = self._make_engine("security", fixes=[
            {"description": "Added health check for API monitoring"},
            {"description": "Added alerting for failed health checks"},
            {"description": "Added monitoring dashboard"},
        ])
        result = analyze_consolidation([eng1], min_cluster=2)
        monitoring_opps = [
            o for o in result["opportunities"]
            if o["capability"] == "monitoring"
        ]
        self.assertEqual(len(monitoring_opps), 1)
        self.assertEqual(monitoring_opps[0]["strength"], "moderate")

    def test_no_cluster_below_threshold(self):
        """A single fix in a capability should not create an opportunity."""
        eng1 = self._make_engine("security", fixes=[
            {"description": "Added health check monitoring"},
        ])
        result = analyze_consolidation([eng1], min_cluster=3)
        self.assertEqual(result["summary"]["opportunities_found"], 0)

    def test_distinct_fixes_no_opportunity(self):
        """Fixes in different capability areas should not cluster."""
        eng1 = self._make_engine("security", fixes=[
            {"description": "Added input validation to form"},
            {"description": "Fixed database migration script"},
            {"description": "Updated deployment pipeline"},
        ])
        # Each is a different capability, so no cluster of 3+
        result = analyze_consolidation([eng1], min_cluster=3)
        self.assertEqual(result["summary"]["opportunities_found"], 0)

    def test_result_format(self):
        eng1 = self._make_engine("security", fixes=[
            {"description": "Added health check endpoint for monitoring"},
            {"description": "Added status alerting and notification"},
            {"description": "Added dashboard for metric tracking"},
        ])
        result = analyze_consolidation([eng1], min_cluster=2)
        self.assertIn("opportunities", result)
        self.assertIn("summary", result)
        for opp in result["opportunities"]:
            self.assertIn("capability", opp)
            self.assertIn("suggested_name", opp)
            self.assertIn("rationale", opp)
            self.assertIn("fixes_consolidated", opp)
            self.assertIn("gaps_consolidated", opp)
            self.assertIn("disciplines_involved", opp)
            self.assertIn("strength", opp)

    def test_subtitle_pipeline_scenario(self):
        """Real-world scenario: subtitle pipeline gaps should cluster to monitoring."""
        eng = self._make_engine("troubleshooting", gaps=[
            {"description": "Health checks are superficial — report healthy when API is broken",
             "fix": "Add Bazarr connectivity check to health endpoint"},
            {"description": "No monitoring/alerting for Bazarr provider status changes",
             "fix": "Add provider status check to monitoring agent"},
            {"description": "No automated detection of subtitle pipeline failures",
             "fix": "Add Bazarr provider status check to ops agent"},
            {"description": "subtitle_auditor not in cron — never runs automatically",
             "fix": "Add cron entry for automated execution"},
        ], fixes=[
            {"description": "Replaced superficial health endpoint with deep connectivity check"},
            {"description": "Added provider status monitoring to OpsAgent"},
            {"description": "Added cron entry for subtitle_auditor automated runs"},
        ])
        result = analyze_consolidation([eng], min_cluster=2)
        self.assertGreater(result["summary"]["opportunities_found"], 0)
        # Should find monitoring and/or deployment-ops clusters
        caps = [o["capability"] for o in result["opportunities"]]
        self.assertTrue(
            "monitoring" in caps or "deployment-ops" in caps,
            f"Expected monitoring or deployment-ops in {caps}"
        )


class TestDeepConsolidation(unittest.TestCase):
    """Test deep consolidation with prior run scanning."""

    def _make_engine(self, project, discipline, gaps=None, fixes=None,
                     kb_entries=None):
        engine = ForgeEngine(project, discipline=discipline)
        if gaps:
            for g in gaps:
                engine.add_gap(
                    g.get("bq", "BQ-01"), g.get("tq", "TQ-01.1"),
                    g["description"],
                    severity=g.get("severity", "medium"),
                    fix=g.get("fix", ""),
                )
        if fixes:
            for f in fixes:
                engine.add_fix(
                    f.get("files", "app.py"),
                    f["description"],
                    f.get("gaps_addressed", []),
                )
        if kb_entries:
            for k in kb_entries:
                engine.add_kb_entry(
                    k.get("category", "general"),
                    k.get("trigger", ""),
                    k.get("pattern", ""),
                    k.get("impact", ""),
                )
        return engine

    def test_deep_returns_base_fields(self):
        eng = self._make_engine("proj-a", "security", fixes=[
            {"description": "Added health check monitoring endpoint"},
            {"description": "Added alerting for failed health checks"},
            {"description": "Added status dashboard for monitoring"},
        ])
        result = analyze_consolidation_deep([eng], min_cluster=2)
        self.assertIn("opportunities", result)
        self.assertIn("summary", result)
        self.assertIn("prior_runs_scanned", result)

    def test_deep_adds_recommendation_field(self):
        eng = self._make_engine("proj-a", "security", fixes=[
            {"description": "Added health check monitoring endpoint"},
            {"description": "Added alerting for failed health checks"},
            {"description": "Added status dashboard for monitoring"},
        ])
        result = analyze_consolidation_deep([eng], min_cluster=2)
        for opp in result["opportunities"]:
            self.assertIn("recommendation", opp)
            self.assertIn(opp["recommendation"], ["build_new", "extend_existing"])
            self.assertIn("prior_evidence", opp)
            self.assertIn("kb_patterns", opp)

    def test_extend_existing_when_systemic_fix_present(self):
        """If a fix looks like a systemic solution (mentions 'service',
        'agent', etc.), recommend extending it."""
        tmpdir = tempfile.mkdtemp()
        try:
            eng = self._make_engine("proj-a", "security", fixes=[
                {"description": "Added monitoring checks to OpsAgent service"},
                {"description": "Added health check endpoint for status tracking"},
                {"description": "Added alerting for failed monitoring checks"},
            ])
            # Use empty search_dir to isolate from prior state files
            result = analyze_consolidation_deep(
                [eng], min_cluster=2, search_dir=tmpdir,
            )
            monitoring = [o for o in result["opportunities"]
                          if o["capability"] == "monitoring"]
            self.assertEqual(len(monitoring), 1)
            self.assertEqual(monitoring[0]["recommendation"], "extend_existing")
            self.assertIsInstance(monitoring[0]["existing_partial"], str)
            self.assertGreater(len(monitoring[0]["existing_partial"]), 0)
        finally:
            os.rmdir(tmpdir)

    def test_build_new_when_no_systemic_fix(self):
        """If fixes are all point patches and no prior runs, recommend building new."""
        tmpdir = tempfile.mkdtemp()
        try:
            eng = self._make_engine("proj-a", "security", fixes=[
                {"description": "Added health check to /status"},
                {"description": "Added alert on check failure"},
                {"description": "Added log for monitoring errors"},
            ])
            # Use empty tmpdir so no prior runs are discovered
            result = analyze_consolidation_deep(
                [eng], min_cluster=2, search_dir=tmpdir,
            )
            monitoring = [o for o in result["opportunities"]
                          if o["capability"] == "monitoring"]
            self.assertEqual(len(monitoring), 1)
            self.assertEqual(monitoring[0]["recommendation"], "build_new")
            self.assertIsNone(monitoring[0]["existing_partial"])
        finally:
            os.rmdir(tmpdir)

    def test_prior_evidence_from_saved_state(self):
        """Deep analysis should find prior runs via forge-state-*.json."""
        tmpdir = tempfile.mkdtemp()
        try:
            # Create a "prior" run with monitoring fixes
            prior = self._make_engine("prior-proj", "troubleshooting", fixes=[
                {"description": "Added health monitoring endpoint"},
            ])
            prior.save(os.path.join(tmpdir, "forge-state-prior-proj.json"))

            # Current run also has monitoring fixes
            current = self._make_engine("current-proj", "security", fixes=[
                {"description": "Added monitoring alerting system"},
                {"description": "Added health check dashboard"},
                {"description": "Added status tracking endpoint"},
            ])

            result = analyze_consolidation_deep(
                [current], min_cluster=2, search_dir=tmpdir,
            )
            self.assertEqual(result["prior_runs_scanned"], 1)

            monitoring = [o for o in result["opportunities"]
                          if o["capability"] == "monitoring"]
            self.assertEqual(len(monitoring), 1)
            self.assertEqual(len(monitoring[0]["prior_evidence"]), 1)
            self.assertEqual(monitoring[0]["strength"], "strong")
        finally:
            for f in os.listdir(tmpdir):
                os.remove(os.path.join(tmpdir, f))
            os.rmdir(tmpdir)

    def test_kb_patterns_matched(self):
        """KB entries with matching capabilities should appear in results."""
        tmpdir = tempfile.mkdtemp()
        try:
            eng = self._make_engine("proj-a", "security",
                fixes=[
                    {"description": "Added health check monitoring endpoint"},
                    {"description": "Added alerting for failed health checks"},
                    {"description": "Added status dashboard for monitoring"},
                ],
                kb_entries=[
                    {"category": "monitoring",
                     "trigger": "Health check failed silently",
                     "pattern": "Monitoring gap allowed silent failure",
                     "impact": "Outage not detected for hours"},
                ],
            )
            result = analyze_consolidation_deep(
                [eng], min_cluster=2, search_dir=tmpdir,
            )
            monitoring = [o for o in result["opportunities"]
                          if o["capability"] == "monitoring"]
            self.assertEqual(len(monitoring), 1)
            self.assertEqual(len(monitoring[0]["kb_patterns"]), 1)
        finally:
            os.rmdir(tmpdir)

    def test_no_opportunities_returns_cleanly(self):
        """If no consolidation found, deep still returns proper structure."""
        eng = self._make_engine("proj-a", "security", fixes=[
            {"description": "Fixed typo in variable name"},
        ])
        result = analyze_consolidation_deep([eng], min_cluster=3)
        self.assertEqual(result["summary"]["opportunities_found"], 0)
        self.assertIn("prior_runs_scanned", result)

    def test_excludes_active_projects_from_prior(self):
        """Active project state files should not be double-counted."""
        tmpdir = tempfile.mkdtemp()
        try:
            eng = self._make_engine("same-proj", "security", fixes=[
                {"description": "Added monitoring health check"},
                {"description": "Added monitoring alerting"},
                {"description": "Added monitoring dashboard"},
            ])
            eng.save(os.path.join(tmpdir, "forge-state-same-proj.json"))

            result = analyze_consolidation_deep(
                [eng], min_cluster=2, search_dir=tmpdir,
            )
            # Should NOT find the same project as "prior evidence"
            for opp in result["opportunities"]:
                for ev in opp.get("prior_evidence", []):
                    self.assertNotEqual(ev["project"], "same-proj")
        finally:
            for f in os.listdir(tmpdir):
                os.remove(os.path.join(tmpdir, f))
            os.rmdir(tmpdir)


class TestNormalizeServiceName(unittest.TestCase):
    """Test service name extraction from file references."""

    def test_simple_py(self):
        self.assertEqual(_normalize_service_name("ops_agent.py"), "ops_agent")

    def test_full_path(self):
        self.assertEqual(
            _normalize_service_name("/mnt/Main/scripts/health_watchdog.py"),
            "health_watchdog",
        )

    def test_container_reference(self):
        self.assertEqual(_normalize_service_name("Bazarr container"), "bazarr")

    def test_nested_path(self):
        self.assertEqual(
            _normalize_service_name("backend/heartbeat/ops_agent.py"),
            "ops_agent",
        )

    def test_config_file(self):
        self.assertEqual(_normalize_service_name("config/settings.json"), "settings")

    def test_empty(self):
        self.assertEqual(_normalize_service_name(""), "unknown")

    def test_hyphenated(self):
        self.assertEqual(
            _normalize_service_name("subtitle-automation.py"),
            "subtitle_automation",
        )


class TestServiceAnalysis(unittest.TestCase):
    """Test service-level improvement analysis."""

    def _make_engine(self, project, discipline, gaps=None, fixes=None):
        engine = ForgeEngine(project, discipline=discipline)
        if gaps:
            for g in gaps:
                engine.add_gap(
                    g.get("bq", "BQ-01"), g.get("tq", "TQ-01.1"),
                    g["description"],
                    severity=g.get("severity", "medium"),
                    fix=g.get("fix", ""),
                )
        if fixes:
            for f in fixes:
                engine.add_fix(
                    f.get("files", "app.py"),
                    f["description"],
                    f.get("gaps_addressed", []),
                )
        return engine

    def test_services_extracted_from_fixes(self):
        eng = self._make_engine("proj", "security", fixes=[
            {"files": "ops_agent.py",
             "description": "Added health monitoring check"},
            {"files": "health_watchdog.py",
             "description": "Added alerting for health failures"},
        ])
        result = analyze_services([eng], search_dir=tempfile.mkdtemp())
        svcs = result["services"]
        self.assertIn("ops_agent", svcs)
        self.assertIn("health_watchdog", svcs)

    def test_overlap_detected(self):
        """Two services both handling monitoring should be flagged."""
        eng = self._make_engine("proj", "security", fixes=[
            {"files": "ops_agent.py",
             "description": "Added health monitoring check and alerting"},
            {"files": "health_watchdog.py",
             "description": "Added monitoring dashboard and alerting"},
        ])
        tmpdir = tempfile.mkdtemp()
        result = analyze_services([eng], search_dir=tmpdir)
        os.rmdir(tmpdir)
        overlaps = result["overlaps"]
        self.assertEqual(len(overlaps), 1)
        svc_pairs = [tuple(sorted(o["services"])) for o in overlaps]
        self.assertIn(
            tuple(sorted(["ops_agent", "health_watchdog"])),
            svc_pairs,
        )

    def test_merge_recommended_for_high_overlap(self):
        """High overlap (2+ specific shared capabilities) should produce merge."""
        eng = self._make_engine("proj", "troubleshooting", fixes=[
            {"files": "ops_agent.py",
             "description": "Added health monitoring alerting and error handling with retry"},
            {"files": "health_watchdog.py",
             "description": "Added monitoring health check and error recovery with fallback"},
        ])
        tmpdir = tempfile.mkdtemp()
        result = analyze_services([eng], search_dir=tmpdir)
        os.rmdir(tmpdir)
        # Both share monitoring + error-handling (2 specific caps)
        self.assertEqual(len(result["overlaps"]), 1)
        self.assertEqual(
            sorted(result["overlaps"][0]["specific_shared"]),
            ["error-handling", "monitoring"],
        )
        merge_recs = [r for r in result["recommendations"] if r["type"] == "merge"]
        self.assertEqual(len(merge_recs), 1)

    def test_no_overlap_clean_services(self):
        """Services with distinct capabilities should not overlap."""
        eng = self._make_engine("proj", "security", fixes=[
            {"files": "auth_service.py",
             "description": "Added authentication and authorization checks"},
            {"files": "db_migration.py",
             "description": "Fixed database migration and schema constraints"},
        ])
        tmpdir = tempfile.mkdtemp()
        result = analyze_services([eng], search_dir=tmpdir)
        os.rmdir(tmpdir)
        self.assertEqual(len(result["overlaps"]), 0)

    def test_result_format(self):
        eng = self._make_engine("proj", "security", fixes=[
            {"files": "app.py", "description": "Added health monitoring"},
        ])
        tmpdir = tempfile.mkdtemp()
        result = analyze_services([eng], search_dir=tmpdir)
        os.rmdir(tmpdir)
        self.assertIn("services", result)
        self.assertIn("overlaps", result)
        self.assertIn("absorptions", result)
        self.assertIn("recommendations", result)
        self.assertIn("summary", result)
        self.assertIn("services_found", result["summary"])

    def test_subtitle_pipeline_scenario(self):
        """Real-world: subtitle pipeline fixes should map to services."""
        eng = self._make_engine("sub-pipe", "troubleshooting", fixes=[
            {"files": "subtitle_automation.py",
             "description": "Fixed 3 Bazarr API endpoint paths"},
            {"files": "subtitle_automation.py",
             "description": "Replaced superficial health endpoint with deep check"},
            {"files": "subtitle_automation.py",
             "description": "Added startup_smoke_test() that validates API endpoints"},
            {"files": "subtitle_automation.py",
             "description": "Improved error logging to include HTTP method"},
            {"files": "ops_agent.py",
             "description": "Added _check_subtitle_pipeline to OpsAgent: monitors providers"},
            {"files": "crontab",
             "description": "Added cron entry for subtitle_auditor automated runs"},
        ])
        tmpdir = tempfile.mkdtemp()
        result = analyze_services([eng], search_dir=tmpdir)
        os.rmdir(tmpdir)
        svcs = result["services"]
        self.assertIn("subtitle_automation", svcs)
        self.assertIn("ops_agent", svcs)
        # subtitle_automation has exactly 4 fixes
        self.assertEqual(svcs["subtitle_automation"]["fix_count"], 4)

    def test_cross_discipline_service_map(self):
        """Services should accumulate data from multiple disciplines."""
        eng1 = self._make_engine("proj", "security", fixes=[
            {"files": "api_gateway.py",
             "description": "Added input validation middleware"},
        ])
        eng2 = self._make_engine("proj", "code-review", fixes=[
            {"files": "api_gateway.py",
             "description": "Added authentication check to gateway"},
        ])
        tmpdir = tempfile.mkdtemp()
        result = analyze_services([eng1, eng2], search_dir=tmpdir)
        os.rmdir(tmpdir)
        self.assertIn("api_gateway", result["services"])
        gw = result["services"]["api_gateway"]
        self.assertEqual(gw["fix_count"], 2)
        self.assertEqual(sorted(gw["disciplines"]), ["code-review", "security"])


class TestVP02KBCheck(unittest.TestCase):
    """Test VP-02 kb_checked verification logic.

    VP-02 kb_checked rule: if the engine has gaps, it must also have KB entries.
    If there are no gaps, KB entries are not required.
    """

    def test_vp02_fails_with_gaps_no_kb(self):
        """Engine with gaps but no KB entries should fail VP-02 kb_checked."""
        engine = ForgeEngine("vp02-test", discipline="security")
        engine.add_gap("BQ-01", "TQ-01.1", "Missing input validation",
                       severity="medium", fix="Add validation")
        result = engine.verify()
        self.assertFalse(result["VP-02"]["checks"]["kb_checked"])

    def test_vp02_passes_with_gaps_and_kb(self):
        """Engine with gaps AND KB entries should pass VP-02 kb_checked."""
        engine = ForgeEngine("vp02-test", discipline="security")
        engine.add_gap("BQ-01", "TQ-01.1", "Missing input validation",
                       severity="medium", fix="Add validation")
        engine.add_kb_entry(
            category="input-validation",
            trigger="User input not sanitized",
            pattern="Missing validation on form handler",
            impact="Potential injection attack",
        )
        result = engine.verify()
        self.assertTrue(result["VP-02"]["checks"]["kb_checked"])

    def test_vp02_passes_with_no_gaps(self):
        """Engine with no gaps should pass VP-02 kb_checked regardless of KB."""
        engine = ForgeEngine("vp02-test", discipline="security")
        # No gaps, no KB entries
        result = engine.verify()
        self.assertTrue(result["VP-02"]["checks"]["kb_checked"])

        # No gaps, but has KB entries — should still pass
        engine.add_kb_entry(
            category="general",
            trigger="Informational pattern",
            pattern="Good practice observed",
            impact="None",
        )
        result = engine.verify()
        self.assertTrue(result["VP-02"]["checks"]["kb_checked"])


if __name__ == "__main__":
    unittest.main()
