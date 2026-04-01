"""
Legacy assistant engine (src/assistant/).

This module predates the current architecture (core/, server/, agent loop).
It is preserved because tests/test_engine*.py, tests/test_filesystem*.py,
tests/test_session.py, and tests/test_cli.py still import from it.

Do not add new features here. New work belongs in core/ and server/.
"""
