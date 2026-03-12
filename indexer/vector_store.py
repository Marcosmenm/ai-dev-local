import hashlib
import json
import os
import time
from pathlib import Path

import chromadb

from indexer.chunkers.base_chunker import CodeChunk


def _chunk_id(chunk: CodeChunk) -> str:
    key = f"{chunk.file_path}::{chunk.chunk_type}::{chunk.symbol_name}::{chunk.start_line}"
    return hashlib.md5(key.encode()).hexdigest()


class VectorStore:
    def __init__(self, db_path: str, collection_name: str):
        self.db_path = Path(db_path).resolve()
        self.collection_name = collection_name
        self._meta_path = self.db_path / "metadata.json"

        self.db_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(self.db_path))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._file_mtimes: dict[str, float] = self._load_meta()

    # ── Indexing ──────────────────────────────────────────────────────────────

    def upsert_chunks(
        self, chunks: list[CodeChunk], embeddings: list[list[float]]
    ) -> None:
        if not chunks:
            return
        ids = [_chunk_id(c) for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [
            {
                "file_path": c.file_path,
                "chunk_type": c.chunk_type,
                "symbol_name": c.symbol_name,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "language": c.language,
            }
            for c in chunks
        ]
        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

    def mark_file_indexed(self, file_path: str) -> None:
        self._file_mtimes[file_path] = os.path.getmtime(file_path)
        self._save_meta()

    def file_needs_indexing(self, file_path: str) -> bool:
        if file_path not in self._file_mtimes:
            return True
        try:
            return os.path.getmtime(file_path) > self._file_mtimes[file_path]
        except FileNotFoundError:
            return True

    def delete_collection(self) -> None:
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._file_mtimes = {}
        self._save_meta()

    # ── Querying ──────────────────────────────────────────────────────────────

    def query(self, query_embedding: list[float], top_k: int = 20) -> list[CodeChunk]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, self._collection.count() or 1),
            include=["documents", "metadatas"],
        )
        chunks = []
        for doc, meta in zip(
            results["documents"][0], results["metadatas"][0]
        ):
            chunks.append(
                CodeChunk(
                    content=doc,
                    file_path=meta["file_path"],
                    chunk_type=meta["chunk_type"],
                    symbol_name=meta["symbol_name"],
                    start_line=meta["start_line"],
                    end_line=meta["end_line"],
                    language=meta["language"],
                )
            )
        return chunks

    def keyword_search(self, term: str, limit: int = 20) -> list[CodeChunk]:
        """Search chunks by literal keyword match in document content."""
        count = self._collection.count()
        if count == 0:
            return []
        try:
            results = self._collection.get(
                where_document={"$contains": term},
                include=["documents", "metadatas"],
                limit=min(limit, count),
            )
        except Exception:
            return []
        chunks = []
        if results and results["documents"]:
            for doc, meta in zip(results["documents"], results["metadatas"]):
                chunks.append(
                    CodeChunk(
                        content=doc,
                        file_path=meta["file_path"],
                        chunk_type=meta["chunk_type"],
                        symbol_name=meta["symbol_name"],
                        start_line=meta["start_line"],
                        end_line=meta["end_line"],
                        language=meta["language"],
                    )
                )
        return chunks

    # ── Stats ─────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        count = self._collection.count()
        last_indexed = max(self._file_mtimes.values()) if self._file_mtimes else None
        files_indexed = len(self._file_mtimes)
        return {
            "total_chunks": count,
            "files_indexed": files_indexed,
            "last_indexed": last_indexed,
            "collection": self.collection_name,
        }

    # ── Metadata persistence ──────────────────────────────────────────────────

    def _load_meta(self) -> dict[str, float]:
        if self._meta_path.exists():
            try:
                return json.loads(self._meta_path.read_text())
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_meta(self) -> None:
        self._meta_path.write_text(json.dumps(self._file_mtimes))
