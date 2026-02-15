import multiprocessing
from typing import List, Optional

embedder = None

def embed_texts_with_hg(
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
    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as e:
        raise ImportError("Embedding features require `pip install arXiTeX[embedding]`") from e

    global embedder

    if embedder is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        embedder = SentenceTransformer(hg_embedder, device=device)
        embedder.eval()

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