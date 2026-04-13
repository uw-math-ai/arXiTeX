import re
from typing import Collection, List, Optional
from pathlib import Path
from .log_envs import log_envs
from .flatten import flatten_tex
from arXiTeX.types import Statement
from arXiTeX.lib.statement.extract_context import strip_comments

_PROOF_BEGIN_RE = re.compile(r'\A\s*\\begin\s*\{proof\*?\}', re.IGNORECASE)
_PROOF_END_RE   = re.compile(r'\\end\s*\{proof\*?\}',        re.IGNORECASE)

# Anchored — used in _post_context to check for an immediately-following section proof
_SECTION_PROOF_IMMEDIATE_RE = re.compile(
    r'\A\s*\\(?:sub{0,2})section\*?\s*\{([^{}]*\bProof\s+of\b[^{}]*\\ref\s*\{[^{}]*\}[^{}]*)\}',
    re.IGNORECASE,
)

def _stmt_boundary_patterns(statement_kinds: Collection[str]):
    """Return (begin_pat, end_pat) for all statement kinds (including starred variants)."""
    kinds_re = "|".join(
        re.escape(k) + r"\*?" for k in sorted(statement_kinds, key=len, reverse=True)
    )
    begin_pat = re.compile(r"\\begin\s*\{\s*(?:" + kinds_re + r")\s*\}", re.IGNORECASE)
    end_pat   = re.compile(r"\\end\s*\{\s*(?:"   + kinds_re + r")\s*\}", re.IGNORECASE)
    return begin_pat, end_pat


def _pre_context(
    clean: str,
    begin_pos: int,
    n: int,
    stmt_end_pat: Optional[re.Pattern],
) -> Optional[str]:
    """Return up to n chars before begin_pos, starting after the last \\end{statement_kind}."""
    text = clean[max(0, begin_pos - n) : begin_pos]
    if stmt_end_pat:
        last = None
        for m in stmt_end_pat.finditer(text):
            last = m
        if last:
            text = text[last.end():]
    return text.strip() or None


def _post_context(
    clean: str,
    end_pos: int,
    n: int,
    stmt_begin_pat: Optional[re.Pattern],
) -> Optional[str]:
    """Return up to n chars after end_pos.

    Skips a proof that immediately follows the statement (either \\begin{proof}
    or \\section{Proof of ...\\ref{...}}), then truncates at the first
    \\begin{statement_kind} found in the window.
    """
    tail = clean[end_pos:]
    m_begin = _PROOF_BEGIN_RE.match(tail)
    if m_begin:
        m_end = _PROOF_END_RE.search(tail, m_begin.end())
        window_start = end_pos + (m_end.end() if m_end else m_begin.end())
    elif m_sec := _SECTION_PROOF_IMMEDIATE_RE.match(tail):
        window_start = end_pos + m_sec.end()
    else:
        window_start = end_pos

    text = clean[window_start : window_start + n]
    if stmt_begin_pat:
        m = stmt_begin_pat.search(text)
        if m:
            text = text[:m.start()]
    return text.strip() or None



def parse(
    paper_dir: Path,
    main_file: Path,
    context: int = 0,
    flat_tex: Optional[str] = None,
    statement_kinds: Optional[Collection[str]] = None,
) -> List[Statement]:
    if flat_tex is None:
        flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)

    envs = log_envs(flat_tex)

    if context > 0:
        clean = strip_comments(flat_tex)
        stmt_begin_pat, stmt_end_pat = (
            _stmt_boundary_patterns(statement_kinds) if statement_kinds else (None, None)
        )
        return [
            Statement(
                kind=env.env,
                ref=env.ref,
                note=env.note,
                label=env.label,
                body=env.body,
                proof=None,
                pre_context=_pre_context(clean, env.begin_pos, context, stmt_end_pat),
                post_context=_post_context(clean, env.end_pos, context, stmt_begin_pat),
            )
            for env in envs
        ]

    return [
        Statement(
            kind=env.env,
            ref=env.ref,
            note=env.note,
            label=env.label,
            body=env.body,
            proof=None,
        )
        for env in envs
    ]
