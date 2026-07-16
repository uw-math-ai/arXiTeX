"""
Text normalization for the eval.

Two jobs:

* ``norm_body`` — canonicalize a full LaTeX body so equivalent bodies from
  different parsers (which differ only in benign spacing around math, control
  words, and braces) compare equal. Used by the exhaustive ``tex`` comparison.

* ``to_words`` / ``overlap`` — reduce a body to math-free prose tokens and score
  snippet overlap. Used by the lenient ``pdf`` comparison, where ground truth
  stores only a few words from the start/end of each body.
"""

from __future__ import annotations

import re

# --- full-body canonicalization (tex mode) --------------------------------

_WS = re.compile(r"\s+")
# Space after a control word, before a "{" or "\" — insignificant to TeX.
_CS_SPACE = re.compile(r"(\\[A-Za-z@]+) +(?=[{\\])")
# Spaces around math punctuation ($ ^ _) — a detokenize/spacing artifact.
_MATH_PUNCT = re.compile(r" *([\^_$]) *")


def norm_body(text: str | None) -> str | None:
    """Canonicalize a LaTeX body for equality comparison across parsers."""
    if text is None:
        return None
    text = _WS.sub(" ", text)
    text = _CS_SPACE.sub(r"\1", text)
    text = _MATH_PUNCT.sub(r"\1", text)
    return text.strip()


# --- math-free prose tokens (pdf mode) ------------------------------------

_MATH_ENVS = ("equation", "align", "gather", "multline", "eqnarray", "displaymath", "math", "split")
_MATH_ENV_RE = re.compile(
    r"\\begin\s*\{(" + "|".join(_MATH_ENVS) + r")\*?\}.*?\\end\s*\{\1\*?\}",
    re.DOTALL,
)
_INLINE_MATH_RES = [
    re.compile(r"\$\$.*?\$\$", re.DOTALL),
    re.compile(r"\$.*?\$", re.DOTALL),
    re.compile(r"\\\(.*?\\\)", re.DOTALL),
    re.compile(r"\\\[.*?\\\]", re.DOTALL),
]
_LABEL_REF_RE = re.compile(r"\\(?:label|ref|eqref|cite|autoref|cref|Cref)\s*\{[^}]*\}")
_CMD_RE = re.compile(r"\\[a-zA-Z@]+\*?")
_NONWORD_RE = re.compile(r"[^a-z0-9]+")


def strip_math(text: str) -> str:
    """Remove display-math environments and inline/display math delimiters."""
    text = _MATH_ENV_RE.sub(" ", text)
    for r in _INLINE_MATH_RES:
        text = r.sub(" ", text)
    return text


def to_words(text: str) -> list[str]:
    """Reduce a LaTeX body (or a ground-truth snippet) to lowercase prose tokens."""
    if not text:
        return []
    text = _LABEL_REF_RE.sub(" ", text)
    text = strip_math(text)
    text = _CMD_RE.sub(" ", text)                 # drop control words, keep brace contents
    text = text.replace("{", " ").replace("}", " ").replace("~", " ")
    text = text.lower()
    return [w for w in _NONWORD_RE.split(text) if w]


def overlap(needle: list[str], haystack: list[str]) -> float:
    """Fraction of *needle* tokens (as a multiset) also present in *haystack*."""
    if not needle:
        return 1.0
    hay = list(haystack)
    found = 0
    for w in needle:
        if w in hay:
            hay.remove(w)          # consume so repeated words need repeated matches
            found += 1
    return found / len(needle)
