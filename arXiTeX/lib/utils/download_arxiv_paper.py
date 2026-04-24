import requests
import gzip
import tarfile
import io
from pathlib import Path


def download_arxiv_paper(cwd: Path, arxiv_id: str) -> Path:
    """
    Downloads an arXiv paper's source files from the arXiv API.

    Parameters
    ----------
    cwd : Path
        Directory to extract the paper's source files into.
    arxiv_id : str
        arXiv id of the paper.

    Returns
    -------
    paper_dir : Path
        The directory containing the downloaded source files.
    """
    safe_id = arxiv_id.replace("/", "-")
    paper_dir = cwd / safe_id

    paper_res = requests.get(f"https://arxiv.org/src/{arxiv_id}")
    paper_res.raise_for_status()

    paper_dir.mkdir(exist_ok=False)
    unzipped = gzip.decompress(paper_res.content)

    try:
        with tarfile.open(fileobj=io.BytesIO(unzipped), mode="r:*") as tf:
            tf.extractall(path=paper_dir)
    except Exception:
        with open(paper_dir / "main.tex", "wb") as main_file:
            main_file.write(unzipped)

    return paper_dir
