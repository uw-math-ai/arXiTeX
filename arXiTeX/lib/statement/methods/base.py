"""
Uniform interface shared by every parsing method (regex, tex, llm).

A ``Method`` is a small config object that knows how to turn a paper's source
directory into a list of ``Statement``s. Method-specific options (TeX engine,
LLM model, ...) live on the concrete subclass, so the common case stays simple
while advanced configuration stays possible.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from arXiTeX.types import Statement


class UnsupportedOption(ValueError):
    """Raised when a method is asked to honor an option it does not support."""


@dataclass
class ParseContext:
    """Everything a method needs to parse one paper.

    Attributes
    ----------
    paper_dir : Path
        Directory containing the paper's source files.
    main_file : Path
        Best-guess main ``.tex`` file.
    kinds : set of str
        Statement kinds the caller is interested in (methods may use this to
        limit work; final filtering is done uniformly by the ``Parser``).
    context : int
        Characters of surrounding text to capture around each statement.
    flat_tex : str, optional
        Flattened single-string source, precomputed by the ``Parser`` when it is
        already needed elsewhere. Methods should fall back to computing their own
        if this is ``None``.
    timeout : int, optional
        Overall parse timeout in seconds, if the caller set one. Methods that
        shell out (e.g. ``tex``) may use it to bound their subprocess so it is
        actually killed rather than merely abandoned.
    """

    paper_dir: Path
    main_file: Path
    kinds: Set[str]
    context: int = 0
    flat_tex: Optional[str] = None
    timeout: Optional[int] = None


class Method(ABC):
    """Base class for parsing methods.

    Subclasses set ``name`` and ``supports_context`` and implement :meth:`parse`.
    Returned statements should include any ``proof`` environments (kind
    ``"proof"``); the ``Parser`` attaches them to their statements afterwards.
    """

    #: short identifier, e.g. "regex", "tex", "llm"
    name: str = "method"
    #: whether the method can populate pre/post context
    supports_context: bool = False

    @abstractmethod
    def parse(self, ctx: ParseContext) -> List[Statement]:
        ...
