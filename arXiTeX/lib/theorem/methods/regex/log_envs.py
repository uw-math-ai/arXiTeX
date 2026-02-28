"""
tex_env_logger.py
-----------------
Parse a flattened LaTeX source string and return a logged list of
theorem-like environments, numbered according to the counter definitions
found in the source itself.

Public API
----------
    from tex_env_logger import log_envs, Environment

    envs = log_envs(tex_source)

Each Environment has:
    env        - raw environment name (e.g. "thm")
    ref        - counter string (e.g. "2.3") or None for unnumbered envs
    note       - optional argument, e.g. [Fermat's Last Theorem], macros expanded
    label      - \\label{...} key or None
    body       - inner content, \\label stripped, macros expanded
    begin_line - 1-based line number of \\begin{env}
    end_line   - 1-based line number of \\end{env}
"""

import re
from typing import Optional
from pydantic import BaseModel


###############################################################################
# Data model
###############################################################################

class Environment(BaseModel):
    env:        str
    ref:        Optional[str] = None
    note:       Optional[str] = None
    label:      Optional[str] = None
    body:       str
    begin_line: int
    end_line:   int


###############################################################################
# Constants
###############################################################################

# Environments emitted with ref=None (unnumbered but semantically relevant).
# These are implicit amsthm/LaTeX environments not defined via \newtheorem.
_UNNUMBERED_ENVS: set[str] = {
    "proof",
}

# Environments silently dropped — purely visual/structural, never useful for
# theorem parsing. We still process their \begin tokens so the stack stays
# consistent, but they never appear in the output.
_SKIP_ENVS: set[str] = {
    "document", "filecontents",
    "verbatim", "Verbatim", "lstlisting", "minted",
    "tikzpicture", "pgfpicture",
    "figure", "figure*", "table", "table*",
    "align", "align*", "aligned",
    "equation", "equation*", "eqnarray", "eqnarray*",
    "gather", "gather*", "multline", "multline*",
    "flalign", "flalign*", "alignat", "alignat*",
    "enumerate", "itemize", "description",
    "tabular", "tabular*", "tabularx", "array",
    "minipage", "adjustbox",
    "abstract",
}

# Section hierarchy used for prefix numbering
_SECTION_LEVELS: list[str] = [
    "part", "chapter", "section", "subsection", "subsubsection", "paragraph",
]


###############################################################################
# Pre-pass helpers
###############################################################################

# ── strip comments ────────────────────────────────────────────────────────────

_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")

def _strip_comments(tex: str) -> str:
    return _COMMENT_RE.sub("", tex)


# ── macro expansion ───────────────────────────────────────────────────────────

# \newcommand{\name}{body}  or  \newcommand{\name}[n]{body}
# also matches \renewcommand with the same syntax
_NEWCMD_RE = re.compile(
    r"\\(?:re)?newcommand\s*\{\s*(\\[\w@]+)\s*\}"   # \name
    r"(?:\s*\[\s*(\d)\s*\])?"                        # optional [n]
    r"\s*\{",                                        # opening { of body
)

# \def\name{body}  (no-arg form only)
_DEF_RE = re.compile(
    r"\\(?:e|g|x)?def\s*(\\[\w@]+)\s*\{",
)

def _collect_macros(tex: str) -> dict[str, tuple[int, str]]:
    """
    Return {macro_name: (nargs, body_template)} for every simple
    \\newcommand / \\renewcommand / \\def found in *tex*.

    Only zero-arg and fixed-arg (#1..#9) commands are collected.
    Complex macros (\\def with parameter patterns) are skipped.
    """
    macros: dict[str, tuple[int, str]] = {}

    def _extract_body(tex: str, start: int) -> str:
        """Extract the balanced-brace body starting at the '{' at tex[start-1]."""
        depth = 1
        i = start
        while i < len(tex) and depth:
            c = tex[i]
            if c == "\\" :
                i += 1          # skip next char (escaped brace etc.)
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        return tex[start : i - 1]

    # \newcommand / \renewcommand
    for m in _NEWCMD_RE.finditer(tex):
        name  = m.group(1)
        nargs = int(m.group(2)) if m.group(2) else 0
        body  = _extract_body(tex, m.end())
        macros[name] = (nargs, body)

    # \def\name{body}  — zero-arg only (skip if next char after name is #)
    for m in _DEF_RE.finditer(tex):
        name = m.group(1)
        # peek: if the char right before '{' is # this is a parameterised \def
        before_brace = tex[m.start():m.end()].rstrip()
        if "#" in tex[m.end() - 5 : m.end()]:
            continue
        body = _extract_body(tex, m.end())
        if name not in macros:          # \newcommand takes priority
            macros[name] = (0, body)

    return macros


