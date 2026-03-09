"""
Main file of paper module. Provides a helper to iterate over arXiv metadata.
"""

import zipfile
import io
import json
from typing import Iterator, List
from pathlib import Path
from datetime import datetime, timezone
from arXiTeX.types import ArXivPaper
from .download_arxiv_metadata import download_arxiv_metadata
from .citations import fetch_paper_s2
from .default_categories import DEFAULT_CATEGORIES

def paper_catalog(
    download_dir: Path | str,
    categories: List[str] = DEFAULT_CATEGORIES,
    batch_size: int = 100
) -> Iterator[List[ArXivPaper]]:
    """
    Generator that yields arXiv paper metadata. Filters by categories and returns results in the
    specified batch size. Citations and references work best with a SemanticScholar API key stored
    as SEMANTIC_SCHOLAR_API_KEY in your '.env'.

    Parameters
    ----------
    download_dir : Path | str
        Path to directory of 'arxiv.zip', the zip of the arXiv Kaggle dataset. If this directory
        doesn't include 'arxiv.zip', just downloads it there with a progress bar.
    categories : List[str], optional
        List of categories to filter papers by. Specify either the whole category name (i.e.
        math.AG) or just the main category (i.e. math). Default, our recommended arXiv categories.
    batch_size : int, optional
        Size of batch of paper metadatas to yield. Default, 100
    
    Returns
    -------
    paper_catalog : Iterator[List[Paper]]
        Iterator of paper metadatas. Yields batches of papers.
    """

    if isinstance(download_dir, str):
        download_dir = Path(download_dir)

    metadata_zip = download_dir / "arxiv.zip"
    if not metadata_zip.exists():
        download_arxiv_metadata(download_dir)
        
    batch: List[ArXivPaper] = []

    def category_match(row_categories: List[str]) -> bool:
        for rc in row_categories:
            for c in categories:
                if (c == rc) or ("." not in c and rc.startswith(c + ".")):
                    return True
        
        return False

    with zipfile.ZipFile(metadata_zip, "r") as z:
        with z.open(z.namelist()[0], "r") as raw, io.TextIOWrapper(raw, encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                paper_id = row.get("id")
                row_categories = row.get("categories").split()
                
                if not category_match(row_categories):
                    continue

                paper = ArXivPaper(
                    arxiv_id=paper_id,
                    title=row.get("title"),
                    authors=[" ".join(filter(None, [f, *m, l])) for (l, f, *m) in row.get("authors_parsed")],
                    url="https://arxiv.org/pdf/" + row.get("id"),
                    categories=row_categories,
                    updated_at=datetime.strptime(row.get("update_date"), "%Y-%m-%d").replace(tzinfo=timezone.utc),
                    journal_ref=row.get("journal-ref"),
                    doi=row.get("doi"),
                    license=row.get("license"),
                    abstract=row.get("abstract"),
                    citation_count=None,
                    reference_ids=[]
                )

                batch.append(paper)

                if len(batch) >= batch_size:
                    ks, rs = fetch_paper_s2([paper.id for paper in batch])
                    for k, r, paper in zip(ks, rs, batch):
                        paper.citation_count = k
                        paper.reference_ids = r

                    yield batch
                    batch.clear()

            if len(batch) > 0:
                ks, rs = fetch_paper_s2([paper.id for paper in batch])
                for k, r, paper in zip(ks, rs, batch):
                    paper.citation_count = k
                    paper.reference_ids = r

                yield batch
                batch.clear()