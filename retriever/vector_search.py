from indexer.chunkers.base_chunker import CodeChunk
from indexer.vector_store import VectorStore
from llm.ollama_client import OllamaClient


class VectorSearch:
    def __init__(self, store: VectorStore, client: OllamaClient):
        self._store = store
        self._client = client

    def search(self, query: str, top_k: int = 20) -> list[CodeChunk]:
        embedding = self._client.embed(query)
        return self._store.query(embedding, top_k=top_k)
