import torch
import multiprocessing
from typing import List, Optional
from sentence_transformers import SentenceTransformer

embedder: Optional[SentenceTransformer] = None
def _get_embedder(hg_embedder: str) -> SentenceTransformer:
    global embedder

    if embedder is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        embedder = SentenceTransformer(hg_embedder, device=device)
        embedder.eval()

    return embedder

def embed_texts(
    hg_embedder: str,
    texts: List[str],
    prompt: Optional[str] = None
) -> List:
    """
    Embeds a list of texts into vectors.

    Parameters
    ----------
    hg_embedder : str
        Embedder name from Hugging Face
    texts : List[str]
        List of texts to embed
    prompt : str, optional
        Prompt to give embedder. Default, None
    """

    embedder = _get_embedder(hg_embedder)

    with torch.inference_mode():
        if embedder.device.type == "cpu":
            n_threads = multiprocessing.cpu_count()
            torch.set_num_threads(n_threads)

            pool = embedder.start_multi_process_pool()

            try:
                embeddings = embedder.encode(
                    texts,
                    pool,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                    batch_size=len(texts),
                    prompt=prompt
                )
            finally:
                embedder.stop_multi_process_pool(pool)

    return embeddings.tolist()