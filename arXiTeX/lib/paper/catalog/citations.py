import os
import time
import requests
from typing import List

def fetch_paper_s2(
    arxiv_ids: List[str],
    retries: int = 3,
    _attempt: int = 0,
) -> tuple[List[int | None], List[List[str]]]:
    """
    Fetches the citation count and references of papers by their arXiv IDs using
    SemanticScholar.

    Parameters
    ----------
    arxiv_ids : List[str]
        List of papers' arXiv IDs.
    retries : int, optional
        Number of retries allowed on failure. Default 3.

    Returns
    -------
    citation_counts : List[int | None]
        The number of citations, or None if not found, for each paper in the same order.
    all_reference_ids : List[List[str]]
        The list of ARXIV (preferred), DOI-prefixed, or S2-prefixed reference IDs
        for each paper in the same order.
    """
    empty_result = [None] * len(arxiv_ids), [[] for _ in arxiv_ids]

    arxiv_ids_formatted = ["ARXIV:" + arxiv_id.split("v")[0] for arxiv_id in arxiv_ids]

    try:
        time.sleep(2)  # guarantee we don't make more than 1 request per second

        scholar_res = requests.post(
            "https://api.semanticscholar.org/graph/v1/paper/batch",
            params={"fields": "citationCount,references.paperId,references.externalIds"},
            json={"ids": arxiv_ids_formatted},
            headers={"x-api-key": os.getenv("SEMANTIC_SCHOLAR_API_KEY")},
        )

        if scholar_res.status_code == 429:
            raise ValueError("SemanticScholar rate limit hit (429)")

        if not scholar_res.ok:
            raise ValueError(f"SemanticScholar response not OK: {scholar_res.status_code}")

        scholar_data = scholar_res.json()

        citation_counts = []
        all_reference_ids = []

        for paper_json in scholar_data:
            citation_counts.append(
                paper_json.get("citationCount", None) if paper_json else None
            )

            reference_ids = []
            for ref in (paper_json.get("references", []) if paper_json else []):
                external_ids = ref.get("externalIds") or {}

                if "ArXiv" in external_ids:
                    reference_ids.append("ARXIV:" + external_ids["ArXiv"])
                elif "DOI" in external_ids:
                    reference_ids.append("DOI:" + external_ids["DOI"])
                elif s2_id := ref.get("paperId"):
                    reference_ids.append("S2:" + s2_id)

            all_reference_ids.append(reference_ids)

        return citation_counts, all_reference_ids

    except Exception as e:
        if retries > 0:
            sleep_s = 2 ** _attempt
            print(f"Sleeping {sleep_s}s for SemanticScholar ({e})")
            time.sleep(sleep_s)
            return fetch_paper_s2(arxiv_ids, retries - 1, _attempt + 1)

    return empty_result