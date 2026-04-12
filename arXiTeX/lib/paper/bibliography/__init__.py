import re
import bibtexparser
from pathlib import Path
from typing import List, Optional
from tempfile import TemporaryDirectory
from arXiTeX.lib.utils.download_arxiv_paper import download_arxiv_paper

# Extracts the entire thebibliography environment
_THEBIB_RE = re.compile(
    r'\\begin\{thebibliography\}.*?\\end\{thebibliography\}',
    re.DOTALL
)
# Matches each \bibitem entry up to the next one or the end of the environment
_BIBITEM_RE = re.compile(
    r'\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}(.*?)(?=\\bibitem|\\end\{thebibliography\})',
    re.DOTALL
)
# Matches arXiv IDs in free text (new-style YYMM.NNNNN or old-style area/NNNNNNN)
_ARXIV_ID_RE = re.compile(
    r'(?:arXiv:|arxiv\.org/abs/)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+/\d{7}(?:v\d+)?)',
    re.IGNORECASE
)


def _strip_latex(text: str) -> str:
    """Best-effort removal of LaTeX commands, keeping text content."""
    # \cmd{content} -> content (repeated to handle nesting)
    for _ in range(4):
        text = re.sub(r'\\[a-zA-Z]+\*?\{([^{}]*)\}', r'\1', text)
    text = re.sub(r'\\[a-zA-Z]+\*?', '', text)
    text = text.replace('{', '').replace('}', '')
    return ' '.join(text.split()).strip()


def _parse_bibitem_from_dir(paper_dir: Path, labels: Optional[List[str]]) -> dict:
    """Parse \bibitem entries from .tex and .bbl files."""
    bibliography = {}

    for tex_file in paper_dir.iterdir():
        if tex_file.suffix not in ('.tex', '.bbl'):
            continue

        try:
            content = tex_file.read_text(encoding='utf-8', errors='replace')
            for env_match in _THEBIB_RE.finditer(content):
                env = env_match.group(0)
                for item_match in _BIBITEM_RE.finditer(env):
                    cite_key = item_match.group(1).strip()
                    if labels is not None and cite_key not in labels:
                        continue

                    raw = item_match.group(2)
                    metadata = {}

                    arxiv_match = _ARXIV_ID_RE.search(raw)
                    if arxiv_match:
                        metadata['arxiv_id'] = arxiv_match.group(1)

                    stripped = _strip_latex(raw)
                    if stripped:
                        metadata['title'] = stripped[:500]

                    if metadata:
                        bibliography[cite_key] = metadata

        except Exception as e:
            print(f"Error parsing {tex_file}: {e}")
            continue

    return bibliography

# Pre-defined strings to supplement bibtexparser's common_strings.
# Covers full month names, common publisher/journal abbreviations seen in arXiv .bib files.
_EXTRA_STRINGS = {
    # Full month names (common_strings only has 3-letter abbreviations)
    "january": "January", "february": "February", "march": "March",
    "april": "April", "may": "May", "june": "June", "july": "July",
    "august": "August", "september": "September", "october": "October",
    "november": "November", "december": "December",
    # Publishers / societies
    "springer": "Springer", "springer_verlag": "Springer-Verlag",
    "birkhauser": "Birkhäuser", "cambridge": "Cambridge University Press",
    "oxford": "Oxford University Press", "princeton": "Princeton University Press",
    "ams": "American Mathematical Society", "ams_press": "AMS Press",
    "siam": "SIAM", "ieee": "IEEE", "acm": "ACM", "elsevier": "Elsevier",
    "wiley": "Wiley", "academic_press": "Academic Press",
    "de_gruyter": "De Gruyter", "msri": "MSRI Publications",
    # Common journal/series abbreviations
    "lnm": "Lecture Notes in Mathematics",
    "lncs": "Lecture Notes in Computer Science",
    "gsm": "Graduate Studies in Mathematics",
    "gtm": "Graduate Texts in Mathematics",
    "pams": "Proc. Amer. Math. Soc.",
    "tams": "Trans. Amer. Math. Soc.",
    "jams": "J. Amer. Math. Soc.",
    "inventiones": "Inventiones Mathematicae",
    "annals": "Annals of Mathematics",
    "duke": "Duke Mathematical Journal",
    "crelle": "Journal für die reine und angewandte Mathematik",
    "compositio": "Compositio Mathematica",
    "mrl": "Mathematical Research Letters",
    "imrn": "International Mathematics Research Notices",
    "jlms": "Journal of the London Mathematical Society",
    "plms": "Proceedings of the London Mathematical Society",
    "forum": "Forum of Mathematics, Sigma",
    "dmj": "Duke Mathematical Journal",
}

