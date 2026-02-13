import bibtexparser
from pathlib import Path
from typing import List,Optional
from tempfile import TemporaryDirectory
from arXiTeX.lib.utils.download_arxiv_paper import download_arxiv_paper

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
        if not bib_file.suffix == '.bib':
            continue
            
        try:
            with open(bib_file, 'r', encoding='utf-8') as f:
                bib_database = bibtexparser.load(f)
            
            for entry in bib_database.entries:
                cite_key = entry.get('ID')
                if not cite_key:
                    continue
                if labels is not None and cite_key not in labels:
                    continue
                
                metadata = {
                    'title': entry.get('title', '').strip('{}').strip(),
                    'arxiv': entry.get('arxiv') or entry.get('eprint'),
                    'doi': entry.get('doi'),
                    'url': entry.get('url'),
                    'authors': entry.get('author', '').split(' and ') if entry.get('author') else []
                }
                
                if metadata['arxiv']:
                    arxiv_id = metadata['arxiv'].replace('arXiv:', '').strip()
                    metadata['arxiv'] = arxiv_id
                
                metadata = {k: v for k, v in metadata.items() if v}
                
                bibliography[cite_key] = metadata
                
        except Exception as e:
            print(f"Error parsing {bib_file}: {e}")
            continue
    
    return bibliography