def _expand_macros(text: str, macros: dict[str, tuple[int, str]]) -> str:
    """
    Single-pass expansion of known macros in *text*.

    Zero-arg macros: \\foo  → body
    n-arg macros:    \\foo{a1}{a2} → body with #1→a1, #2→a2
    """
    if not macros or not text:
        return text

    # Build one alternation pattern sorted longest-first to avoid prefix clashes
    sorted_names = sorted(macros.keys(), key=len, reverse=True)
    pattern = re.compile(
        "(" + "|".join(re.escape(n) for n in sorted_names) + r")(?![a-zA-Z@])"
    )

    def _read_arg(s: str, pos: int) -> tuple[str, int]:
        """Read one braced argument starting at pos (skipping whitespace)."""
        while pos < len(s) and s[pos] in " \t\n":
            pos += 1
        if pos >= len(s) or s[pos] != "{":
            return ("", pos)
        depth = 1
        i = pos + 1
        while i < len(s) and depth:
            c = s[i]
            if c == "\\":
                i += 1
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            i += 1
        return (s[pos + 1 : i - 1], i)

    result = []
    pos = 0
    for m in pattern.finditer(text):
        result.append(text[pos : m.start()])
        name = m.group(1)
        nargs, tmpl = macros[name]
        cur = m.end()
        if nargs == 0:
            result.append(tmpl)
        else:
            args = []
            for _ in range(nargs):
                arg, cur = _read_arg(text, cur)
                args.append(arg)
            expanded = tmpl
            for i, arg in enumerate(args, 1):
                expanded = expanded.replace(f"#{i}", arg)
            result.append(expanded)
        pos = cur
    result.append(text[pos:])
    return "".join(result)


# ── theorem declarations ───────────────────────────────────────────────────────

# \newtheorem{env}{Display}
# \newtheorem{env}[shared]{Display}
# \newtheorem{env}{Display}[reset_level]
_NEWTHM_RE = re.compile(
    r"\\newtheorem\s*\{\s*(\w+)\s*\}"          # {env}
    r"\s*(?:\[\s*(\w+)\s*\])?"                 # optional [shared_counter]
    r"\s*\{[^}]*\}"                            # {Display name} — we don't need this
    r"\s*(?:\[\s*(\w+)\s*\])?"                 # optional [reset_level]
)

# thmtools: \declaretheorem[options]{env}
# options we care about: sibling=, numberlike=, numberwithin=
_DECLARE_THM_RE = re.compile(
    r"\\declaretheorem\s*(?:\[[^\]]*\])?\s*\{\s*(\w+)\s*\}",
    re.DOTALL,
)
_DECLARE_OPT_RE = re.compile(
    r"\\declaretheorem\s*\[([^\]]*)\]\s*\{\s*(\w+)\s*\}",
    re.DOTALL,
)

def _parse_theorem_defs(
    tex: str,
) -> dict[str, dict]:
    """
    Return a dict keyed by env name:
    {
      "thm":  {"shared": None,    "reset": None},
      "lem":  {"shared": "thm",   "reset": None},
      "prop": {"shared": None,    "reset": "section"},
    }
    All envs that share a counter are normalised so that "shared" always
    points to the *root* name (not a transitive link).
    """
    defs: dict[str, dict] = {}

    # Standard \newtheorem
    for m in _NEWTHM_RE.finditer(tex):
        env, shared, reset = m.group(1), m.group(2), m.group(3)
        defs[env] = {"shared": shared, "reset": reset}

    # \declaretheorem with options
    for m in _DECLARE_OPT_RE.finditer(tex):
        opts_str, env = m.group(1), m.group(2)
        shared = reset = None
        sib = re.search(r"(?:sibling|numberlike)\s*=\s*(\w+)", opts_str)
        nw  = re.search(r"numberwithin\s*=\s*(\w+)", opts_str)
        if sib:
            shared = sib.group(1)
        if nw:
            reset = nw.group(1)
        defs[env] = {"shared": shared, "reset": reset}

    # \declaretheorem without options (independent counter)
    for m in _DECLARE_THM_RE.finditer(tex):
        env = m.group(1)
        if env not in defs:
            defs[env] = {"shared": None, "reset": None}

    # Resolve transitive shared pointers to root
    def _root(name: str, visited: set) -> str:
        if name in visited or name not in defs:
            return name
        visited.add(name)
        parent = defs[name]["shared"]
        return _root(parent, visited) if parent else name

    for env in list(defs):
        if defs[env]["shared"]:
            defs[env]["shared"] = _root(defs[env]["shared"], set())

    return defs


