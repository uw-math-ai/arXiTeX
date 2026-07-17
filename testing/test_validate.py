"""Statement validation heuristics (truncation, math balance)."""

import pytest

from arxitex.lib.statement.validate_statements import validate_statement
from arxitex.types import Statement


def _check(body):
    validate_statement(Statement(kind="remark", body=body))


def test_a_complete_statement_ending_in_a_colon_is_not_truncated():
    # A statement can only end on a colon when \end{env} follows it, i.e. the
    # colon introduces content *outside* the env (a display or a following
    # theorem). That is complete. Mirrors the Remark 1.8 of arXiv:2402.10823.
    _check(
        "The connectedness assumption is not essential. On the other hand, the "
        "theorem does extend to the nonreduced case if we modify the hypotheses:"
    )


def test_genuine_truncation_still_flagged():
    for tail in [
        "Let $X$ be a scheme such that",
        "There exists a group $G$ and",
        "Consider the following diagram where",
        "The morphism factors through the quotient stack and equals =",
        "Take the open cover of the scheme given by (",
    ]:
        with pytest.raises(ValueError, match="truncated"):
            _check(tail)


def test_unbalanced_math_delimiters_flagged():
    with pytest.raises(ValueError, match="unbalanced"):
        _check("The quantity $x + y is always positive and well defined.")


def test_empty_and_too_short_bodies_flagged():
    with pytest.raises(ValueError, match="empty"):
        _check("   ")
    with pytest.raises(ValueError, match="too short"):
        _check("short")


def test_ordinary_complete_statement_passes():
    _check("Every bounded monotone sequence of real numbers converges to a finite limit.")