# Matches bare (unquoted) string references on the right-hand side of field assignments,
# e.g.  month = july,   or   publisher = springer,
_BARE_VALUE_RE = re.compile(
    r'^\s*\w[\w-]*\s*=\s*([a-zA-Z][a-zA-Z0-9_]*)\s*[,}]',
    re.MULTILINE,
)
# Matches @STRING{name = ...} definitions already present in the file
_STRING_DEF_RE = re.compile(r'@[Ss][Tt][Rr][Ii][Nn][Gg]\s*\{\s*(\w+)\s*=')


def _build_parser(content: str) -> bibtexparser.bparser.BibTexParser:
    """Return a BibTexParser pre-loaded with common strings plus any bare
    string identifiers found in *content* that aren't already defined."""
    parser = bibtexparser.bparser.BibTexParser(common_strings=True, ignore_nonstandard_types=False)
    for k, v in _EXTRA_STRINGS.items():
        if k not in parser.bib_database.strings:
            parser.bib_database.strings[k] = v

    # Collect names already defined (standard abbreviations + file-level @STRINGs)
    defined = {k.lower() for k in parser.bib_database.strings}
    defined |= {m.group(1).lower() for m in _STRING_DEF_RE.finditer(content)}

    # Any remaining bare identifier becomes a string that maps to itself
    for m in _BARE_VALUE_RE.finditer(content):
        name = m.group(1)
        if name.lower() not in defined:
            parser.bib_database.strings[name] = name
            defined.add(name.lower())

    return parser


def parse_bibliography(
    arxiv_id: Optional[str] = None,
    paper_path: Optional[Path | str] = None,
    labels: Optional[List[str]] = None
):
    if arxiv_id is not None:
        with TemporaryDirectory() as temp_dir:
            paper_dir = download_arxiv_paper(Path(temp_dir), arxiv_id)
            return parse_bibliography_from_dir(paper_dir, labels=labels)
    elif paper_path is not None:
        if isinstance(paper_path, str):
            paper_path = Path(paper_path)
        if paper_path.is_dir():
            return parse_bibliography_from_dir(paper_path, labels=labels)
        else:
            return {}


def parse_bibliography_from_dir(paper_dir: Path, labels: Optional[List[str]] = None):
    bibliography = {}

    for bib_file in paper_dir.iterdir():
        if bib_file.suffix != ".bib":
            continue

        try:
            content = bib_file.read_text(encoding="utf-8")
            parser = _build_parser(content)
            bib_database = bibtexparser.loads(content, parser=parser)

            for entry in bib_database.entries:
                cite_key = entry.get("ID")
                if not cite_key:
                    continue
                if labels is not None and cite_key not in labels:
                    continue

                metadata = {
                    "title": entry.get("title", "").strip("{}").strip(),
                    "arxiv_id": (entry.get("eprint") or entry.get("arxiv", "")).replace("arXiv:", "").strip()
                }

                metadata = {k: v for k, v in metadata.items() if v}

                if metadata:
                    bibliography[cite_key] = metadata

        except Exception as e:
            print(f"Error parsing {bib_file}: {e}")
            continue

    if bibliography:
        return bibliography, True

    return _parse_bibitem_from_dir(paper_dir, labels), False
