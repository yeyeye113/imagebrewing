"""Quant-Trader Security Test Module.

Defensive security testing for the quant-trader API server.
All tests are non-destructive -- read-only probes against a running server.

Usage:
    # Run all tests
    python -m quanttrader.security_test

    # Run specific test suite
    python -m quanttrader.security_test.api_test
    python -m quanttrader.security_test.auth_test
    python -m quanttrader.security_test.config_test
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

# Ensure project root is on sys.path so tests can import siblings
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)


def load_all_tests() -> unittest.TestSuite:
    """Discover and return all security test cases."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    # Import each module to register its test classes
    from . import api_test, auth_test, config_test

    for mod in (api_test, auth_test, config_test):
        suite.addTests(loader.loadTestsFromModule(mod))
    return suite


if __name__ == "__main__":
    unittest.TextTestRunner(verbosity=2).run(load_all_tests())