###############################################################################
# Counter format pre-pass
###############################################################################

# Matches \renewcommand{\thefoo}{<format_body>}
# Also handles \renewcommand*{...}{...}
# Matches up to and including the opening { of the format body.
# We use balanced-brace extraction in _parse_counter_formats for the body
# so that nested braces (e.g. \Alph{thm}) are handled correctly.
_THECMD_RE = re.compile(
    r"\\renewcommand\s*\*?\s*\{\s*\\the(\w+)\s*\}\s*\{"
)

# LaTeX counter format commands we understand
_FMT_CMD_RE = re.compile(
    r"\\(arabic|alph|Alph|roman|Roman|fnsymbol)\s*\{\s*(\w+)\s*\}"
)

# A reference to another \the<counter> inside the format body
_THE_REF_RE = re.compile(r"\\the(\w+)")


def _int_to_roman(n: int, upper: bool = False) -> str:
    vals = [1000,900,500,400,100,90,50,40,10,9,5,4,1]
    syms = ["M","CM","D","CD","C","XC","L","XL","X","IX","V","IV","I"]
    result = ""
    for v, s in zip(vals, syms):
        while n >= v:
            result += s
            n -= v
    return result if upper else result.lower()


def _apply_format(fmt: str, n: int) -> str:
    if fmt == "arabic":  return str(n)
    elif fmt == "alph":  return chr(96 + n) if 1 <= n <= 26 else str(n)
    elif fmt == "Alph":  return chr(64 + n) if 1 <= n <= 26 else str(n)
    elif fmt == "roman": return _int_to_roman(n, upper=False)
    elif fmt == "Roman": return _int_to_roman(n, upper=True)
    elif fmt == "fnsymbol":
        symbols = ["*", "†", "‡", "§", "¶", "‖", "**", "††", "‡‡"]
        return symbols[n - 1] if 1 <= n <= len(symbols) else str(n)
    return str(n)


def _parse_counter_formats(tex: str) -> dict[str, str]:
    """
    Return {env_name: raw_format_body} for every \\renewcommand{\\the<env>}{...}
    found in *tex*.  Uses a balanced-brace extractor so that nested braces
    (e.g. \\Alph{thm}, \\thesection.\\arabic{prop}) are captured correctly.
    The format body is stored raw and evaluated at ref-generation time.
    """
    formats: dict[str, str] = {}
    for m in _THECMD_RE.finditer(tex):
        env_name = m.group(1)
        # m.end() points just past the opening '{' of the format body
        # (the regex ends with \s*\{ which consumed that brace)
        start = m.end()
        depth = 1
        i = start
        while i < len(tex) and depth:
            c = tex[i]
            if c == '\\':
                i += 1
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        body = tex[start : i - 1].strip()
        formats[env_name] = body
    return formats


###############################################################################
# Section counter tracker
###############################################################################

_SECTION_RE = re.compile(
    r"\\(" + "|".join(_SECTION_LEVELS) + r")\s*(?:\*\s*)?"
    r"(?:\[[^\]]*\])?\s*\{[^}]*\}"
)

class _SectionTracker:
    def __init__(self) -> None:
        self._counts: dict[str, int] = {l: 0 for l in _SECTION_LEVELS}

    def bump(self, level: str) -> None:
        idx = _SECTION_LEVELS.index(level)
        self._counts[level] += 1
        for deeper in _SECTION_LEVELS[idx + 1:]:
            self._counts[deeper] = 0

    def prefix(self, reset_level: Optional[str]) -> str:
        """
        Return the prefix string (e.g. "2.1.") implied by *reset_level*.
        If reset_level is None, return "".
        """
        if not reset_level or reset_level not in _SECTION_LEVELS:
            return ""
        parts: list[str] = []
        for level in _SECTION_LEVELS:
            n = self._counts[level]
            if n:
                parts.append(str(n))
            if level == reset_level:
                break
        return ".".join(parts) + "." if parts else ""


