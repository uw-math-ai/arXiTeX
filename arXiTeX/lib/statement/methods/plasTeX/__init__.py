from pathlib import Path
from plasTeX.TeX import TeX
from typing import List, Optional
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
        Number of characters of LaTeX source to capture before/after each
        statement's environment. 0 = disabled.
    flat_tex : str, optional
        Pre-computed flattened LaTeX source. If provided, skips re-flattening
        for context extraction. Pass this from _parse_paper to avoid a second
        flatten_tex call inside the timeout window.

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
    raw_env_names: List[str] = []

    for node in _iter_nodes_depth_first(doc):
        raw_node_name = getattr(node, "nodeName", None)
        if not raw_node_name:
            continue

        # Only capture named environments; skip raw text/character nodes
        # whose nodeName starts with '#' (e.g. '#text', '#document').
        if raw_node_name.startswith("#"):
            continue

        node_name = raw_node_name
        if getattr(node, "thmName", False):
            node_name = str(getattr(node, "caption", node_name)).lower()

        ref, note, label, body = parse_node(node)

        # Skip nodes that produced no body — they're not statement environments
        if not body:
            continue

        raw_env_names.append(raw_node_name)
        statements.append(Statement(
            kind=node_name,
            ref=ref,
            note=note,
            label=label,
            body=body,
            proof=None,
        ))

    if context > 0:
        from arXiTeX.lib.statement.extract_context import extract_contexts
        if flat_tex is None:
            from arXiTeX.lib.statement.methods.regex.flatten import flatten_tex
            flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)
        contexts = extract_contexts(flat_tex, raw_env_names, context)
        statements = [
            s.model_copy(update={"pre_context": pre, "post_context": post})
            for s, (pre, post) in zip(statements, contexts)
        ]

    return statements
