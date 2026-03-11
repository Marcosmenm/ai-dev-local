from indexer.chunkers.base_chunker import BaseChunker, CodeChunk


class BladeChunker(BaseChunker):
    def chunk(self, file_path: str, source: str) -> list[CodeChunk]:
        return self._split_by_tokens(source, file_path, "blade")
