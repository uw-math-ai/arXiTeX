"""
Shared context extraction for both regex and plasTeX parsers.

Given a flattened LaTeX source and a list of raw environment names in
document order, finds each \\begin{env}...\\end{env} block via a sequential
scan and returns (pre_context, post_context) character slices around it.
Both parsers use this identically so context capture is method-agnostic.
"""

import re
from typing import List, Tuple, Optional

_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
_COMMENT_ENV_RE = re.compile(r"\\begin\s*\{comment\}.*?\\end\s*\{comment\}", re.DOTALL)


def strip_comments(tex: str) -> str:
    tex = _COMMENT_ENV_RE.sub("", tex)
    return _COMMENT_RE.sub("", tex)

# Private alias for internal use and backward-compat imports
_strip_comments = strip_comments


def extract_contexts(
    flat_tex: str,
    raw_env_names: List[str],
    n: int,
) -> List[Tuple[Optional[str], Optional[str]]]:
    """
    For each environment name in `raw_env_names` (in document order), finds
    the corresponding \\begin{env}...\\end{env} in the flattened source and
    returns (pre_context, post_context) slices of up to `n` characters each.

    The scan is sequential: each search starts where the previous one ended,
    so order must match document order exactly.

    Parameters
    ----------
    flat_tex : str
        Flattened (single-file) LaTeX source.
    raw_env_names : List[str]
        Environment names as they appear in the source (e.g. "thm", "theorem*"),
        in document order.
    n : int
        Number of characters of context to capture before/after each environment.

    Returns
    -------
    List[Tuple[Optional[str], Optional[str]]]
        (pre_context, post_context) for each env; both None on lookup failure.
    """
    clean = _strip_comments(flat_tex)
    cursor = 0
    results = []

    for raw_env in raw_env_names:
        escaped = re.escape(raw_env)
        begin_re = re.compile(r"\\begin\s*\{\s*" + escaped + r"\s*\}")
        end_re   = re.compile(r"\\end\s*\{\s*"   + escaped + r"\s*\}")

        m_begin = begin_re.search(clean, cursor)
        if m_begin is None:
            results.append((None, None))
            continue

        begin_pos = m_begin.start()
        # Advance cursor to after \begin{env} — not after \end{env}.
        # If we advanced to \end{env}, outer environments (e.g. section, figure)
        # would push the cursor past all environments nested inside them, causing
        # their \begin tags to be missed on the next search.
        cursor = m_begin.end()

        m_end = end_re.search(clean, cursor)
        if m_end is None:
            results.append((None, None))
            continue

        end_pos  = m_end.end()
        pre  = clean[max(0, begin_pos - n) : begin_pos] or None
        post = clean[end_pos : end_pos + n] or None
        results.append((pre, post))

    return results
