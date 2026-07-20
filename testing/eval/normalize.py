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


# --- comparable word tokens (pdf mode) ------------------------------------

# Commands that only control presentation or structure. A reader never
# transcribes their *name*, so drop the name but keep whatever they wrap.
_LAYOUT_CMDS = frozenset("""
    left right middle
    big bigl bigr bigm Big Bigl Bigr Bigm bigg biggl biggr Bigg Biggl Biggr
    quad qquad enspace thinspace hspace vspace phantom hphantom vphantom
    displaystyle textstyle scriptstyle scriptscriptstyle limits nolimits
    mathbf mathrm mathcal mathbb mathfrak mathsf mathtt mathit mathnormal
    boldsymbol pmb bm textbf textit textrm texttt textsf textnormal emph text
    mbox hbox operatorname ensuremath
    bf rm it sf tt em normalfont itshape bfseries
    frac dfrac tfrac cfrac over atop binom choose sqrt
    nonumber notag
""".split())

_LABEL_REF_RE = re.compile(r"\\(?:label|ref|eqref|cite|autoref|cref|Cref)\s*\{[^}]*\}")
_ENV_WRAPPER_RE = re.compile(r"\\(?:begin|end)\s*\{[^}]*\}")
_MATH_DELIM_RE = re.compile(r"\$\$|\$|\\\[|\\\]|\\\(|\\\)")
_CMD_RE = re.compile(r"\\([a-zA-Z@]+)\*?")
_NONWORD_RE = re.compile(r"[^a-z0-9]+")


def _cmd_word(m: re.Match) -> str:
    """Layout commands contribute nothing; any other keeps its name as a word,
    so ``\\omega`` becomes "omega" — what an annotator would write."""
    return " " if m.group(1) in _LAYOUT_CMDS else f" {m.group(1)} "


def to_words(text: str) -> list[str]:
    """Reduce a LaTeX body (or an annotation snippet) to comparable word tokens.

    Math is deliberately **not** discarded. Annotations spell a symbol out as a
    word, else a letter, else a number, so the parsed side has to surface those
    too — otherwise a statement whose body is all math has nothing to match on.
    ``$s_{\\mathbf{u}}(\\Delta_p)$`` becomes ``["s", "u", "delta", "p"]``.
    """
    if not text:
        return []
    text = _LABEL_REF_RE.sub(" ", text)
    text = _ENV_WRAPPER_RE.sub(" ", text)     # \begin{align} wrappers, keep the content
    text = _MATH_DELIM_RE.sub(" ", text)      # $ \[ \] \( \) — delimiters only
    text = _CMD_RE.sub(_cmd_word, text)
    text = text.replace("{", " ").replace("}", " ").replace("~", " ")
    return [w for w in _NONWORD_RE.split(text.lower()) if w]


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
