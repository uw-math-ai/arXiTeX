import requests
import gzip
import tarfile
import io
from pathlib import Path
from typing import Optional

s3 = None

def _get_s3():
    import boto3

    global s3

    if s3 is None:
        s3 = boto3.client("s3")
    
    return s3

def download_arxiv_paper(
    cwd: Path, 
    arxiv_id: str,
    s3_bundle_key: Optional[str] = None,
    s3_bytes_range: Optional[str] = None
) -> Path:
    """
    Downloads a arXiv paper's source files from S3 or the API.

    Parameters
    ----------
    cwd : Path
        Directory's to add the paper's source files to.
    arxiv_id : Optional[str], optional
        arXiv id of a paper. Either this or paper_path must be used.
    s3_bundle_key: str, optional
        Bundle key of paper in arXiv's S3 bucket. Default, None.
    s3_bytes_range: str, optional
        Bytes range of paper in arXiv's S3 bucket. Default, None.
        
    Returns
    -------
    paper_dir : Path
        The paper's downloaded source files.
    """

    if (s3_bundle_key is not None) and (s3_bytes_range is not None):
        s3_mode = True
    elif (s3_bundle_key is not None) or (s3_bytes_range is not None):
        raise ValueError("s3_bundle_key and s3_bytes_range must be either both None or both strings")
    else:
        s3_mode = False
    
    safe_id = arxiv_id.replace("/", "-")
    paper_dir = cwd / safe_id

    try:
        if s3_mode:
            s3 = _get_s3()

            res = s3.get_object(
                Bucket="arxiv",
                Key=s3_bundle_key,
                Range=s3_bytes_range,
                RequestPayer="requester"
            )

            b = res["Body"].read()
        else:
            paper_res = requests.get(f"https://arxiv.org/src/{arxiv_id}")
            paper_res.raise_for_status()

            b = paper_res.content

        paper_dir.mkdir(exist_ok=False)
        unzipped = gzip.decompress(b)

        try:
            with tarfile.open(fileobj=io.BytesIO(unzipped), mode="r:*") as tf:
                tf.extractall(path=paper_dir)
        except:
            with open(paper_dir / "main.tex", "wb") as main_file:
                main_file.write(unzipped)

        return paper_dir
    except:
        return None


    