###############################################################################
# Main scanner
###############################################################################

_BEGIN_RE = re.compile(r"\\begin\s*\{\s*(\w+\*?)\s*\}")
_END_RE   = re.compile(r"\\end\s*\{\s*(\w+\*?)\s*\}")

# Optional note after \begin{env}: \begin{thm}[some note]
# Note: do NOT use \A here — we always slice the string before matching
_NOTE_RE  = re.compile(r"^\s*\[([^\]]*)\]")

# \label{key}
_LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")


def log_envs(tex: str) -> list[Environment]:
    """
    Logs all theorem-like environments from a flattened TeX source.
    Numbers each env according to \\newtheorem / \\declaretheorem definitions.
    Expands simple macros throughout.

    Parameters
    ----------
    tex : str
        Flattened TeX source.

    Returns
    -------
    List[Environment]
        One entry per theorem-like environment, in source order.
    """

    # ── 1. strip comments, build line-start index ─────────────────────────────
    clean  = _strip_comments(tex)
    # Map char offset → 1-based line number
    line_starts: list[int] = [0]
    for i, ch in enumerate(clean):
        if ch == "\n":
            line_starts.append(i + 1)

    def _lineno(pos: int) -> int:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    # ── 2. collect macro definitions (pre-pass) ───────────────────────────────
    macros = _collect_macros(clean)

    # ── 3. collect theorem definitions (pre-pass) ─────────────────────────────
    thm_defs = _parse_theorem_defs(clean)

    # ── 3b. collect counter format overrides (pre-pass) ───────────────────────
    # e.g. \renewcommand{\thethm}{\Alph{thm}}
    counter_formats = _parse_counter_formats(clean)

    # ── 4. build counter state ────────────────────────────────────────────────
    # root_counter → {prefix_string → count}
    root_counts:  dict[str, dict[str, int]] = {}
    # track last prefix seen per root so we know when to reset
    root_prefix:  dict[str, str] = {}

    section_tracker = _SectionTracker()

    def _get_root(env: str) -> Optional[str]:
        if env not in thm_defs:
            return None
        info = thm_defs[env]
        return info["shared"] if info["shared"] else env

    def _render_format(env: str, root: str, n: int) -> str:
        """
        Render the ref string for *env* with current count *n*, respecting
        any \renewcommand{\the<env>}{...} override.

        Falls back to plain arabic if no override is found.

        Handles composite formats like \thesection.\arabic{prop} by
        recursively resolving \the<counter> references using live section
        counter values.
        """
        # Look up format body: prefer override on env, then on root
        fmt_body = counter_formats.get(env) or counter_formats.get(root)

        if not fmt_body:
            # No override — use the reset-level prefix + arabic by default
            reset_level = thm_defs[root].get("reset") or thm_defs[env].get("reset")
            prefix = section_tracker.prefix(reset_level)
            return f"{prefix}{n}"

        result = fmt_body

        # Replace \the<level> references (e.g. \thesection) with live values
        def _replace_the(m: re.Match) -> str:
            ref_name = m.group(1)   # e.g. "section"
            if ref_name in _SECTION_LEVELS:
                return str(section_tracker._counts.get(ref_name, 0))
            # Could be another theorem counter — leave as-is for now
            return m.group(0)

        result = _THE_REF_RE.sub(_replace_the, result)

        # Replace \arabic{x}, \Alph{x}, etc.
        def _replace_fmt(m: re.Match) -> str:
            fmt_cmd  = m.group(1)   # e.g. "Alph"
            ctr_name = m.group(2)   # e.g. "thm"
            # The counter this format applies to — use n if it matches root/env
            if ctr_name in (env, root):
                val = n
            elif ctr_name in _SECTION_LEVELS:
                val = section_tracker._counts.get(ctr_name, 0)
            else:
                val = 0
            return _apply_format(fmt_cmd, val)

        result = _FMT_CMD_RE.sub(_replace_fmt, result)
        return result.strip(".")

    def _infer_reset_level(env: str, root: str) -> Optional[str]:
        """
        Determine the reset level for this env/root counter by checking:
          1. Explicit declaration in \newtheorem{...}{...}[level]
          2. \the<level> reference inside a \renewcommand{\the<env>}{...} body
        Returns the deepest section level implied, or None.
        """
        explicit = thm_defs[root].get("reset") or thm_defs[env].get("reset")
        if explicit:
            return explicit
        # Check format body for \the<level> references
        fmt_body = counter_formats.get(env) or counter_formats.get(root) or ""
        deepest = None
        for m in _THE_REF_RE.finditer(fmt_body):
            ref_name = m.group(1)
            if ref_name in _SECTION_LEVELS:
                if deepest is None or _SECTION_LEVELS.index(ref_name) > _SECTION_LEVELS.index(deepest):
                    deepest = ref_name
        return deepest

    def _next_ref(env: str) -> Optional[str]:
        root = _get_root(env)
        if root is None:
            return None
        reset_level = _infer_reset_level(env, root)
        prefix = section_tracker.prefix(reset_level)

        if root not in root_counts:
            root_counts[root] = {}
            root_prefix[root] = prefix

        # Reset counter when section prefix changes
        if root_prefix[root] != prefix:
            root_counts[root] = {}
            root_prefix[root] = prefix

        root_counts[root][prefix] = root_counts[root].get(prefix, 0) + 1
        n = root_counts[root][prefix]
        return _render_format(env, root, n)

    # ── 5. linear scan with stack ─────────────────────────────────────────────
    results:  list[Environment] = []
    # stack entries: (env_name, body_start_pos, begin_line, note)
    stack:    list[tuple[str, int, int, Optional[str]]] = []
    # merge begin/end token stream
    tokens = sorted(
        [("begin", m.group(1), m.start(), m.end()) for m in _BEGIN_RE.finditer(clean)]
        + [("end",  m.group(1), m.start(), m.end()) for m in _END_RE.finditer(clean)],
        key=lambda t: t[2],
    )

    # We also need section bumps interleaved — collect them
    section_events = [
        ("section", m.group(1), m.start())
        for m in _SECTION_RE.finditer(clean)
    ]
    sec_idx = 0

    for kind, env, tok_start, tok_end in tokens:

        # Advance section tracker past any sections before this token
        while sec_idx < len(section_events) and section_events[sec_idx][2] < tok_start:
            _, sec_level, _ = section_events[sec_idx]
            section_tracker.bump(sec_level)
            sec_idx += 1

        if kind == "begin":
            # Check for optional note argument immediately after \begin{env}
            # Slice first — \A / ^ anchors don't work correctly with pos= argument
            after_begin = clean[tok_end:]
            note_match  = _NOTE_RE.match(after_begin)
            note_raw    = note_match.group(1).strip() if note_match else None
            note        = _expand_macros(note_raw, macros) if note_raw else None

            body_start  = tok_end + note_match.end() if note_match else tok_end
            stack.append((env, body_start, _lineno(tok_start), note))

        elif kind == "end":
            # Find matching open on stack (search backwards for robustness)
            match_idx = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == env:
                    match_idx = i
                    break
            if match_idx is None:
                continue  # unmatched \end — skip

            open_env, body_start, begin_line, note = stack.pop(match_idx)
            end_line = _lineno(tok_start)

            # Three-tier filter:
            #   _SKIP_ENVS       → drop silently (visual/structural junk)
            #   thm_defs         → emit with computed ref
            #   _UNNUMBERED_ENVS → emit with ref=None
            #   anything else    → emit with ref=None (unknown, retained for safety)
            if open_env in _SKIP_ENVS:
                continue

            raw_body = clean[body_start:tok_start]

            # Extract and remove \label
            label_m = _LABEL_RE.search(raw_body)
            label   = label_m.group(1).strip() if label_m else None
            body    = _LABEL_RE.sub("", raw_body).strip()

            # Expand macros
            body = _expand_macros(body, macros)

            # ref: computed for known theorem envs, None for everything else
            ref = _next_ref(open_env) if open_env in thm_defs else None

            results.append(Environment(
                env        = open_env,
                ref        = ref,
                note       = note,
                label      = label,
                body       = body,
                begin_line = begin_line,
                end_line   = end_line,
            ))

    return results