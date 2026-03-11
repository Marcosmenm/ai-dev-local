from indexer.chunkers.base_chunker import CodeChunk
from indexer.vector_store import VectorStore

MAX_CONTEXT_TOKENS = 5500  # Leave ~2500 for model response

LANG_FENCE = {
    "php": "php",
    "typescript": "typescript",
    "javascript": "javascript",
    "python": "python",
    "blade": "html",
    "file_header": "php",
}


def build_context(chunks: list[CodeChunk], store: VectorStore) -> str:
    """
    Format retrieved chunks into a structured context block for the LLM.
    Also injects the file header for each unique source file to provide
    import/dependency context.
    """
    # Collect unique file paths from non-header chunks
    seen_files: set[str] = set()
    file_headers: list[CodeChunk] = []

    for chunk in chunks:
        if chunk.chunk_type != "file_header" and chunk.file_path not in seen_files:
            seen_files.add(chunk.file_path)
            # Pull the file header from the store for this file
            header = _get_file_header(chunk.file_path, store)
            if header:
                file_headers.append(header)

    context_parts = []
    total_tokens = 0

    # Add file headers first (dependency context)
    for header in file_headers:
        section = _format_chunk(header, len(context_parts) + 1)
        tokens = int(len(section.split()) * 1.3)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            break
        context_parts.append(section)
        total_tokens += tokens

    # Add retrieved chunks
    for chunk in chunks:
        if chunk.chunk_type == "file_header":
            continue
        section = _format_chunk(chunk, len(context_parts) + 1)
        tokens = int(len(section.split()) * 1.3)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            break
        context_parts.append(section)
        total_tokens += tokens

    return "\n\n".join(context_parts)


def _format_chunk(chunk: CodeChunk, index: int) -> str:
    fence = LANG_FENCE.get(chunk.language, "")
    label = chunk.display_label()
    return f"### [{index}] {label}\n```{fence}\n{chunk.content}\n```"


def _get_file_header(file_path: str, store: VectorStore) -> CodeChunk | None:
    """Query the store for the file_header chunk of a given file."""
    try:
        results = store._collection.get(
            where={"$and": [{"file_path": file_path}, {"chunk_type": "file_header"}]},
            include=["documents", "metadatas"],
            limit=1,
        )
        if results["documents"]:
            doc = results["documents"][0]
            meta = results["metadatas"][0]
            return CodeChunk(
                content=doc,
                file_path=meta["file_path"],
                chunk_type=meta["chunk_type"],
                symbol_name=meta["symbol_name"],
                start_line=meta["start_line"],
                end_line=meta["end_line"],
                language=meta["language"],
            )
    except Exception:
        pass
    return None
