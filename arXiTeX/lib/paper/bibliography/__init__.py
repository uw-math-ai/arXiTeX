import re
import bibtexparser
from pathlib import Path
from typing import List, Optional
from tempfile import TemporaryDirectory
from arXiTeX.lib.utils.download_arxiv_paper import download_arxiv_paper

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
            return _parse_bibliography(paper_dir, labels=labels)
    elif paper_path is not None:
        if isinstance(paper_path, str):
            paper_path = Path(paper_path)
        if paper_path.is_dir():
            return _parse_bibliography(paper_path, labels=labels)
        else:
            return {}


def _parse_bibliography(paper_dir: Path, labels: Optional[List[str]]):
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

    return bibliography
