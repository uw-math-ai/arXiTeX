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
from pydantic import BaseModel, field_validator


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

    @field_validator("env", "ref", "note", "label", "body", mode="before")
    @classmethod
    def strip_nul(cls, v: object) -> object:
        return v.replace("\x00", "") if isinstance(v, str) else v


###############################################################################
# Constants
###############################################################################



# Section hierarchy used for prefix numbering
_SECTION_LEVELS: list[str] = [
    "part", "chapter", "section", "subsection", "subsubsection", "paragraph",
]


###############################################################################
# Pre-pass helpers
###############################################################################

# ── strip comments ────────────────────────────────────────────────────────────

_COMMENT_RE = re.compile(r"(?<!\\)%[^\n]*")
_COMMENT_ENV_RE = re.compile(r"\\begin\s*\{comment\}.*?\\end\s*\{comment\}", re.DOTALL)

def _strip_comments(tex: str) -> str:
    tex = _COMMENT_ENV_RE.sub("", tex)
    return _COMMENT_RE.sub("", tex)


# ── macro expansion ───────────────────────────────────────────────────────────

# \newcommand{\name}{body}  or  \newcommand{\name}[n]{body}
# also matches \renewcommand with the same syntax
_NEWCMD_RE = re.compile(
    r"\\(?:re|provide)?newcommand\s*\*?\s*\{\s*(\\[\w@]+)\s*\}"   # \name
    r"(?:\s*\[\s*(\d)\s*\])?"                                      # optional [n]
    r"\s*\{",                                                      # opening { of body
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
    r"\s*\{([^}]*)\}"                          # {Display name}
    r"\s*(?:\[\s*(\w+)\s*\])?"                 # optional [reset_level]
)

