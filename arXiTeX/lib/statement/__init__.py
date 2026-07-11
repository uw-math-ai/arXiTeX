"""
The ``Parser`` — arXiTeX's single entry point for turning a paper into
structured statements, preamble, and bibliography.

A ``Parser`` bundles *how* to parse (method(s), kinds, focus, validation, ...)
so it can be configured once and reused across many papers. Call
:meth:`Parser.parse` with a source (arXiv id, local path, or ``s3://`` URI).
"""

import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator, List, Optional, Set, Tuple

from arXiTeX.types import (
    Statement,
    ValidationLevel,
    ParseFocus,
    ParseResult,
)
from arXiTeX.lib.utils.download_arxiv_paper import download_arxiv_paper
from arXiTeX.lib.utils.download_s3_paper import download_s3_paper
from arXiTeX.lib.paper.bibliography import parse_bibliography_from_dir
from .methods import Method, ParseContext, resolve_methods, MethodSpec
from .validate_statements import validate_statement, validate_statements
from .run_with_timeout import run_with_timeout
from .errors import ParseError, format_error
from .guess_main_file import guess_main_file
from .connect_proofs import connect_proofs

STATEMENT_KINDS = {
    "theorem", "lemma", "proposition", "corollary",
    "definition",
    "axiom", "postulate",
    "conjecture", "hypothesis",
    "proof",
    "remark", "note", "observation",
    "claim",
    "fact",
    "assumption",
    "notation", "convention",
}

#: Default method chain: real TeX engine, falling back to regex if it is
#: unavailable (no tectonic/pdflatex) or fails to produce statements.
DEFAULT_METHOD: Tuple[str, ...] = ("tex", "regex")

_DOC_BEGIN_RE = re.compile(r"\\begin\s*\{document\}", re.IGNORECASE)
_PREAMBLE_MAX_CHARS = 16_384

# new-style (2107.12345) or old-style (math.AG/0601001) arXiv ids, optional version
_ARXIV_ID_RE = re.compile(
    r"^(?:\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?$",
    re.IGNORECASE,
)


def _extract_preamble(tex: str) -> Optional[str]:
    m = _DOC_BEGIN_RE.search(tex)
    if not m:
        return None
    preamble = tex[: m.start()].strip()
    if not preamble:
        return None
    if len(preamble) > _PREAMBLE_MAX_CHARS:
        cut = preamble.rfind("\n", 0, _PREAMBLE_MAX_CHARS)
        if cut == -1:
            cut = _PREAMBLE_MAX_CHARS
        preamble = preamble[:cut] + "\n% TRUNCATED"
    return preamble


