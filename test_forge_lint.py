#!/usr/bin/env python3
"""Tests for forge_lint.py — the DQ-file data validator."""

import json
import os
import unittest

import forge_lint


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))


class TestRealRepoData(unittest.TestCase):
    """The actual disciplines/ + profile data in this repo must lint clean."""

    def test_no_errors_in_repo_data(self):
        findings = forge_lint.run_lint(REPO_ROOT)
        errors = [f for f in findings if f.severity == "error"]
        self.assertEqual(
            errors, [], "\n" + "\n".join(str(f) for f in errors)
        )


class TestDuplicateKeyDetection(unittest.TestCase):
    def test_load_yaml_checking_dups_reports_dup(self):
        path = os.path.join(REPO_ROOT, "disciplines", "gates.yaml")
        # Sanity check the loader itself round-trips clean data with no dups.
        data, dups = forge_lint.load_yaml_checking_dups(path)
        self.assertEqual(dups, [])
        self.assertIn("gates", data)

    def test_dup_key_yaml_flagged(self, tmp_path=None):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dup.yaml")
            with open(path, "w") as f:
                f.write("a: 1\na: 2\n")
            data, dups = forge_lint.load_yaml_checking_dups(path)
            self.assertEqual(dups, ["a"])
            self.assertEqual(data["a"], 2)


class TestLintDisciplineFile(unittest.TestCase):
    def test_missing_required_fields_flagged(self):
        data = {"id": "x", "questions": {}}
        findings = forge_lint.lint_discipline_file("disciplines/x.yaml", data, [])
        messages = [f.message for f in findings]
        self.assertTrue(any("name" in m for m in messages))
        self.assertTrue(any("version" in m for m in messages))
        self.assertTrue(any("non-empty mapping" in m for m in messages))

    def test_id_mismatch_flagged(self):
        data = {
            "name": "X",
            "id": "wrong-id",
            "version": "1.0.0",
            "questions": {"BQ-01": {"name": "A", "tqs": {"TQ-01.1": {"name": "B", "dqs": ["q1"]}}}},
        }
        findings = forge_lint.lint_discipline_file("disciplines/x.yaml", data, [])
        self.assertTrue(any("does not match filename" in f.message for f in findings))

    def test_empty_dqs_flagged(self):
        data = {
            "name": "X",
            "id": "x",
            "version": "1.0.0",
            "questions": {"BQ-01": {"name": "A", "tqs": {"TQ-01.1": {"name": "B", "dqs": []}}}},
        }
        findings = forge_lint.lint_discipline_file("disciplines/x.yaml", data, [])
        self.assertTrue(any("missing or empty 'dqs'" in f.message for f in findings))

    def test_duplicate_dq_text_flagged(self):
        data = {
            "name": "X",
            "id": "x",
            "version": "1.0.0",
            "questions": {
                "BQ-01": {
                    "name": "A",
                    "tqs": {"TQ-01.1": {"name": "B", "dqs": ["same question?", "same question?"]}},
                }
            },
        }
        findings = forge_lint.lint_discipline_file("disciplines/x.yaml", data, [])
        self.assertTrue(any("duplicate DQ text" in f.message for f in findings))

    def test_bad_triage_preset_ref_flagged(self):
        data = {
            "name": "X",
            "id": "x",
            "version": "1.0.0",
            "triage_presets": {"quick": ["BQ-99"]},
            "questions": {"BQ-01": {"name": "A", "tqs": {"TQ-01.1": {"name": "B", "dqs": ["q1"]}}}},
        }
        findings = forge_lint.lint_discipline_file("disciplines/x.yaml", data, [])
        self.assertTrue(any("unknown BQ 'BQ-99'" in f.message for f in findings))

    def test_valid_discipline_clean(self):
        data = {
            "name": "X",
            "id": "x",
            "version": "1.0.0",
            "questions": {"BQ-01": {"name": "A", "tqs": {"TQ-01.1": {"name": "B", "dqs": ["q1", "q2"]}}}},
        }
        findings = forge_lint.lint_discipline_file("disciplines/x.yaml", data, [])
        self.assertEqual(findings, [])


