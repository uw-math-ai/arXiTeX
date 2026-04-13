from pathlib import Path
from plasTeX.TeX import TeX
from typing import List, Optional, Tuple
from .use_texinputs import use_texinputs
from .parse_node import parse_node
from .use_plastex_log_capturer import use_plastex_log_capturer
from arXiTeX.types import Statement


def _iter_nodes_with_parents(node, parent=None):
    """Yield (node, parent) pairs in depth-first document order."""
    for child in getattr(node, "childNodes", []):
        yield child, node
        yield from _iter_nodes_with_parents(child, node)


def _node_source(node) -> str:
    return getattr(node, "source", None) or getattr(node, "textContent", None) or ""


def _get_sibling_context(stmt_node, parent) -> Tuple[Optional[str], Optional[str]]:
    """Return (pre_context, post_context) by walking the statement's siblings.

    Collects source text from adjacent #text and par siblings, stopping as
    soon as any other named environment is encountered — that boundary acts
    as a paragraph break.  Siblings are collected in natural document order.
    """
    if parent is None:
        return None, None

    siblings = list(getattr(parent, "childNodes", []))
    try:
        idx = next(i for i, s in enumerate(siblings) if s is stmt_node)
    except StopIteration:
        return None, None

    def _is_env(node) -> bool:
        """True when the node is a named environment (not bare text or par)."""
        name = getattr(node, "nodeName", "") or ""
        return bool(name) and not name.startswith("#") and name != "par"

    # Pre-context: walk backwards, accumulate in reverse, then flip.
    pre_parts: List[str] = []
    for sib in reversed(siblings[:idx]):
        if _is_env(sib):
            break
        src = _node_source(sib).strip()
        if src:
            pre_parts.insert(0, src)

    # Post-context: if the first environment sibling is a proof, skip past it.
    post_start = idx + 1
    for i in range(idx + 1, len(siblings)):
        sib = siblings[i]
        if _is_env(sib):
            name = (getattr(sib, "nodeName", "") or "").lower().rstrip("*")
            if name == "proof":
                post_start = i + 1
            break  # stop scanning regardless — only skip a leading proof

    post_parts: List[str] = []
    for sib in siblings[post_start:]:
        if _is_env(sib):
            break
        src = _node_source(sib).strip()
        if src:
            post_parts.append(src)

    pre_context  = " ".join(pre_parts).strip()  or None
    post_context = " ".join(post_parts).strip() or None
    return pre_context, post_context


def _cap(text: Optional[str], n: int) -> Optional[str]:
    """Truncate text to at most n characters, or return as-is if n <= 0."""
    if text is None or n <= 0:
        return text
    return text[:n] or None


def parse(
    paper_dir: Path,
    main_file: Path,
    context: int = 0,
    flat_tex: Optional[str] = None,
) -> List[Statement]:
    """
    Parses a paper's source files into a list of Statements in document order
    using plasTeX.

    Parameters
    ----------
    paper_dir : Path
        The path to all of a paper's source files
    main_file : Path
        The main .tex file to parse
    context : int
        When > 0, pre/post context is captured for each statement by walking
        the DOM sibling nodes (the flat_tex parameter is ignored for plasTeX).
    flat_tex : str, optional
        Unused for plasTeX (kept for API compatibility with the regex parser).

    Returns
    -------
    statements : List[Statement]
        A list of plasTeX-parsed statements in the order they appear in the
        document. Filtering by kind is left to the caller.
    """
    tex = TeX()

    with (
        use_texinputs(paper_dir),
        use_plastex_log_capturer(),
    ):
        f = open(main_file, "r", errors="ignore")
        tex.input(f)
        doc = tex.parse()
        f.close()

    statements: List[Statement] = []
    # (node, parent) pairs corresponding to each collected statement, used for
    # context extraction below.
    stmt_node_parents: List[Tuple] = []

    for node, parent in _iter_nodes_with_parents(doc):
        raw_node_name = getattr(node, "nodeName", None)
        if not raw_node_name or raw_node_name.startswith("#"):
            continue

        node_name = raw_node_name
        if getattr(node, "thmName", False):
            node_name = str(getattr(node, "caption", node_name)).lower()

        ref, note, label, body = parse_node(node)

        if not body:
            continue

        stmt_node_parents.append((node, parent))
        statements.append(Statement(
            kind=node_name,
            ref=ref,
            note=note,
            label=label,
            body=body,
            proof=None,
        ))

    if context > 0:
        statements = [
            s.model_copy(update={
                "pre_context":  _cap(pre,  context),
                "post_context": _cap(post, context),
            })
            for s, (node, parent) in zip(statements, stmt_node_parents)
            for pre, post in [_get_sibling_context(node, parent)]
        ]

    return statements