class Parser:
    """Configurable parser for arXiv/LaTeX papers.

    Parameters
    ----------
    method : str | Method | list, optional
        Which parsing method(s) to use: ``"regex"``, ``"tex"``, ``"llm"``, a
        configured instance (e.g. ``Tex(engine="pdflatex")``), or a list of these
        forming a fallback chain (each is tried until one yields statements).
        Defaults to ``("tex", "regex")``.
    kinds : set of str, optional
        Statement kinds to keep. Defaults to a broad preset (:data:`STATEMENT_KINDS`).
    focus : ParseFocus | str, optional
        Which parts of the paper to populate (``"all"``, ``"statements"``,
        ``"preamble"``, ``"bibliography"``). Defaults to ``"all"``.
    validation : ValidationLevel | str, optional
        How strictly to validate statements (``"paper"``, ``"statement"``,
        ``"none"``). Defaults to ``"paper"``.
    context : int, optional
        Characters of surrounding text to capture around each statement. Only the
        ``regex`` method supports this; a non-zero value with any other method
        raises. Defaults to ``0``.
    timeout : int, optional
        Maximum seconds for a single ``parse`` call. Defaults to no limit.
    """

    def __init__(
        self,
        method: MethodSpec = DEFAULT_METHOD,
        kinds: Set[str] = STATEMENT_KINDS,
        focus: "ParseFocus | str" = ParseFocus.ALL,
        validation: "ValidationLevel | str" = ValidationLevel.PAPER,
        context: int = 0,
        timeout: Optional[int] = None,
    ):
        self.methods: List[Method] = resolve_methods(method)
        self.kinds: Set[str] = set(kinds)
        self.focus = ParseFocus(focus)
        self.validation = ValidationLevel(validation)
        self.context = context
        self.timeout = timeout

        if context > 0:
            unsupported = [m.name for m in self.methods if not m.supports_context]
            if unsupported:
                raise ValueError(
                    f"context={context} is only supported by the 'regex' method; "
                    f"these methods do not support it: {', '.join(unsupported)}."
                )

    # ---- public API ------------------------------------------------------

    def parse(
        self,
        source: Optional[str] = None,
        *,
        arxiv_id: Optional[str] = None,
        path: "str | Path | None" = None,
        s3_uri: Optional[str] = None,
    ) -> ParseResult:
        """Parse a paper.

        Provide the source either positionally (auto-detected) or via exactly one
        keyword. Auto-detection: ``s3://...`` → S3, an existing path → local file
        or directory, otherwise an arXiv id.

        Examples
        --------
        >>> parser.parse("2109.06451")           # arXiv id
        >>> parser.parse("path/to/paper/")        # local directory
        >>> parser.parse(s3_uri="s3://bucket/p.tar.gz")
        """
        kind, value = self._resolve_source(source, arxiv_id, path, s3_uri)
        return run_with_timeout(self.timeout, self._parse_resolved, kind, value)

    # ---- source handling -------------------------------------------------

    def _resolve_source(
        self,
        source: Optional[str],
        arxiv_id: Optional[str],
        path: "str | Path | None",
        s3_uri: Optional[str],
    ) -> Tuple[str, str]:
        explicit = [
            ("arxiv_id", arxiv_id),
            ("path", path),
            ("s3_uri", s3_uri),
        ]
        given = [(k, v) for k, v in explicit if v is not None]

        if source is not None:
            if given:
                raise ValueError(
                    "Pass the source positionally OR as a keyword, not both."
                )
            return self._detect_source(source)

        if len(given) != 1:
            raise ValueError(
                "Provide exactly one source: a positional argument, or one of "
                "arxiv_id / path / s3_uri."
            )
        return given[0]

    @staticmethod
    def _detect_source(source: "str | Path") -> Tuple[str, str]:
        s = str(source)
        if s.startswith("s3://"):
            return ("s3_uri", s)
        if Path(source).exists():
            return ("path", s)
        if _ARXIV_ID_RE.match(s):
            return ("arxiv_id", s)
        raise ValueError(
            f"Could not interpret source {source!r} as an arXiv id, existing "
            f"path, or s3:// URI."
        )

    @contextmanager
    def _materialize(self, kind: str, value: str) -> Iterator[Path]:
        """Yield a directory containing the paper's source files."""
        if kind == "arxiv_id":
            with TemporaryDirectory() as tmp:
                try:
                    paper_dir = download_arxiv_paper(cwd=Path(tmp), arxiv_id=value)
                except Exception as e:
                    raise RuntimeError(format_error(ParseError.DOWNLOAD, str(e)))
                yield paper_dir
        elif kind == "s3_uri":
            with TemporaryDirectory() as tmp:
                try:
                    paper_dir = download_s3_paper(cwd=Path(tmp), s3_uri=value)
                except Exception as e:
                    raise RuntimeError(format_error(ParseError.DOWNLOAD, str(e)))
                yield paper_dir
        elif kind == "path":
            p = Path(value)
            if p.is_dir():
                yield p
            elif p.is_file():
                with TemporaryDirectory() as tmp:
                    dest = Path(tmp) / p.name
                    shutil.copy2(p, dest)
                    yield Path(tmp)
            else:
                raise FileNotFoundError(format_error(
                    ParseError.DOWNLOAD, f"Path not found: {value}"
                ))
        else:
            raise ValueError(f"Unknown source kind: {kind}")

    # ---- core parse ------------------------------------------------------

    def _parse_resolved(self, kind: str, value: str) -> ParseResult:
        with self._materialize(kind, value) as paper_dir:
            return self._parse_dir(paper_dir)

    def _parse_dir(self, paper_dir: Path) -> ParseResult:
        do_statements = self.focus in (ParseFocus.ALL, ParseFocus.STATEMENTS)
        do_preamble = self.focus in (ParseFocus.ALL, ParseFocus.PREAMBLE)
        do_bibliography = self.focus in (ParseFocus.ALL, ParseFocus.BIBLIOGRAPHY)

        statements = None
        preamble = None
        bibliography = None
        bibliography_bibtex = None
        method_used = None

        main_file = None
        if do_preamble or do_statements:
            try:
                main_file = guess_main_file(paper_dir)
            except Exception as e:
                raise RuntimeError(format_error(ParseError.PARSING, str(e)))

        # Flatten once if the preamble or context path needs it.
        flat_tex = None
        if do_preamble or (do_statements and self.context > 0):
            try:
                from .methods.regex.flatten import flatten_tex
                flat_tex = flatten_tex(paper_dir, main_file, ignore_errors=True)
            except Exception:
                flat_tex = None

        if do_preamble and flat_tex is not None:
            preamble = _extract_preamble(flat_tex)

        if do_statements:
            statements, method_used = self._run_methods(paper_dir, main_file, flat_tex)

        if do_bibliography:
            bibliography, bibliography_bibtex = parse_bibliography_from_dir(paper_dir)

        return ParseResult(
            statements=statements,
            preamble=preamble,
            bibliography=bibliography,
            bibliography_bibtex=bibliography_bibtex,
            method_used=method_used,
        )

    def _run_methods(
        self,
        paper_dir: Path,
        main_file: Path,
        flat_tex: Optional[str],
    ) -> Tuple[List[Statement], str]:
        ctx = ParseContext(
            paper_dir=paper_dir,
            main_file=main_file,
            kinds=self.kinds,
            context=self.context,
            flat_tex=flat_tex,
            timeout=self.timeout,
        )

        errors: List[str] = []
        first_exc: Optional[Exception] = None
        for method in self.methods:
            try:
                raw = method.parse(ctx)
                statements = self._postprocess(raw)
            except Exception as e:
                if first_exc is None:
                    first_exc = e
                errors.append(f"{method.name}: {e}")
                continue

            if statements:
                return statements, method.name
            errors.append(f"{method.name}: no statements found")

        raise RuntimeError(format_error(
            ParseError.EMPTY,
            "No method produced statements. " + " | ".join(errors),
        )) from first_exc

    def _postprocess(self, raw_statements: List[Statement]) -> List[Statement]:
        """Normalize kinds, validate, and attach proofs. May raise on PAPER-level
        validation failure (so the Parser can fall back to the next method)."""
        if not raw_statements:
            return []

        # Normalize each statement's kind to a requested kind (substring match),
        # always keeping proofs so connect_proofs can attach them.
        internal_kinds = self.kinds | {"proof"}
        normalized = [
            stmt.model_copy(update={"kind": sk})
            for stmt in raw_statements
            if (sk := next((k for k in internal_kinds if k in stmt.kind), None)) is not None
        ]
        if not normalized:
            return []

        if self.validation == ValidationLevel.STATEMENT:
            kept = []
            for stmt in normalized:
                try:
                    validate_statement(stmt)
                    kept.append(stmt)
                except Exception:
                    pass
            normalized = kept
        elif self.validation == ValidationLevel.PAPER:
            validate_statements(normalized)
        # ValidationLevel.NONE: no checks

        if not normalized:
            return []

        return connect_proofs(normalized)
