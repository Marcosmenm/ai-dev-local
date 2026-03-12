from pathlib import Path
from typing import Generator

from config import settings
from indexer.chunkers.blade_chunker import BladeChunker
from indexer.chunkers.fallback_chunker import FallbackChunker
from indexer.chunkers.php_chunker import PhpChunker
from indexer.chunkers.typescript_chunker import TypescriptChunker
from indexer.dependency_graph import DependencyGraph
from indexer.embedder import embed_chunks
from indexer.file_header import extract_file_header
from indexer.file_scanner import scan_repo
from indexer.vector_store import VectorStore
from llm.ollama_client import OllamaClient
from llm.prompt_templates import QUERY_TEMPLATE, SYSTEM_PROMPT
from retriever.context_builder import build_context
from retriever.hybrid_search import HybridSearch
from retriever.reranker import Reranker


class IndexStats:
    def __init__(self):
        self.files_scanned = 0
        self.files_skipped = 0
        self.chunks_created = 0


class RepoAgent:
    def __init__(self, repo_path: str | None = None):
        self.repo_path = repo_path or settings.repo_path
        self._collection_name = settings.collection_name(self.repo_path)

        self._client = OllamaClient()
        self._client.health_check()

        db_path = str(
            (Path(__file__).parent.parent / settings.chroma_db_path).resolve()
        )
        self._store = VectorStore(db_path, self._collection_name)
        self._search = HybridSearch(self._store, self._client)
        self._reranker = Reranker(self._client)

        # Dependency graph — persisted next to ChromaDB
        self._graph = DependencyGraph()
        self._graph_path = Path(db_path) / f"{self._collection_name}_deps.json"
        self._graph.load(self._graph_path)

        self._chunkers = {
            "php": PhpChunker(settings.max_chunk_tokens),
            "typescript": TypescriptChunker(settings.max_chunk_tokens),
            "javascript": TypescriptChunker(settings.max_chunk_tokens),
            "blade": BladeChunker(settings.max_chunk_tokens),
        }
        self._fallback = FallbackChunker(settings.max_chunk_tokens)

    # ── Indexing ──────────────────────────────────────────────────────────────

    def clear_index(self) -> None:
        """Wipe all indexed data for this collection. Called only after explicit user confirmation."""
        self._store.delete_collection()

    def index(
        self,
        progress_callback=None,
        file_path: str | None = None,
    ) -> IndexStats:
        stats = IndexStats()
        files = scan_repo(self.repo_path)

        if file_path:
            files = [(f, l) for f, l in files if f == file_path]

        stats.files_scanned = len(files)

        for fp, lang in files:
            # Always build dependency graph (fast regex, no embedding needed)
            try:
                source = Path(fp).read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            self._graph.add_file(fp, source, lang)

            if not self._store.file_needs_indexing(fp):
                stats.files_skipped += 1
                continue

            chunker = self._chunkers.get(lang, self._fallback)
            chunks = chunker.chunk(fp, source)

            header = extract_file_header(fp, source, lang)
            if header:
                chunks.insert(0, header)

            if not chunks:
                continue

            embedded = embed_chunks(chunks, self._client)
            self._store.upsert_chunks(
                [c for c, _ in embedded],
                [e for _, e in embedded],
            )
            self._store.mark_file_indexed(fp)

            stats.chunks_created += len(chunks)

            if progress_callback:
                progress_callback(fp, len(chunks))

        # Persist dependency graph
        self._graph.save(self._graph_path)

        return stats

    # ── Querying ──────────────────────────────────────────────────────────────

    def query(self, question: str, debug: bool = False) -> Generator[str, None, None]:
        if self._store.get_stats()["total_chunks"] == 0:
            yield (
                "[No index found. Run: python main.py index --repo "
                f"{self.repo_path}]"
            )
            return

        candidates = self._search.search(question, top_k=settings.top_k_candidates)
        top_chunks = self._reranker.rerank(
            question, candidates, top_k=settings.top_k_results
        )

        if debug:
            yield "## Retrieved Chunks\n"
            for i, chunk in enumerate(top_chunks, 1):
                yield f"[{i}] {chunk.display_label()}\n"
            yield "\n## Answer\n"

        context = build_context(top_chunks, self._store, self._graph)
        prompt = (
            f"{SYSTEM_PROMPT}\n\n"
            + QUERY_TEMPLATE.format(context=context, question=question)
        )
        yield from self._client.generate(prompt, stream=True)

    # ── Stats ─────────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        return self._store.get_stats()
