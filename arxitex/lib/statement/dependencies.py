"""
Turn the cross-references a statement carries into explicit dependency edges.

Two kinds, both deterministic (no LLM, no network):

- **Intra-paper**: a ``\\ref``/``\\cref``/... that resolves to another statement's
  ``\\label`` in the same paper.
- **Inter-paper**: a ``\\cite`` that resolves (via the bibliography) to another,
  cited paper — plus a best-effort name of the specific result cited
  (e.g. ``"Theorem 3.2"``) drawn from the ``\\cite`` optional argument or the
  prose right before it.

Run on the *final* statement list (proofs already attached into ``stmt.proof``
and the standalone ``proof`` statements removed), so a proof's references are
found on its theorem via ``stmt.proof``.
"""

import re
from typing import Dict, List, Optional

from arxitex.types import Statement, Dependency, DependencyScope
from .refs import referenced_labels, iter_citations

# Synthetic labels the regex method assigns to label-less nested statements when
# it splices them out of a parent — never a real cross-reference.
_SYNTHETIC_LABEL_PREFIX = "inner-"

# A named result sitting just before a \cite: "Theorem 3.2", "Lemma~2.1", ...
# Captured from a short window ending at the \cite, so "by Lemma 2.1 of \cite{x}"
# yields "Lemma 2.1".
_KIND_WORD = (
    r"Theorem|Lemma|Proposition|Corollary|Definition|Claim|Conjecture|"
    r"Remark|Example|Section|Equation|Eq"
)
_PRECEDING_NAME_RE = re.compile(
    r"(?P<kind>" + _KIND_WORD + r")\.?~?\s*(?P<num>[0-9A-Z][0-9A-Za-z.]*)"
    r"(?:\s+(?:of|in|from|by))?"   # optional connector, e.g. "Lemma 2.1 of \cite"
    r"\W*$",
    re.IGNORECASE,
)
# How far back to look for a preceding named result.
_PRECEDING_WINDOW = 40


def _inside(inner: Statement, outer: Statement) -> bool:
    """Whether *inner*'s span sits within *outer*'s (when both are known)."""
    if None in (inner.begin_pos, inner.end_pos, outer.begin_pos, outer.end_pos):
        return False
    return outer.begin_pos < inner.begin_pos and inner.end_pos <= outer.end_pos


def _label_index(statements: List[Statement]) -> Dict[str, int]:
    """Map every real ``\\label`` to the index of the statement carrying it
    (first wins, matching :mod:`connect_proofs`)."""
    label_to_idx: Dict[str, int] = {}
    for idx, statement in enumerate(statements):
        for label in statement.labels:
            if label.startswith(_SYNTHETIC_LABEL_PREFIX):
                continue
            label_to_idx.setdefault(label, idx)
    return label_to_idx


def _preceding_name(text: str, cite_start: int) -> Optional[str]:
    """A "Theorem 3.2"-style name in the ``\\cite``'s immediate lead-in, if any."""
    window = text[max(0, cite_start - _PRECEDING_WINDOW):cite_start]
    m = _PRECEDING_NAME_RE.search(window)
    if not m:
        return None
    return f"{m.group('kind').capitalize()} {m.group('num')}"


def _intra_edges(
    i: int,
    statement: Statement,
    origin: str,
    text: str,
    statements: List[Statement],
    label_to_idx: Dict[str, int],
) -> List[Dependency]:
    edges: List[Dependency] = []
    for label in referenced_labels(text):
        j = label_to_idx.get(label)
        if j is None or j == i:
            continue                       # unresolved (e.g. \eqref) or self-ref
        if _inside(statements[j], statement):
            continue                       # the \ref{child} nesting splices in
        edges.append(Dependency(
            source_index=i,
            scope=DependencyScope.INTRA,
            origin=origin,
            raw=f"\\ref{{{label}}}",
            target_index=j,
            target_label=label,
        ))
    return edges


def _inter_edges(
    i: int,
    origin: str,
    text: str,
    bibliography: Dict[str, dict],
) -> List[Dependency]:
    edges: List[Dependency] = []
    for note, keys, raw, start in iter_citations(text):
        name = note or _preceding_name(text, start)
        for key in keys:
            meta = bibliography.get(key) or {}
            edges.append(Dependency(
                source_index=i,
                scope=DependencyScope.INTER,
                origin=origin,
                raw=raw,
                cite_key=key,
                target_arxiv_id=meta.get("arxiv_id"),
                target_title=meta.get("title"),
                target_name=name,
            ))
    return edges


def resolve_dependencies(
    statements: List[Statement],
    bibliography: Optional[Dict[str, dict]] = None,
) -> List[Dependency]:
    """Extract intra- and inter-paper dependency edges from *statements*.

    Parameters
    ----------
    statements : list of Statement
        The final statements (proofs attached), in document order.
    bibliography : dict, optional
        ``cite_key -> {"title", "arxiv_id"}`` (as produced by
        :func:`arxitex.lib.paper.bibliography.parse_bibliography_from_dir`). Used
        only to enrich inter-paper edges; missing keys still yield an edge.

    Returns
    -------
    list of Dependency
        Deduplicated edges, in ``(source_index, origin)`` scan order.
    """
    bibliography = bibliography or {}
    label_to_idx = _label_index(statements)

    edges: List[Dependency] = []
    for i, statement in enumerate(statements):
        for origin, text in (
            ("body", statement.body),
            ("note", statement.note),
            ("proof", statement.proof),
        ):
            if not text:
                continue
            edges += _intra_edges(i, statement, origin, text, statements, label_to_idx)
            edges += _inter_edges(i, origin, text, bibliography)

    # De-duplicate identical edges (a label/cite repeated within the same text).
    seen = set()
    unique: List[Dependency] = []
    for e in edges:
        key = (
            e.source_index, e.scope, e.origin, e.target_index,
            e.target_label, e.cite_key, e.target_name,
        )
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique
