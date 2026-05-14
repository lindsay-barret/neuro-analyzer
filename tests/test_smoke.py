"""Smoke tests: the package imports cleanly and exposes its declared surface.

This file deliberately avoids exercising any business logic. It only
verifies that the package is importable, the version string is present,
and the entry-point objects are reachable. Failures here mean the
package is structurally broken before any feature can run.
"""

import importlib


def test_package_imports():
    importlib.import_module("neuro_analyzer")


def test_version_is_non_empty_string():
    import neuro_analyzer

    assert hasattr(neuro_analyzer, "__version__"), "neuro_analyzer must expose __version__"
    assert isinstance(neuro_analyzer.__version__, str)
    assert neuro_analyzer.__version__.strip(), "__version__ must be non-empty"


def test_cli_entry_point_is_callable():
    from neuro_analyzer.main import cli

    assert callable(cli), "neuro_analyzer.main:cli must be callable (Click group)"


def test_disclaimer_module_exposes_constant():
    from neuro_analyzer.disclaimer import DISCLAIMER_BILINGUAL

    assert isinstance(DISCLAIMER_BILINGUAL, str)
    assert DISCLAIMER_BILINGUAL.strip()
