"""
tex_flatten.py (Claude)
-----------------------
Flatten a multi-file LaTeX project into a single source string by
recursively resolving \\input and \\include directives.

Usage
-----
    from tex_flatten import flatten_tex

    from pathlib import Path
    source = flatten_tex(
        folder    = Path("/path/to/project"),
        main_file = Path("/path/to/project/main.tex"),
    )

API
---
    flatten_tex(folder, main_file, *, encoding="utf-8", ignore_errors=False)
        -> str

    Parameters
    ----------
    folder        : project root; used to resolve relative paths
    main_file     : the top-level .tex file
    encoding      : file encoding (default "utf-8")
    ignore_errors : if True, unresolvable \\input/\\include lines are left
                    as-is instead of raising FileNotFoundError

Notes
-----
Handles:
  - \\input{file} and \\input file  (with or without .tex extension)
  - \\include{file}                 (always adds .tex if no extension)
  - Commented-out directives        (lines where the command follows a %)
  - Recursive includes
  - Cycle detection (same file included twice → included once, then skipped)

Does NOT handle (rare in practice, fine to ignore for a fallback parser):
  - \\includeonly
  - \\input inside macro definitions
  - Inputs whose path is itself a macro expansion
"""

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Matches an uncommented \input or \include on a line.
# Group 1: command name ("input" or "include")
# Group 2: filename (with or without braces)
#
# The negative lookbehind (?<!%) is not enough on its own because the %
# might be earlier on the same line, so we strip comments first per line.
_DIRECTIVE_RE = re.compile(
    r"\\(input|include)\s*"   # command
    r"\{([^}]+)\}"            # {filename}  ← brace form
    r"|"
    r"\\(input)\s+"           # \input filename  ← space form (no braces)
    r"([^\s%{}\\]+)",         # filename ends at whitespace / comment / brace
)

_USEPACKAGE_RE = re.compile(
    r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}"  # \usepackage[opts]{name(s)}
)

_COMMENT_RE = re.compile(r"(?<!\\)%.*$")  # strip from % that isn't \%


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Remove a LaTeX comment from a single line."""
    return _COMMENT_RE.sub("", line)


def _resolve_path(filename: str, current_dir: Path, folder: Path) -> Path:
    """
    Try to locate *filename* relative to *current_dir* first, then *folder*.
    Appends '.tex' if the file has no suffix and the bare name doesn't exist.
    """
    candidates = [
        current_dir / filename,
        folder / filename,
    ]
    if not Path(filename).suffix:
        candidates += [
            current_dir / (filename + ".tex"),
            folder / (filename + ".tex"),
        ]

    for path in candidates:
        if path.is_file():
            return path.resolve()

    raise FileNotFoundError(
        f"Could not resolve \\input/\\include {{{filename!r}}} "
        f"(looked in {current_dir} and {folder})"
    )


# ---------------------------------------------------------------------------
# Core recursive expander
# ---------------------------------------------------------------------------

def _expand(
    file_path: Path,
    folder: Path,
    encoding: str,
    ignore_errors: bool,
    seen: set[Path],
) -> str:
    """Recursively expand *file_path*, tracking visited files in *seen*."""

    resolved = file_path.resolve()
    if resolved in seen:
        # Cycle or duplicate \include — skip silently (matches LaTeX behaviour)
        return f"% [tex_flatten] skipped duplicate include: {file_path.name}\n"
    seen.add(resolved)

    try:
        text = resolved.read_text(encoding=encoding)
    except UnicodeDecodeError:
        text = resolved.read_text(encoding="latin-1")

    lines = text.splitlines(keepends=True)
    out   = []

    for line in lines:
        stripped = _strip_comment(line)
        m = _DIRECTIVE_RE.search(stripped)

        if m is None:
            # Check for \usepackage with a local .sty file
            pkg_match = _USEPACKAGE_RE.search(stripped)
            inlined = False
            if pkg_match:
                for pkg_name in pkg_match.group(1).split(","):
                    pkg_name = pkg_name.strip()
                    for candidate in [resolved.parent / f"{pkg_name}.sty", folder / f"{pkg_name}.sty"]:
                        if candidate.is_file() and candidate.resolve() not in seen:
                            out.append(_expand(candidate, folder, encoding, ignore_errors, seen))
                            inlined = True
                            break
            if not inlined:
                out.append(line)
            continue

        # Extract command and filename from whichever alternative matched
        if m.group(1):                      # brace form: \input{f} or \include{f}
            cmd, fname = m.group(1), m.group(2).strip()
        else:                               # space form: \input f
            cmd, fname = m.group(3), m.group(4).strip()

        try:
            child_path = _resolve_path(fname, resolved.parent, folder)
        except FileNotFoundError:
            if ignore_errors:
                out.append(line)            # leave directive in place
                continue
            raise

        # \include adds a \clearpage before and after (LaTeX semantics)
        if cmd == "include":
            out.append("\n\\clearpage\n")

        out.append(
            _expand(child_path, folder, encoding, ignore_errors, seen)
        )

        if cmd == "include":
            out.append("\n\\clearpage\n")

    return "".join(out)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def flatten_tex(
    folder: Path,
    main_file: Path,
    *,
    encoding: str = "utf-8",
    ignore_errors: bool = False,
) -> str:
    """
    Recursively expand \\input and \\include directives and return the full
    flattened LaTeX source as a single string.

    Parameters
    ----------
    folder        : project root directory
    main_file     : path to the top-level .tex file
    encoding      : character encoding for all files (default "utf-8")
    ignore_errors : if True, leave unresolvable directives in the output
                    rather than raising FileNotFoundError
    """
    folder    = Path(folder).resolve()
    main_file = Path(main_file).resolve()
    return _expand(main_file, folder, encoding, ignore_errors, seen=set())