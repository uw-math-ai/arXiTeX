"""Shared test helpers and fixture paths."""

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# Fixtures are either a directory (possibly multi-file) or a single .tex file.
FIXTURE_PATHS = {
    "simple": FIXTURES / "simple",
    "multifile": FIXTURES / "multifile",
    "thmtools": FIXTURES / "thmtools.tex",
    "proof_by_ref": FIXTURES / "proof_by_ref",
    "macros": FIXTURES / "macros.tex",
    "no_statements": FIXTURES / "no_statements",
}

# Skip decorator for tests that need a real TeX engine on PATH.
requires_tectonic = pytest.mark.skipif(
    shutil.which("tectonic") is None,
    reason="tectonic not installed; skipping real-TeX tests",
)


def by_label(statements):
    """Index statements by their \\label key."""
    return {s.label: s for s in statements if s.label}


def by_kind(statements):
    """Group statements by kind."""
    out = {}
    for s in statements:
        out.setdefault(s.kind, []).append(s)
    return out
