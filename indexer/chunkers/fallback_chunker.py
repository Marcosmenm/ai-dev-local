from indexer.chunkers.base_chunker import BaseChunker, CodeChunk


class FallbackChunker(BaseChunker):
    def chunk(self, file_path: str, source: str) -> list[CodeChunk]:
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else "text"
        return self._split_by_tokens(source, file_path, ext)
