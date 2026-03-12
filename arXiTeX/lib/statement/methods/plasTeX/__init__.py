from pathlib import Path
from plasTeX.TeX import TeX
from typing import List
import os
import tempfile
from .use_texinputs import use_texinputs
from .parse_node import parse_node
from .use_plastex_log_capturer import use_plastex_log_capturer
from arXiTeX.types import Statement


def _iter_nodes_depth_first(node):
    """Yield all descendant nodes in document (depth-first) order."""
    for child in getattr(node, "childNodes", []):
        yield child
        yield from _iter_nodes_depth_first(child)


def parse(
    paper_dir: Path,
    main_file: Path,
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

    Returns
    -------
    statements : List[Statement]
        A list of plasTeX-parsed statements in the order they appear in the
        document. Filtering by kind (e.g. theorem, lemma, proof) is left to
        the caller.
    """
    tex = TeX()

    # Use a throwaway temp dir as cwd so any incidental files plasTeX writes
    # (e.g. .paux cross-reference caches) go there rather than to a tmpfs
    # mount or the source tree.  The directory is deleted on exit.
    with (
        use_texinputs(paper_dir),
        use_plastex_log_capturer(),
    ):
        f = open(main_file, "r", errors="ignore")
        tex.input(f)
        doc = tex.parse()
        f.close()

    statements: List[Statement] = []

    for node in _iter_nodes_depth_first(doc):
        node_name = getattr(node, "nodeName", None)
        if not node_name:
            continue

        # Only capture named environments; skip raw text/character nodes
        # whose nodeName starts with '#' (e.g. '#text', '#document').
        if node_name.startswith("#"):
            continue

        if getattr(node, "thmName", False):
            node_name = str(getattr(node, "caption", node_name)).lower()

        ref, note, label, body = parse_node(node)

        # Skip nodes that produced no body — they're not statement environments
        if not body:
            continue

        statements.append(Statement(
            kind=node_name,
            ref=ref,
            note=note,
            label=label,
            body=body,
            proof=None
        ))

    return statements