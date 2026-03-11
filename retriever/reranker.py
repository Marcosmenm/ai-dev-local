from indexer.chunkers.base_chunker import CodeChunk
from llm.ollama_client import OllamaClient


class Reranker:
    def __init__(self, client: OllamaClient):
        self._client = client

    def rerank(
        self, query: str, chunks: list[CodeChunk], top_k: int = 6
    ) -> list[CodeChunk]:
        if len(chunks) <= top_k:
            return chunks

        scored: list[tuple[int, CodeChunk]] = []
        for chunk in chunks:
            score = self._client.score_relevance(query, chunk.content)
            scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [chunk for _, chunk in scored[:top_k]]
