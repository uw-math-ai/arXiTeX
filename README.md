# arXiTeX

Helpers to Build the Theorem Search Dataset

------------------------------------------------------------------------

## Overview

**arXiTeX** is a Python package for constructing a large-scale corpus of
mathematical theorems and their informal, natural-language
representations ("slogans").

It is designed to support:

-   Theorem-level semantic search
-   AI proof assistants
-   Mathematical retrieval and reasoning systems
-   Dataset construction for ML research

Our work powers the theorem search system described in our paper and
demo:

-   **Paper:** https://arxiv.org/abs/2602.05216
-   **Demo:** https://huggingface.co/spaces/uw-math-ai/theorem-search
-   **Dataset subset:**
    https://huggingface.co/datasets/uw-math-ai/theorem-search-dataset

The full internal dataset contains:

-   9M+ theorems
-   From ~700,000 papers
-   Sourced from [arxiv](arxiv.org) (primarily), [ProofWiki](https://proofwiki.org/wiki/Main_Page), [The Stacks Project](https://stacks.math.columbia.edu/), and many more

However, only ~15% of arXiv papers use permissive licenses (CC BY, CC
BY-SA, CC0). For that reason, we *cannot* distribute the full dataset.

Instead, arXiTeX provides the tooling to rebuild the dataset yourself.

------------------------------------------------------------------------

## What This Package Does

arXiTeX provides helpers to:

-   Catalog papers and metadata
-   Parse LaTeX sources into structured theorem objects
-   Extract theorem bodies, proofs, labels, and references
-   Validate parsed theorems

It does **NOT**:

-   Provide database code
-   Perform upserts
-   Manage infrastructure

We hosted our database on AWS internally. For reference implementation scripts, see our repo: https://github.com/uw-math-ai/TheoremSearch/tree/main/pipeline

------------------------------------------------------------------------

## Installation

Install directly from GitHub:

```
pip install git+https://github.com/uw-math-ai/arXiTeX.git
```

We recommend installing inside a virtual environment.

------------------------------------------------------------------------

## Usage

### 1. Catalog arXiv Papers

Use `paper_catalog` to iterate through papers in batches.

``` python
from arXiTeX import paper_catalog
from arXiTeX.types import Paper

CATEGORIES = ["stat.ML", "math"]

for paper_batch in paper_catalog(
    categories=CATEGORIES,
    batch_size=100,
):
    for paper in paper_batch:
        print(paper.id, paper.title)
```

This yields batches of structured `Paper` objects.

We use [SemanticScholar](https://www.semanticscholar.org/) for citation counts. Therefore, the generator works best with a SemanticScholar API key (https://www.semanticscholar.org/product/api):

In a `.env`:
```
SEMANTIC_SCHOLAR_API_KEY=...
```

Otherwise, please consider using a tiny `batch_size` (e.g. 1 or 2) and adding delays in your `paper_catalog` loop.

------------------------------------------------------------------------

### 2. Parse a Paper into Theorems

You can parse either:

-   A local LaTeX source directory
-   An arXiv ID (automatically downloaded)

``` python
from arXiTeX import parse_paper
from arXiTeX.types import Theorem, TheoremValidationLevel

theorems_from_local: list[Theorem] = parse_paper(
    paper_path="path/to/paper",
    validation_level=TheoremValidationLevel.Paper,
    timeout=10,
)

theorems_from_arxiv: list[Theorem] = parse_paper(
    arxiv_id="2109.06451"
)
```

Each call returns a list of validated `Theorem` objects.

------------------------------------------------------------------------

## Core Data Models

We use [`pydantic`](https://docs.pydantic.dev/latest/) for schema validation and Python typing for clarity
and safety.

### Paper

``` python
class Paper(BaseModel):
    id: str
    title: str
    license: Optional[str]
    authors: List[str]
    link: str
    abstract: str
    journal_ref: Optional[str]
    categories: List[str]
    citations: Optional[int]
```

Notes:

-   `authors` are formatted as "First Middle Last"
-   `categories[0]` is the primary category
-   `license` is stored as a URL when available
-   `citations` may be None if unavailable

------------------------------------------------------------------------

### Theorem

``` python
class Theorem(BaseModel):
    type: TheoremType
    ref: str
    note: Optional[str]
    label: Optional[str]
    body: str
    proof: Optional[str]
```

Notes:

-   `type` is either `Theorem`, `Lemma`, `Proposition`, or `Corollary`
-   `note` is an optional theorem title or caption
-   `label` is an internal LaTeX label (i.e `\label{...}`)
-   `body` is the raw LaTeX theorem body with simple macros resolved
-   `proof` is the raw LaTeX proof (if present) with simple macros resolved

------------------------------------------------------------------------

## Contributing

We welcome issues and pull requests. If you are building theorem-level
search, proof assistants, or structured math datasets, we would love to
collaborate.
