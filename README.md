<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/logo-dark.png">
    <img alt="arXiTeX" src="images/logo-light.png" width="440">
  </picture>
</p>

<p align="center">A Python library for parsing arXiv papers.</p>

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

The `"llm"` method needs an extra: `pip install "arXiTeX[llm] @ git+https://github.com/uw-math-ai/arXiTeX.git"`.

The `"tex"` method needs a TeX engine on your `PATH` —
[tectonic](https://tectonic-typesetting.github.io/) (recommended, a single
self-contained binary) or a `pdflatex` from an existing TeX Live/MiKTeX install.
The `"regex"` method has no system dependencies.

------------------------------------------------------------------------

## Usage

### Catalog arXiv paper metadata

`paper_catalog` streams metadata for arXiv papers in batches, filtered
by category. It uses the [arXiv Kaggle dataset](https://www.kaggle.com/datasets/Cornell-University/arxiv)
and enriches each paper with citation counts and reference IDs via
[Semantic Scholar](https://www.semanticscholar.org/).

```python
import arXiTeX as arx

for batch in arx.paper_catalog(
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

Everything goes through one object: **`Parser`**. Configure *how* to parse once,
then call `.parse(...)` on any number of papers. A paper source can be an arXiv
ID (downloaded automatically), a local path, or an `s3://` URI — auto-detected.

```python
import arXiTeX as arx

parser = arx.Parser(method="tex")      # real TeX engine; macros/packages expanded natively

result = parser.parse("2109.06451")    # arXiv ID
# result = parser.parse("path/to/paper/")          # local directory or .tex file
# result = parser.parse(s3_uri="s3://bucket/p.tar.gz")

print("parsed with:", result.method_used)
for stmt in result.statements:
    print(stmt.kind, stmt.ref, "-", stmt.note)
    print(stmt.body)
    if stmt.proof:
        print(stmt.proof)
```

#### Methods

There are three parsing methods, from fastest to most capable:

| Method | How it works | Needs | Best for |
|---|---|---|---|
| `"regex"` | Pattern-matches environments and expands simple macros. | nothing | speed, huge corpora, no system deps |
| `"tex"` | Runs a **real TeX engine** over an instrumented copy of the paper, so packages, `\newtheorem` numbering, conditionals, and `\input`s all resolve natively. | a TeX engine on `PATH` | accuracy on arbitrary packages/macros |
| `"llm"` | Sends section-aware chunks to an LLM and merges the extracted statements. | `pip install 'arXiTeX[llm]'` + API key | messy sources, semantic edge cases |

The `"tex"` method uses [**tectonic**](https://tectonic-typesetting.github.io/)
by default (a single self-contained binary that fetches only the packages a
paper needs). To use an existing TeX Live install instead, pass
`Tex(engine="pdflatex")`. The `"llm"` method is provider-agnostic via
[litellm](https://github.com/BerriAI/litellm): pass any model string, e.g.
`Llm(model="anthropic/claude-sonnet-5")` or `Llm(model="openai/gpt-4o")`, with
the provider's API key in the environment (or `api_key=...`).

```python
import arXiTeX as arx

arx.Parser(method="regex")                       # fast, no deps
arx.Parser(method=arx.Tex(engine="pdflatex"))    # real TeX via local TeX Live
arx.Parser(method=arx.Llm(model="openai/gpt-4o"))  # LLM extraction
```

#### Fallback chains

Pass a **list** of methods to try each in order until one yields statements —
useful across a large, heterogeneous corpus. `result.method_used` tells you
which one produced the output.

```python
# Try the real TeX engine; fall back to regex if it's unavailable or fails.
parser = arx.Parser(method=["tex", "regex"])     # this is the default
```

**Parameters** (`Parser(...)`)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `method` | `str \| Method \| list` | `("tex", "regex")` | `"regex"`, `"tex"`, `"llm"`, a configured `Tex(...)`/`Llm(...)`, or a list forming a fallback chain. |
| `kinds` | `Set[str]` | broad preset | Statement types to keep. |
| `focus` | `ParseFocus \| str` | `"all"` | Which parts of the paper to populate. |
| `validation` | `ValidationLevel \| str` | `"paper"` | `"paper"` (validate whole parse), `"statement"` (drop invalid ones), or `"none"`. |
| `context` | `int` | `0` | Characters of surrounding text before/after each statement. **`regex` only.** |
| `timeout` | `int` | `None` | Max seconds per `.parse()` call. |

**`.parse(...)`** takes the source positionally (auto-detected) or as exactly one
of `arxiv_id=`, `path=`, or `s3_uri=`.

**`kinds`** defaults to:

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

**`focus`** controls which fields are populated in the returned `ParseResult`,
so you can skip work you don't need:

```python
arx.Parser(focus="statements").parse("2109.06451")     # skip preamble + bibliography
arx.Parser(focus="preamble").parse("2109.06451")       # just the LaTeX preamble
arx.Parser(focus="bibliography").parse("2109.06451")   # just the bibliography
```

| `focus` | `statements` | `preamble` | `bibliography` |
|---|---|---|---|
| `"all"` | ✓ | ✓ | ✓ |
| `"statements"` | ✓ | | |
| `"preamble"` | | ✓ | |
| `"bibliography"` | | | ✓ |

#### Command line

Installing the package also provides an `arXiTeX` CLI:

```
arXiTeX 2109.06451 -o statements.jsonl
arXiTeX path/to/paper/ -m tex -m regex           # fallback chain
arXiTeX 2109.06451 -m tex --engine pdflatex
arXiTeX 2109.06451 -m llm --model openai/gpt-4o
```

------------------------------------------------------------------------

### Parse a paper's bibliography

`parse_bibliography` extracts bibliography entries from a paper's source.
Supports BibTeX (`.bib`), biblatex `.bbl`, amsrefs `.bbl`, and inline
`\bibitem` entries.

```python
import arXiTeX as arx

bibliography, is_bibtex = arx.parse_bibliography(arxiv_id="2109.06451")

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
    body: str                  # LaTeX body, user macros expanded where possible
    proof: Optional[str]       # raw LaTeX proof, if present
    pre_context: Optional[str] # text before the statement (regex method + context only)
    post_context: Optional[str] # text after the statement (regex method + context only)
```

### `ParseResult`

```python
@dataclass
class ParseResult:
    statements: Optional[List[Statement]]
    preamble: Optional[str]
    bibliography: Optional[Dict[str, Dict[str, str]]]
    bibliography_bibtex: Optional[bool]
    method_used: Optional[str]   # which method produced `statements` (e.g. "tex", "regex")
```

------------------------------------------------------------------------

## Development

```
pip install -e ".[dev]"
pytest
```

The `tests/` folder contains small, self-contained LaTeX projects (in
`tests/fixtures/`) that double as readable examples of what each method handles —
shared counters, unnumbered environments, `thmtools`, multi-file `\input`s,
proof-by-reference, nested macros, and a no-statements paper. The `tex` tests are
skipped automatically when no TeX engine is on `PATH`, and the `llm` tests use a
mocked backend (no API key needed). See `tests/README.md` for details.
