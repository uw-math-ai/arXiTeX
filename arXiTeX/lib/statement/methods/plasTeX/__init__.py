from pathlib import Path
from plasTeX.TeX import TeX
from typing import List, Optional
from .use_texinputs import use_texinputs
from .parse_node import parse_node
from .use_plastex_log_capturer import use_plastex_log_capturer
from arXiTeX.types import Statement


def _iter_nodes_with_parents(node, parent=None):
    """Yield (node, parent) pairs in depth-first document order."""
    for child in getattr(node, "childNodes", []):
        yield child, node
        yield from _iter_nodes_with_parents(child, node)


def parse(
    paper_dir: Path,
    main_file: Path,
    context: int = 0,
    flat_tex: Optional[str] = None,
    **kwargs,
) -> List[Statement]:
    """
    Parses a paper's source files into a list of Statements in document order
    using plasTeX.

    Note: plasTeX mode does **not** populate ``pre_context`` / ``post_context``
    on returned statements. Pass ``ParsingMethod.REGEX`` to ``parse_paper`` if
    pre/post context is required.

    Parameters
    ----------
    paper_dir : Path
        The path to all of a paper's source files.
    main_file : Path
        The main .tex file to parse.
    context : int
        Ignored. plasTeX mode does not support context extraction.
    flat_tex : str, optional
        Ignored. plasTeX mode does not use flattened source.

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

    for node, _ in _iter_nodes_with_parents(doc):
        raw_node_name = getattr(node, "nodeName", None)
        if not raw_node_name or raw_node_name.startswith("#"):
            continue

        node_name = raw_node_name
        if getattr(node, "thmName", False):
            node_name = str(getattr(node, "caption", node_name)).lower()

        ref, note, label, body = parse_node(node)

        if not body:
            continue

        statements.append(Statement(
            kind=node_name,
            ref=ref,
            note=note,
            label=label,
            body=body,
            proof=None,
        ))

    return statements