# \newtheorem*{env}{Display}  — unnumbered variant
_NEWTHM_STAR_RE = re.compile(
    r"\\newtheorem\*\s*\{\s*(\w+)\s*\}\s*\{([^}]*)\}"
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

# amsmath: \numberwithin{counter}{section-level}
_NUMBERWITHIN_RE = re.compile(
    r"\\numberwithin\s*\{\s*(\w+)\s*\}\s*\{\s*(\w+)\s*\}"
)

# aliascnt: \newaliascnt{new}{existing}
# Makes 'new' a counter alias for 'existing' — they share the same value.
# Typically followed by \newtheorem{new}[new]{...} + \aliascntresetthe{new}.
_ALIASCNT_RE = re.compile(
    r"\\newaliascnt\s*\{\s*(\w+)\s*\}\s*\{\s*(\w+)\s*\}"
)

# \newenvironment{name} — detects wrapper environments around aliased theorems
_NEWENV_RE = re.compile(r"\\newenvironment\s*\{\s*(\w+)\s*\}")

def _parse_theorem_defs(
    tex: str,
) -> dict[str, dict]:
    """
    Return a dict keyed by env name:
    {
      "thm":  {"shared": None,    "reset": None,      "display": "Theorem",  "unnumbered": False},
      "lem":  {"shared": "thm",   "reset": None,      "display": "Lemma",    "unnumbered": False},
      "prop": {"shared": None,    "reset": "section", "display": "Proposition", "unnumbered": False},
      "rmk*": {"shared": None,    "reset": None,      "display": "Remark",   "unnumbered": True},
    }
    All envs that share a counter are normalised so that "shared" always
    points to the *root* name (not a transitive link).
    """
    defs: dict[str, dict] = {}

    # Build alias map from \newaliascnt{new}{existing} — must come before
    # \newtheorem parsing so shared-counter pointers can be resolved through it.
    # alias_map[new] = existing
    alias_map: dict[str, str] = {}
    for m in _ALIASCNT_RE.finditer(tex):
        alias_map[m.group(1)] = m.group(2)

    def _resolve_alias(name: str, visited: set) -> str:
        """Follow alias chains to the ultimate target."""
        if name in visited or name not in alias_map:
            return name
        visited.add(name)
        return _resolve_alias(alias_map[name], visited)

    # Maps env -> raw (pre-resolution) shared counter name, for display name lookup later.
    raw_shared_map: dict[str, str] = {}

    # Standard \newtheorem — groups: 1=env, 2=shared, 3=display, 4=reset
    for m in _NEWTHM_RE.finditer(tex):
        env, shared, display, reset = m.group(1), m.group(2), m.group(3), m.group(4)
        # If the shared counter is itself an alias, follow the chain.
        if shared:
            raw_shared_map[env] = shared
            shared = _resolve_alias(shared, set())
        # If the env name is an aliascnt alias and no explicit shared counter
        # was given, treat it as sharing the alias target.
        elif env in alias_map:
            shared = _resolve_alias(env, set())
        defs[env] = {"shared": shared, "reset": reset, "display": display.strip(), "unnumbered": False}

    # \newtheorem* — unnumbered; display name still useful for env normalisation
    for m in _NEWTHM_STAR_RE.finditer(tex):
        env, display = m.group(1), m.group(2)
        defs[env] = {"shared": None, "reset": None, "display": display.strip(), "unnumbered": True}

    # \declaretheorem with options
    for m in _DECLARE_OPT_RE.finditer(tex):
        opts_str, env = m.group(1), m.group(2)
        shared = reset = None
        sib  = re.search(r"(?:sibling|numberlike)\s*=\s*(\w+)", opts_str)
        nw   = re.search(r"numberwithin\s*=\s*(\w+)", opts_str)
        name = re.search(r"name\s*=\s*\{([^}]*)\}", opts_str)
        nonum = re.search(r"numbered\s*=\s*no", opts_str)
        if sib:
            shared = _resolve_alias(sib.group(1), set())
        elif env in alias_map:
            shared = _resolve_alias(env, set())
        if nw:
            reset = nw.group(1)
        defs[env] = {
            "shared": shared, "reset": reset,
            "display": name.group(1).strip() if name else env,
            "unnumbered": bool(nonum),
        }

    # \declaretheorem without options (independent counter)
    for m in _DECLARE_THM_RE.finditer(tex):
        env = m.group(1)
        if env not in defs:
            shared = _resolve_alias(env, set()) if env in alias_map else None
            defs[env] = {"shared": shared, "reset": None, "display": env, "unnumbered": False}

    # \numberwithin{counter}{level} — override reset level for any known env
    for m in _NUMBERWITHIN_RE.finditer(tex):
        env, level = m.group(1), m.group(2)
        if env in defs:
            defs[env]["reset"] = level

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

    # Handle \newenvironment wrappers around aliased theorem counters.
    # Pattern: \newaliascnt{X}{Y} + \newenvironment{X}{...} where X is never
    # declared via \newtheorem directly. X must share Y's counter so that
    # \begin{X} in source gets properly numbered.
    newenv_names = {m.group(1) for m in _NEWENV_RE.finditer(tex)}
    for name, target in alias_map.items():
        if name in defs or name not in newenv_names:
            continue
        root = _resolve_alias(name, set())
        # Find the \newtheorem whose raw [shared] argument was exactly `name`
        # (e.g. \newtheorem{examplex}[example]{Example} → raw_shared="example").
        # This is the pairing convention and avoids matching other envs that
        # happen to share the same root counter (e.g. lemma).
        display = name
        for env, raw_shared in raw_shared_map.items():
            if raw_shared == name:
                display = defs[env]["display"]
                break
        defs[name] = {
            "shared": root,
            "reset": defs.get(root, {}).get("reset"),
            "display": display,
            "unnumbered": False,
        }

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
# Unified counter bank (mirrors plasTeX's Counter + resetby cascading)
###############################################################################

_SECTION_RE = re.compile(
    r"\\(" + "|".join(_SECTION_LEVELS) + r")\b\s*(\*)?"
    r"(?:\[[^\]]*\])?\s*\{"
)

# \setcounter{name}{value}  \addtocounter{name}{value}  \stepcounter{name}
_SETCOUNTER_RE = re.compile(r"\\setcounter\s*\{\s*(\w+)\s*\}\s*\{\s*(-?\d+)\s*\}")
_ADDTOCOUNTER_RE = re.compile(r"\\addtocounter\s*\{\s*(\w+)\s*\}\s*\{\s*(-?\d+)\s*\}")
_STEPCOUNTER_RE = re.compile(r"\\(?:step|refstep)counter\s*\{\s*(\w+)\s*\}")


class _CounterBank:
    """
    Mirrors plasTeX's Counter + Context counter machinery.

    Each counter has a value and an optional resetby parent.  Stepping a
    counter cascades resets to all (transitive) dependents — exactly as
    plasTeX's Counter.resetcounters() does.
    """

    def __init__(self) -> None:
        self._values:  dict[str, int]           = {}
        self._resetby: dict[str, Optional[str]] = {}

    def declare(self, name: str, resetby: Optional[str] = None, initial: int = 0) -> None:
        if name not in self._values:
            self._values[name]  = initial
            self._resetby[name] = resetby

    def step(self, name: str) -> int:
        if name not in self._values:
            return 0
        self._values[name] += 1
        self._cascade_reset(name)
        return self._values[name]

    def set(self, name: str, value: int) -> None:
        self._values[name] = value  # declare implicitly if missing
        if name not in self._resetby:
            self._resetby[name] = None
        self._cascade_reset(name)

    def add(self, name: str, delta: int) -> None:
        if name not in self._values:
            return
        self._values[name] += delta
        self._cascade_reset(name)

    def get(self, name: str) -> int:
        return self._values.get(name, 0)

    def _cascade_reset(self, name: str) -> None:
        for cname, parent in self._resetby.items():
            if parent == name:
                self._values[cname] = 0
                self._cascade_reset(cname)


###############################################################################
# Main scanner
###############################################################################

_BEGIN_RE = re.compile(r"\\begin\s*\{\s*(\w+\*?)\s*\}")
_END_RE   = re.compile(r"\\end\s*\{\s*(\w+\*?)\s*\}")

# Optional note after \begin{env}: \begin{thm}[some note]
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
    counter_formats = _parse_counter_formats(clean)

    # ── 4. build unified counter bank ─────────────────────────────────────────
    bank = _CounterBank()

    # Declare section-level counters with cascading resets
    for i, level in enumerate(_SECTION_LEVELS):
        parent = _SECTION_LEVELS[i - 1] if i > 0 else None
        bank.declare(level, resetby=parent)

    # Declare theorem counters.  Only the root counter needs an entry; sharing
    # envs reuse the root counter directly (no separate declaration needed).
    for env, info in thm_defs.items():
        if info.get("unnumbered"):
            continue
        root = info["shared"] or env
        if root == env:  # only declare the root, not sharing aliases
            bank.declare(env, resetby=info.get("reset"))

    def _get_root(env: str) -> Optional[str]:
        info = thm_defs.get(env, {})
        return info["shared"] if info.get("shared") else (env if env in thm_defs else None)

    # ── 4b. ref rendering (mirrors plasTeX's TheCounter.invoke) ───────────────

    def _eval_format(fmt_body: str, self_name: str) -> str:
        """
        Evaluate a \\the<X> format body, resolving \\the<Y> references
        recursively and \\arabic{}, \\Alph{} etc. against the live bank.
        """
        result = fmt_body

        def _replace_the(m: re.Match) -> str:
            ref_name = m.group(1)
            if ref_name == self_name:
                return str(bank.get(self_name))
            return _counter_ref(ref_name)

        result = _THE_REF_RE.sub(_replace_the, result)

        def _replace_fmt(m: re.Match) -> str:
            fmt_cmd  = m.group(1)
            ctr_name = m.group(2)
            return _apply_format(fmt_cmd, bank.get(ctr_name))

        result = _FMT_CMD_RE.sub(_replace_fmt, result)
        return result.strip(".")

    def _counter_ref(name: str) -> str:
        """
        Return the formatted ref string for *name* given the current bank state.
        Checks \\renewcommand{\\the<name>} first, then falls back to the
        resetby ancestor chain (mirroring plasTeX's default TheCounter format).
        """
        fmt_body = counter_formats.get(name)
        if fmt_body:
            return _eval_format(fmt_body, name)

        resetby = bank._resetby.get(name)
        n = bank.get(name)
        if not resetby:
            return str(n)

        prefix = _counter_ref(resetby)
        # Strip leading "0." components (plasTeX trimLeft behaviour for
        # book/report classes where chapter may be 0)
        ref = f"{prefix}.{n}" if prefix and not all(p == "0" for p in prefix.split(".")) else str(n)
        return ref

    def _next_ref(env: str) -> Optional[str]:
        if thm_defs.get(env, {}).get("unnumbered"):
            return None
        root = _get_root(env)
        if root is None:
            return None
        bank.step(root)
        return _counter_ref(root)

    # ── 5. collect interleaved events and scan ────────────────────────────────

    # Section events: (pos, "section", level, is_starred)
    section_events = [
        (m.start(), "section", m.group(1), m.group(2) == "*")
        for m in _SECTION_RE.finditer(clean)
    ]

    # Counter mutation events: (pos, op, name, value_or_0)
    counter_events: list[tuple[int, str, str, int]] = []
    for m in _SETCOUNTER_RE.finditer(clean):
        counter_events.append((m.start(), "set", m.group(1), int(m.group(2))))
    for m in _ADDTOCOUNTER_RE.finditer(clean):
        counter_events.append((m.start(), "add", m.group(1), int(m.group(2))))
    for m in _STEPCOUNTER_RE.finditer(clean):
        counter_events.append((m.start(), "step", m.group(1), 0))

    # Merge and sort all pre-token events by position
    all_pre_events: list[tuple[int, str, str, int | bool]] = sorted(
        [(pos, "section", level, starred) for pos, _, level, starred in section_events]
        + counter_events,
        key=lambda e: e[0],
    )
    pre_idx = 0

    def _flush_pre_events(up_to: int) -> None:
        nonlocal pre_idx
        while pre_idx < len(all_pre_events) and all_pre_events[pre_idx][0] < up_to:
            pos, kind, name, val = all_pre_events[pre_idx]
            if kind == "section":
                if not val:  # val is is_starred here
                    bank.step(name)
            elif kind == "set":
                bank.set(name, val)
            elif kind == "add":
                bank.add(name, val)
            elif kind == "step":
                bank.step(name)
            pre_idx += 1

    results: list[Environment] = []
    stack:   list[tuple[str, int, int, Optional[str], Optional[str]]] = []

    tokens = sorted(
        [("begin", m.group(1), m.start(), m.end()) for m in _BEGIN_RE.finditer(clean)]
        + [("end",  m.group(1), m.start(), m.end()) for m in _END_RE.finditer(clean)],
        key=lambda t: t[2],
    )

    for kind, env, tok_start, tok_end in tokens:
        _flush_pre_events(tok_start)

        if kind == "begin":
            after_begin = clean[tok_end:]
            note_match  = _NOTE_RE.match(after_begin)
            note_raw    = note_match.group(1).strip() if note_match else None
            note        = re.sub(r'\s+', ' ', _expand_macros(note_raw, macros)).strip() if note_raw else None
            body_start  = tok_end + note_match.end() if note_match else tok_end
            # Step the counter now (at \begin time), mirroring LaTeX's behaviour.
            # This ensures any \setcounter / section commands inside the body
            # don't corrupt the ref that was assigned to this environment.
            ref         = _next_ref(env) if env in thm_defs else None
            stack.append((env, body_start, _lineno(tok_start), note, ref))

        elif kind == "end":
            match_idx = None
            for i in range(len(stack) - 1, -1, -1):
                if stack[i][0] == env:
                    match_idx = i
                    break
            if match_idx is None:
                continue

            open_env, body_start, begin_line, note, ref = stack.pop(match_idx)
            end_line = _lineno(tok_start)

            raw_body = clean[body_start:tok_start]
            label_m  = _LABEL_RE.search(raw_body)
            label    = label_m.group(1).strip() if label_m else None
            body     = re.sub(r'\s+', ' ', _expand_macros(_LABEL_RE.sub("", raw_body), macros)).strip()

            env_name = thm_defs[open_env]["display"].lower() if open_env in thm_defs else open_env

            results.append(Environment(
                env        = env_name,
                ref        = ref,
                note       = note,
                label      = label,
                body       = body,
                begin_line = begin_line,
                end_line   = end_line,
            ))

    return results