"""
Hybrid retrieval: vector similarity + keyword search.

Combines semantic matching (embeddings) with lexical matching (keyword)
for better recall on queries where important terms appear literally in code.
"""
from indexer.chunkers.base_chunker import CodeChunk
from indexer.vector_store import VectorStore
from llm.ollama_client import OllamaClient


def _chunk_key(c: CodeChunk) -> str:
    """Stable identity key for deduplication (no id field on CodeChunk)."""
    return f"{c.file_path}::{c.chunk_type}::{c.symbol_name}::{c.start_line}"


class HybridSearch:
    def __init__(self, store: VectorStore, client: OllamaClient):
        self._store = store
        self._client = client

    def search(self, query: str, top_k: int = 20) -> list[CodeChunk]:
        """
        Run vector search and keyword search in parallel, merge by
        reciprocal rank fusion (RRF).

        RRF is a simple, robust way to combine two ranked lists without
        needing to normalise scores across different systems.
        """
        vector_results = self._vector_search(query, top_k=top_k)
        keyword_results = self._keyword_search(query, top_k=top_k)

        return self._rrf_merge(vector_results, keyword_results, top_k=top_k)

    # ── Vector search ─────────────────────────────────────────────────────

    def _vector_search(self, query: str, top_k: int) -> list[CodeChunk]:
        embedding = self._client.embed(query)
        return self._store.query(embedding, top_k=top_k)

    # ── Keyword search ────────────────────────────────────────────────────

    def _keyword_search(self, query: str, top_k: int) -> list[CodeChunk]:
        """
        Search ChromaDB documents and metadata for literal query terms.

        Strategy:
        1. Extract meaningful terms from the query (skip stop words)
        2. Use ChromaDB where_document $contains for each term
        3. Also match against symbol_name and file_path in metadata
        4. Score by number of term hits, return top-k
        """
        terms = self._extract_terms(query)
        if not terms:
            return []

        # Collect chunks that match any term, count how many terms each matches
        hit_counts: dict[str, tuple[CodeChunk, int]] = {}

        for term in terms:
            # Search document content via ChromaDB
            matches = self._store.keyword_search(term, limit=top_k)
            for chunk in matches:
                key = _chunk_key(chunk)
                if key in hit_counts:
                    _, count = hit_counts[key]
                    hit_counts[key] = (chunk, count + 1)
                else:
                    hit_counts[key] = (chunk, 1)

        # Sort by number of terms matched (more = better)
        ranked = sorted(hit_counts.values(), key=lambda x: x[1], reverse=True)
        return [chunk for chunk, _ in ranked[:top_k]]

    # ── Reciprocal Rank Fusion ────────────────────────────────────────────

    def _rrf_merge(
        self,
        vector_results: list[CodeChunk],
        keyword_results: list[CodeChunk],
        top_k: int,
        k: int = 60,
    ) -> list[CodeChunk]:
        """
        Reciprocal Rank Fusion (RRF) — standard method for combining
        ranked lists from different retrieval systems.

        score(doc) = sum over lists of 1 / (k + rank)

        k=60 is the standard constant from the original RRF paper.
        """
        scores: dict[str, float] = {}
        chunk_map: dict[str, CodeChunk] = {}

        for rank, chunk in enumerate(vector_results):
            key = _chunk_key(chunk)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank)
            chunk_map[key] = chunk

        for rank, chunk in enumerate(keyword_results):
            key = _chunk_key(chunk)
            scores[key] = scores.get(key, 0) + 1.0 / (k + rank)
            chunk_map[key] = chunk

        # Sort by combined RRF score
        ranked_keys = sorted(scores, key=scores.get, reverse=True)
        return [chunk_map[key] for key in ranked_keys[:top_k]]

    # ── Term extraction ───────────────────────────────────────────────────

    @staticmethod
    def _extract_terms(query: str) -> list[str]:
        """
        Extract meaningful search terms from a natural language query.
        Removes common stop words and very short words.
        """
        stop_words = {
            "how", "does", "the", "is", "are", "was", "were", "what", "where",
            "when", "which", "who", "why", "can", "could", "would", "should",
            "will", "do", "did", "has", "have", "had", "been", "being", "be",
            "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "by", "from", "it", "its", "this", "that", "these",
            "those", "i", "me", "my", "we", "our", "you", "your", "they",
            "their", "he", "she", "his", "her", "not", "no", "so", "if",
            "about", "into", "through", "during", "before", "after",
            "implemented", "work", "handle", "handled", "works",
        }
        words = query.lower().split()
        # Keep words that are meaningful and long enough
        terms = [w.strip("?.,!\"'") for w in words if w.lower().strip("?.,!\"'") not in stop_words]
        return [t for t in terms if len(t) >= 2]
