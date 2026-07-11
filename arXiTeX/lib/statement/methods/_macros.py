"""
Shared helper for expanding user-defined LaTeX macros in a captured body.

Reuses the (well-tested) simple-macro collector/expander from the regex method.
The ``tex`` method uses this to expand *user* macros (\\newcommand / \\def) found
in the preamble while leaving standard LaTeX/math commands intact — giving
"expanded LaTeX" bodies without the over-expansion a raw TeX ``\\edef`` would cause.
"""

from .regex.log_envs import _collect_macros, _expand_macros


def expand_user_macros(body: str, source_for_macros: str) -> str:
    """Expand simple user macros defined in ``source_for_macros`` within ``body``.

    Parameters
    ----------
    body : str
        The statement body to expand.
    source_for_macros : str
        LaTeX source (typically the flattened source or preamble) to scan for
        ``\\newcommand`` / ``\\renewcommand`` / ``\\def`` definitions.

    Returns
    -------
    str
        ``body`` with known user macros expanded (best effort). Expansion is run
        to a fixed point up to a small iteration cap so nested macros resolve.
    """
    macros = _collect_macros(source_for_macros)
    if not macros:
        return body

    prev = None
    out = body
    for _ in range(5):
        if out == prev:
            break
        prev = out
        out = _expand_macros(out, macros)
    return out
