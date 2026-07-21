"""
The ``tex`` parsing method: run a real TeX engine (tectonic by default, or
pdflatex) over an instrumented copy of the paper so macros, packages, counters
and ``\\input``s are all resolved natively, then read back the statements the
engine emitted.

See ``arxitex-hook.sty`` for the instrumentation. This module discovers which
theorem-like environments to instrument, injects the hook into the preamble,
runs the engine, and parses the ``.arxitex`` capture file into ``Statement``s.
"""

import re
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional, Set

from arxitex.types import Statement
from arxitex.lib.statement.methods.base import ParseContext, Method, UnsupportedOption
from arxitex.lib.statement.methods._macros import expand_user_macros
from arxitex.lib.statement.methods.regex.flatten import flatten_tex
from arxitex.lib.statement.methods.regex.log_envs import _parse_theorem_defs

_HOOK_STY = Path(__file__).with_name("arxitex-hook.sty")

_DOC_BEGIN_RE = re.compile(r"\\begin\s*\{document\}")
_LABEL_RE = re.compile(r"\\label\s*\{([^}]+)\}")
_WS_RE = re.compile(r"\s+")


class TexEngineError(RuntimeError):
    """Raised when the TeX engine is unavailable or the compile produced nothing."""


def _engine_cmd(engine: str, main_name: str) -> list[str]:
    if engine == "tectonic":
        return [
            "tectonic",
            "--outfmt", "xdv",           # skip PDF/font work; we only need the run
            "--chatter", "minimal",
            "-Z", "continue-on-errors",  # survive non-fatal LaTeX errors
            main_name,
        ]
    elif engine == "pdflatex":
        return [
            "pdflatex",
            "-interaction=nonstopmode",
            main_name,
        ]
    raise UnsupportedOption(f"Unknown tex engine: {engine!r} (use 'tectonic' or 'pdflatex')")


def _inject_hook(main_text: str, instrument_lines: str) -> Optional[str]:
    """Insert the hook usepackage + instrument calls just before \\begin{document}."""
    m = _DOC_BEGIN_RE.search(main_text)
    if not m:
        return None
    injection = "\\usepackage{arxitex-hook}\n" + instrument_lines + "\n"
    return main_text[: m.start()] + injection + main_text[m.start() :]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def _build_records(capture: str) -> List[dict]:
    """Parse the .arxitex capture file into ordered field dicts, one per statement.

    Fields (REF/NOTE/BODY) are written one-per-line by the hook, so a simple
    line scan is sufficient; the current field accumulates trailing lines in the
    (rare) event the engine ever splits one.
    """
    records: List[dict] = []
    cur: Optional[dict] = None
    field: Optional[str] = None

    for line in capture.splitlines():
        if line.startswith("<<<ARXITEX BEGIN "):
            env = line[len("<<<ARXITEX BEGIN ") : -len(">>>")]
            cur = {"env": env, "REF": None, "NOTE": None, "BODY": None}
            field = None
        elif line.startswith("<<<ARXITEX END "):
            if cur is not None:
                records.append(cur)
            cur, field = None, None
        elif cur is not None and (
            line.startswith("REF=") or line.startswith("NOTE=") or line.startswith("BODY=")
        ):
            field, _, val = line.partition("=")
            cur[field] = val
        elif cur is not None and field is not None:
            cur[field] = (cur[field] or "") + line

    return records


def _record_to_statement(rec: dict, thm_defs: dict, flat_tex: str) -> Optional[Statement]:
    env = rec["env"]
    info = thm_defs.get(env)

    if env == "proof":
        kind = "proof"
    elif info is not None:
        kind = (info.get("display") or env).lower()
    else:
        kind = env

    raw_body = rec.get("BODY") or ""
    # Keep every \label (a restated theorem may carry several) so a proof can
    # reference any one of them.
    labels = [l.strip() for l in _LABEL_RE.findall(raw_body)]
    body = _LABEL_RE.sub("", raw_body)
    body = expand_user_macros(body, flat_tex)
    body = _WS_RE.sub(" ", body).strip()

    if not body:
        return None

    note = rec.get("NOTE")
    if note is not None:
        note = _WS_RE.sub(" ", expand_user_macros(note, flat_tex)).strip() or None

    number = rec.get("REF")
    if number is not None:
        number = number.strip() or None

    return Statement(kind=kind, number=number, note=note, labels=labels, body=body, proof=None)


def tex_parse(
    paper_dir: Path,
    main_file: Path,
    kinds: Set[str],
    flat_tex: Optional[str] = None,
    engine: str = "tectonic",
    timeout: Optional[int] = None,
) -> List[Statement]:
    if shutil.which(engine) is None:
        raise TexEngineError(
            f"TeX engine {engine!r} not found on PATH. Install it, or use a "
            f"different method (e.g. method='regex')."
        )

    if flat_tex is None:
        flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)

    thm_defs = _parse_theorem_defs(flat_tex)

    # Build the instrument calls: numbered theorem envs record their ref, while
    # unnumbered (\newtheorem*) envs and proof are captured without a ref.
    instrument = []
    for env, info in thm_defs.items():
        if info.get("unnumbered"):
            instrument.append(f"\\arxitexInstrumentProof{{{env}}}")
        else:
            instrument.append(f"\\arxitexInstrument{{{env}}}")
    instrument.append("\\arxitexInstrumentProof{proof}")
    instrument_lines = "".join(instrument)

    with TemporaryDirectory() as tmp:
        work = Path(tmp) / "src"
        shutil.copytree(paper_dir, work)

        rel_main = main_file.resolve().relative_to(paper_dir.resolve())
        work_main = work / rel_main
        run_dir = work_main.parent

        injected = _inject_hook(_read_text(work_main), instrument_lines)
        if injected is None:
            raise TexEngineError(r"No \begin{document} found; cannot instrument with the tex method.")
        work_main.write_text(injected, encoding="utf-8")

        shutil.copy2(_HOOK_STY, run_dir / _HOOK_STY.name)

        try:
            proc = subprocess.run(
                _engine_cmd(engine, work_main.name),
                cwd=run_dir,
                capture_output=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise TimeoutError(f"tex engine timed out after {timeout}s") from e

        capture_file = run_dir / (work_main.stem + ".arxitex")
        if not capture_file.is_file():
            tail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace").strip()
            tail = tail[-500:]
            raise TexEngineError(
                f"{engine} produced no capture file (the compile likely failed). "
                f"Engine output tail:\n{tail}"
            )
        capture = _read_text(capture_file)

    statements: List[Statement] = []
    for rec in _build_records(capture):
        stmt = _record_to_statement(rec, thm_defs, flat_tex)
        if stmt is not None:
            statements.append(stmt)
    return statements


class Tex(Method):
    """Parse with a real TeX engine (macros/packages expanded natively).

    Parameters
    ----------
    engine : str
        ``"tectonic"`` (default, self-contained) or ``"pdflatex"`` (uses your
        local TeX installation).
    timeout : int, optional
        Per-compile timeout in seconds passed to the engine subprocess.
    """

    name = "tex"
    supports_context = False

    def __init__(self, engine: str = "tectonic", timeout: Optional[int] = None):
        self.engine = engine
        self.timeout = timeout

    def parse(self, ctx: ParseContext) -> List[Statement]:
        timeout = self.timeout if self.timeout is not None else ctx.timeout
        return tex_parse(
            ctx.paper_dir,
            ctx.main_file,
            ctx.kinds,
            flat_tex=ctx.flat_tex,
            engine=self.engine,
            timeout=timeout,
        )
