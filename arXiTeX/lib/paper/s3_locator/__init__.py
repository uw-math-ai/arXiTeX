import boto3
import tarfile
import re
from typing import Iterable, Iterator
from pydantic import BaseModel
from tempfile import NamedTemporaryFile
from tqdm import tqdm

class S3Location(BaseModel):
    arxiv_id: str
    bundle_key: str
    bytes_range: str

def _normalize_arxiv_id(arxiv_id: str) -> str:
    if "/" in arxiv_id:
        arxiv_id = arxiv_id.split("/", 1)[1]
    arxiv_id = re.sub(r"^([a-zA-Z-]+)(\d+)$", r"\1/\2", arxiv_id)

    return arxiv_id

def s3_locator(arxiv_ids: Iterable) -> Iterator[S3Location]:
    """
    Generator that yields locations in the S3 'arxiv' bucket for LaTeX sources of given arXiv ids.
    Useful for efficiently downloading arXiv LaTeX sources later.

    Parrameters
    -----------
    arxiv_ids : Iterable
        arXiv ids to locate.

    Returns
    -------
    s3_locator : Iterator[S3Location]
        Generator of locations: arxiv_id, bundle_key, and bytes_range
    """
    
    arxiv_ids = set(arxiv_ids)

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    
    with tqdm(
        total=len(arxiv_ids), 
        dynamic_ncols=True,
        unit=" ids"
    ) as pbar:
        for bundle_page in paginator.paginate(
            Bucket="arxiv",
            Prefix="src/",
            RequestPayer="requester"
        ):
            for bundle_obj in bundle_page.get("Contents", []):
                bundle_key = bundle_obj["Key"]
                
                try:
                    with NamedTemporaryFile() as bundle_file:
                        s3.download_fileobj(
                            "arxiv",
                            bundle_key,
                            bundle_file,
                            ExtraArgs={"RequestPayer": "requester"},
                        )
                        bundle_file.flush()
                        bundle_file.seek(0)

                        with tarfile.open(fileobj=bundle_file, mode="r:") as bundle_tar:
                            for member in bundle_tar.getmembers():
                                if not member.isfile() or not member.name.endswith(".gz"):
                                    continue
                                if not getattr(member, "size", 0):
                                    continue
                                
                                try:
                                    member_id = member.name[:-3]
                                    arxiv_id = _normalize_arxiv_id(member_id)

                                    if arxiv_id in arxiv_ids:
                                        bytes_start = getattr(member, "offset_data", None)
                                        if bytes_start is None:
                                            raise RuntimeError("member.offset_data is None")

                                        bytes_end = bytes_start + member.size - 1

                                        bundle_file.seek(bytes_start)
                                        if bundle_file.read(3) != b"\x1f\x8b\x08":
                                            raise RuntimeError("Bad gzip header")
                                        
                                        yield S3Location(
                                            arxiv_id=arxiv_id,
                                            bundle_key=bundle_key,
                                            bytes_range=f"bytes={bytes_start}-{bytes_end}"
                                        )

                                        del arxiv_ids[arxiv_id]

                                        pbar.update(1)
                                except:
                                    pass
                except:
                    pass