class TestLintGates(unittest.TestCase):
    def setUp(self):
        self.disciplines = {
            "security": {
                "questions": {
                    "BQ-01": {"tqs": {"TQ-01.1": {"dqs": ["q1", "q2"]}}},
                }
            }
        }
        self.intake_fields = {"has_auth": {"type": "bool"}}

    def test_bad_target_discipline_flagged(self):
        data = {"gates": {"g1": {"condition": "has_auth == false", "reason": "r", "targets": ["nope:BQ-01"]}}}
        findings = forge_lint.lint_gates("gates.yaml", data, [], self.disciplines, self.intake_fields)
        self.assertTrue(any("unknown discipline 'nope'" in f.message for f in findings))

    def test_bad_target_bq_flagged(self):
        data = {"gates": {"g1": {"condition": "has_auth == false", "reason": "r", "targets": ["security:BQ-99"]}}}
        findings = forge_lint.lint_gates("gates.yaml", data, [], self.disciplines, self.intake_fields)
        self.assertTrue(any("unknown BQ 'BQ-99'" in f.message for f in findings))

    def test_dq_index_out_of_range_flagged(self):
        data = {
            "gates": {
                "g1": {
                    "condition": "has_auth == false",
                    "reason": "r",
                    "targets": ["security:BQ-01.TQ-01.1[5]"],
                }
            }
        }
        findings = forge_lint.lint_gates("gates.yaml", data, [], self.disciplines, self.intake_fields)
        self.assertTrue(any("DQ index 5 out of range" in f.message for f in findings))

    def test_unknown_condition_field_flagged(self):
        data = {"gates": {"g1": {"condition": "has_bogus_field == false", "reason": "r", "targets": ["security:BQ-01"]}}}
        findings = forge_lint.lint_gates("gates.yaml", data, [], self.disciplines, self.intake_fields)
        self.assertTrue(any("unknown intake field 'has_bogus_field'" in f.message for f in findings))

    def test_valid_gate_clean(self):
        data = {"gates": {"g1": {"condition": "has_auth == false", "reason": "r", "targets": ["security:BQ-01"]}}}
        findings = forge_lint.lint_gates("gates.yaml", data, [], self.disciplines, self.intake_fields)
        self.assertEqual(findings, [])


class TestLintRouter(unittest.TestCase):
    def setUp(self):
        self.disciplines = {"security": {}, "code-review": {}}

    def test_bad_primary_flagged(self):
        data = {"intent_signals": {"sig": {"primary": "bogus"}}}
        findings = forge_lint.lint_router("router.yaml", data, [], self.disciplines)
        self.assertTrue(any("unknown discipline 'bogus'" in f.message for f in findings))

    def test_bad_decision_tree_result_flagged(self):
        data = {"decision_tree": {"root": {"options": [{"label": "x", "result": ["bogus"]}]}}}
        findings = forge_lint.lint_router("router.yaml", data, [], self.disciplines)
        self.assertTrue(any("unknown discipline 'bogus'" in f.message for f in findings))

    def test_bad_decision_tree_next_flagged(self):
        data = {"decision_tree": {"root": {"options": [{"label": "x", "next": "missing_node"}]}}}
        findings = forge_lint.lint_router("router.yaml", data, [], self.disciplines)
        self.assertTrue(any("unknown node 'missing_node'" in f.message for f in findings))


class TestLintProfile(unittest.TestCase):
    def setUp(self):
        self.intake_fields = {
            "environment": {"type": "choice", "options": ["personal-homelab", "production-saas"]},
            "has_auth": {"type": "bool"},
        }

    def _write(self, tmp, name, obj):
        path = os.path.join(tmp, name)
        with open(path, "w") as f:
            json.dump(obj, f)
        return path

    def test_missing_answers_wrapper_flagged(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(tmp, "forge-profile-x.json", {"project": "x", "environment": "production-saas"})
            findings = forge_lint.lint_profile(path, self.intake_fields)
            self.assertTrue(any("missing required field 'answers'" in f.message for f in findings))

    def test_unknown_answer_field_flagged(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                "forge-profile-x.json",
                {
                    "version": "1.0.0",
                    "project": "x",
                    "created": "now",
                    "updated": "now",
                    "answers": {"bogus_field": True},
                },
            )
            findings = forge_lint.lint_profile(path, self.intake_fields)
            self.assertTrue(any("unknown intake field 'bogus_field'" in f.message for f in findings))

    def test_bad_choice_value_flagged(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                "forge-profile-x.json",
                {
                    "version": "1.0.0",
                    "project": "x",
                    "created": "now",
                    "updated": "now",
                    "answers": {"environment": "not-a-real-option"},
                },
            )
            findings = forge_lint.lint_profile(path, self.intake_fields)
            self.assertTrue(any("not in options" in f.message for f in findings))

    def test_bad_bool_value_flagged(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                "forge-profile-x.json",
                {
                    "version": "1.0.0",
                    "project": "x",
                    "created": "now",
                    "updated": "now",
                    "answers": {"has_auth": "yes"},
                },
            )
            findings = forge_lint.lint_profile(path, self.intake_fields)
            self.assertTrue(any("expected bool" in f.message for f in findings))

    def test_valid_profile_clean(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = self._write(
                tmp,
                "forge-profile-x.json",
                {
                    "version": "1.0.0",
                    "project": "x",
                    "created": "now",
                    "updated": "now",
                    "answers": {"environment": "production-saas", "has_auth": True},
                },
            )
            findings = forge_lint.lint_profile(path, self.intake_fields)
            self.assertEqual(findings, [])


class TestCLI(unittest.TestCase):
    def test_main_exits_zero_on_clean_repo(self):
        exit_code = forge_lint.main(["--root", REPO_ROOT])
        self.assertEqual(exit_code, 0)


if __name__ == "__main__":
    unittest.main()
