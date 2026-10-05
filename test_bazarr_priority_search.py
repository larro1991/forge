#!/usr/bin/env python3
"""Tests for bazarr_priority_search.py's API key handling.

The script does real sqlite3/network work at import time, so these tests
only exercise the safe, side-effect-free path: BAZARR_API_KEY unset, which
must exit before anything touches the database or network.
"""

import os
import re
import subprocess
import sys
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bazarr_priority_search.py")


class TestBazarrApiKeyRequired(unittest.TestCase):
    def _run_without_key(self):
        env = {k: v for k, v in os.environ.items() if k != "BAZARR_API_KEY"}
        return subprocess.run(
            [sys.executable, SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
        )

    def test_exits_nonzero_when_unset(self):
        result = self._run_without_key()
        self.assertNotEqual(result.returncode, 0)

    def test_error_message_mentions_env_var(self):
        result = self._run_without_key()
        self.assertIn("BAZARR_API_KEY", result.stdout + result.stderr)

    def test_no_hardcoded_key_literal_in_source(self):
        with open(SCRIPT, encoding="utf-8") as f:
            source = f.read()
        # API_KEY must be sourced from the environment, never a string literal.
        self.assertIsNone(re.search(r'API_KEY\s*=\s*["\']', source))
        self.assertIn('os.environ.get("BAZARR_API_KEY")', source)


if __name__ == "__main__":
    unittest.main()
