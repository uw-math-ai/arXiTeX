"""
Shared regex machinery for the two kinds of cross-reference a statement can
carry: ``\\ref``-family commands (pointing at another ``\\label`` in the *same*
paper) and ``\\cite``-family commands (pointing at a bibliography entry, i.e.
another paper).

Kept in one place so :mod:`connect_proofs` (which walks ``\\ref``s to attach
proofs) and :mod:`dependencies` (which turns both into edges) stay in sync.
"""

import re
from typing import Iterator, List, Tuple

# \ref{...}, \Cref{...}, \autoref{...}, \eqref{...}, \hyperref[...]. The first
# alternative's inner group covers \ref, \Ref, \cref, \Cref, \vref, \autoref,
# \eqref, ...; \hyperref uses square brackets.
REF_RE = re.compile(
    r'\\(?:[a-zA-Z]*[Rr]ef|autoref|cref|Cref|eqref)\s*\{([^}]*)\}'
    r'|\\hyperref\s*\[([^\]]*)\]'
)

# \cite and its natbib/biblatex cousins, with up to two optional [..] arguments
# and a comma-separated key list. The *note* (e.g. "Theorem 3.2") is the last
# bracket before the {keys}: \cite[note]{k} or \citep[pre][note]{k}.
#   group 1: first optional bracket, if any
#   group 2: second optional bracket, if any
#   group 3: the comma-separated cite keys
CITE_RE = re.compile(
    r'\\[Cc]ite[a-zA-Z]*\s*'
    r'(?:\[([^\]]*)\])?'        # optional first bracket
    r'(?:\[([^\]]*)\])?'        # optional second bracket
    r'\s*\{([^}]*)\}'
)


def referenced_labels(text: str) -> set:
    """Labels *text* points at via ``\\ref``/``\\Cref``/``\\hyperref``/..."""
    out = set()
    for m in REF_RE.finditer(text or ""):
        for group in m.groups():
            if group:
                out.update(part.strip() for part in group.split(",") if part.strip())
    return out


def iter_citations(text: str) -> Iterator[Tuple[str, List[str], str, int]]:
    """Yield ``(note, keys, raw, start)`` for each ``\\cite`` in *text*.

    ``note`` is the second optional-bracket argument (``""`` if absent), ``keys``
    the individual cite keys, ``raw`` the full matched command, and ``start`` its
    offset in *text* (so callers can inspect the preceding prose).
    """
    for m in CITE_RE.finditer(text or ""):
        # The note is the last bracket present before the {keys}.
        note = (m.group(2) if m.group(2) is not None else (m.group(1) or "")).strip()
        keys = [k.strip() for k in (m.group(3) or "").split(",") if k.strip()]
        if keys:
            yield note, keys, m.group(0), m.start()
