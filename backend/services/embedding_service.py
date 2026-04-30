import os
import math
from openai import OpenAI

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    return _client


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embed texts via OpenAI text-embedding-3-large. Returns list of embedding vectors."""
    if not texts:
        return []
    client = _get_client()
    # OpenAI allows up to 2048 inputs per batch; chunk if needed
    all_embeddings = []
    batch_size = 2048
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(model='text-embedding-3-large', input=batch)
        all_embeddings.extend([item.embedding for item in resp.data])
    return all_embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def search_embeddings(query_embedding: list[float], items: list[dict], top_k: int = 10) -> list[dict]:
    """Rank items by cosine similarity to query_embedding.

    Each item must have an 'embedding' key. Returns top_k items sorted by score,
    with a 'similarity' field added.
    """
    scored = []
    for item in items:
        emb = item.get('embedding')
        if not emb:
            continue
        sim = cosine_similarity(query_embedding, emb)
        scored.append({**item, 'similarity': sim})
    scored.sort(key=lambda x: x['similarity'], reverse=True)
    return scored[:top_k]
