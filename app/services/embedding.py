import json
import numpy as np
from sentence_transformers import SentenceTransformer
from app.config import settings


class EmbeddingService:
    def __init__(self, model_name: str = None):
        model_name = model_name or settings.EMBEDDING_MODEL
        self.model = SentenceTransformer(model_name)

    def generate_embedding(self, text: str) -> list[float]:
        vector = self.model.encode(text)
        return vector.tolist()

    def embedding_to_json(self, vector: list[float]) -> str:
        return json.dumps(vector)

    def json_to_embedding(self, json_str: str) -> list[float]:
        return json.loads(json_str)

    def semantic_search(self, query: str, paragraphs: list[dict], top_k: int = 3) -> list[dict]:
        if not paragraphs:
            return []
        para_texts = [p["content"] for p in paragraphs]
        query_embedding = self.model.encode(query)
        para_embeddings = self.model.encode(para_texts)
        similarities = np.dot(para_embeddings, query_embedding) / (
            np.linalg.norm(para_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )
        top_indices = np.argsort(similarities)[::-1][:top_k]
        results = []
        for idx in top_indices:
            para = paragraphs[idx]
            results.append({
                "para_index": para["para_index"],
                "content": para["content"],
                "similarity": float(similarities[idx]),
            })
        return results
