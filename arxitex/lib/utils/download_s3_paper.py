import gzip
import io
import tarfile
from pathlib import Path
from typing import Tuple

import boto3


def _parse_uri(uri: str) -> Tuple[str, str]:
    without_scheme = uri[len("s3://"):]
    bucket, _, key = without_scheme.partition("/")
    return bucket, key


def download_s3_paper(cwd: Path, s3_uri: str) -> Path:
    """
    Downloads a paper's source files from a `s3://` tarball.

    The tarball is expected to be gzipped. Falls back to writing the decompressed bytes to
    `main.tex` if untar fails (mirrors `download_arxiv_paper`).

    Parameters
    ----------
    cwd : Path
        Directory to extract the paper's source files into.
    s3_uri : str
        S3 URI of the paper's tarball (e.g. ``s3://papers-bucket/blueprint/apap.tar.gz``).

    Returns
    -------
    paper_dir : Path
        The directory containing the extracted source files.
    """

    bucket, key = _parse_uri(s3_uri)
    slug = Path(key).name
    for suffix in (".tar.gz", ".tgz", ".gz"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
            break

    paper_dir = cwd / slug
    paper_dir.mkdir(exist_ok=False)

    buf = io.BytesIO()
    boto3.client("s3").download_fileobj(bucket, key, buf)
    raw = buf.getvalue()

    try:
        unzipped = gzip.decompress(raw)
    except OSError:
        unzipped = raw

    try:
        with tarfile.open(fileobj=io.BytesIO(unzipped), mode="r:*") as tf:
            tf.extractall(path=paper_dir)
    except Exception:
        with open(paper_dir / "main.tex", "wb") as main_file:
            main_file.write(unzipped)

    return paper_dir
