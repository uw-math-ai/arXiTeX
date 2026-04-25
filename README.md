![arXiTeX](images/logo.png)

A Python library for parsing arXiv papers.

------------------------------------------------------------------------

## Overview

**arXiTeX** parses arXiv papers. Given an arXiv ID or a local LaTeX
source directory, it extracts structured mathematical statements, proofs,
bibliography entries, and document preambles from the raw `.tex` source.

It is designed for building math datasets, theorem search indices, and
any downstream task that needs structured access to arXiv content.

- **Paper:** https://arxiv.org/abs/2602.05216
- **Demo:** https://huggingface.co/spaces/uw-math-ai/theorem-search

------------------------------------------------------------------------

## Installation

```
pip install git+https://github.com/uw-math-ai/arXiTeX.git
```

------------------------------------------------------------------------

## Usage

### Catalog arXiv paper metadata

`paper_catalog` streams metadata for arXiv papers in batches, filtered
by category. It uses the [arXiv Kaggle dataset](https://www.kaggle.com/datasets/Cornell-University/arxiv)
and enriches each paper with citation counts and reference IDs via
[Semantic Scholar](https://www.semanticscholar.org/).

```python
from arXiTeX import paper_catalog

for batch in paper_catalog(
    download_dir="data/",        # where to cache the Kaggle metadata ZIP
    categories=["math", "cs.LG"],
    batch_size=100,
):
    for paper in batch:
        print(paper.arxiv_id, paper.title)
```

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `download_dir` | `Path \| str` | — | Directory for the cached `arxiv.zip` metadata file. Downloaded automatically on first run. |
| `categories` | `List[str]` | math + CS categories | Category filter. Accepts full names (`math.AG`) or prefixes (`math`). |
| `batch_size` | `int` | `100` | Papers per yielded batch. |

For citation enrichment, set a Semantic Scholar API key in your environment:

```
SEMANTIC_SCHOLAR_API_KEY=...
```

Without it, citation data is unavailable — reduce `batch_size` to avoid
rate-limiting.

------------------------------------------------------------------------

### Parse a paper's statements

`parse_paper` parses theorems, lemmas, definitions, proofs, and other
mathematical statements out of a paper's LaTeX source. Accepts either
an arXiv ID (downloads automatically) or a local path.

```python
from arXiTeX import parse_paper
from arXiTeX.types import ParsingMethod, ParseFocus

result = parse_paper(
    arxiv_id="2109.06451",
    parsing_method=ParsingMethod.PLASTEX,   # default; use REGEX as fallback
    timeout=30,
)

for stmt in result.statements:
    print(stmt.kind, stmt.ref)
    print(stmt.body)
    if stmt.proof:
        print(stmt.proof)
```

Or from a local file or directory:

```python
result = parse_paper(paper_path="path/to/paper.tex")
result = parse_paper(paper_path="path/to/paper_dir/")
```

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `arxiv_id` | `str` | `None` | arXiv ID. Either this or `paper_path` is required. |
| `paper_path` | `Path \| str` | `None` | Path to a `.tex` file or source directory. Either this or `arxiv_id` is required. |
| `parsing_method` | `ParsingMethod` | `PLASTEX` | `PLASTEX` (accurate, slower) or `REGEX` (fast, less robust). |
| `statement_kinds` | `Set[str]` | broad default set | Statement types to capture. |
| `validation_level` | `StatementValidationLevel` | `Paper` | `Paper` validates the full parse; `Statement` validates individually. |
| `timeout` | `int` | `None` | Max seconds before raising a timeout error. |
| `focus` | `ParseFocus` | `ALL` | Which parts of the paper to parse. |
| `context` | `int` | `0` | Characters of surrounding text to capture before/after each statement. Only supported with `ParsingMethod.REGEX`; ignored for `PLASTEX`. |

**`statement_kinds`** defaults to:

```python
{
    "theorem", "lemma", "proposition", "corollary",
    "definition",
    "axiom", "postulate",
    "conjecture", "hypothesis",
    "proof",
    "remark", "note", "observation",
    "claim", "fact", "assumption",
    "notation", "convention",
}
```

**`ParseFocus`** controls which fields are populated in the returned
`ParseResult`. Use it to skip work you don't need:

```python
from arXiTeX.types import ParseFocus

# Only parse theorems — skip bibliography and preamble
result = parse_paper(arxiv_id="2109.06451", focus=ParseFocus.STATEMENTS)

# Only extract the LaTeX preamble
result = parse_paper(arxiv_id="2109.06451", focus=ParseFocus.PREAMBLE)

# Only parse the bibliography
result = parse_paper(arxiv_id="2109.06451", focus=ParseFocus.BIBLIOGRAPHY)
```

| `ParseFocus` | `statements` | `preamble` | `bibliography` |
|---|---|---|---|
| `ALL` | ✓ | ✓ | ✓ |
| `STATEMENTS` | ✓ | | |
| `PREAMBLE` | | ✓ | |
| `BIBLIOGRAPHY` | | | ✓ |

------------------------------------------------------------------------

### Parse a paper's bibliography

`parse_bibliography` extracts bibliography entries from a paper's source.
Supports BibTeX (`.bib`), biblatex `.bbl`, amsrefs `.bbl`, and inline
`\bibitem` entries.

```python
from arXiTeX import parse_bibliography

bibliography, is_bibtex = parse_bibliography(arxiv_id="2109.06451")

for cite_key, entry in bibliography.items():
    print(cite_key, entry.get("title"), entry.get("arxiv_id"))
```

Returns a `(dict, bool)` tuple. The dict maps cite keys to metadata
dicts (containing `title` and `arxiv_id` where found). The bool is
`True` when the source was a `.bib` file.

**Parameters**

| Parameter | Type | Default | Description |
|---|---|---|---|
| `arxiv_id` | `str` | `None` | arXiv ID. Either this or `paper_path` is required. |
| `paper_path` | `Path \| str` | `None` | Path to a source directory. Either this or `arxiv_id` is required. |
| `labels` | `List[str]` | `None` | Restrict output to these cite keys. Returns all entries when `None`. |

------------------------------------------------------------------------

## Data models

### `ArXivPaper`

```python
class ArXivPaper(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str]         # formatted as "First Middle Last"
    url: str
    categories: List[str]      # categories[0] is the primary category
    updated_at: datetime
    journal_ref: Optional[str]
    doi: Optional[str]
    license: Optional[str]     # stored as a URL when available
    abstract: str
    citation_count: Optional[int]
    reference_ids: List[str]
```

### `Statement`

```python
class Statement(BaseModel):
    kind: str                  # e.g. "theorem", "lemma", "proof"
    ref: Optional[str]         # numbering as it appears in the document, e.g. "1.1"
    note: Optional[str]        # optional title or caption
    label: Optional[str]       # LaTeX \label{...} key
    body: str                  # raw LaTeX body
    proof: Optional[str]       # raw LaTeX proof, if present
    pre_context: Optional[str] # text before the statement (regex mode only)
    post_context: Optional[str] # text after the statement (regex mode only)
```

### `ParseResult`

```python
@dataclass
class ParseResult:
    statements: Optional[List[Statement]]
    preamble: Optional[str]
    bibliography: Optional[Dict[str, Dict[str, str]]]
    bibliography_bibtex: Optional[bool]
```
