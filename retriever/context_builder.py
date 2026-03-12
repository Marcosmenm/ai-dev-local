from indexer.chunkers.base_chunker import CodeChunk
from indexer.dependency_graph import DependencyGraph
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


def build_context(
    chunks: list[CodeChunk],
    store: VectorStore,
    graph: DependencyGraph | None = None,
) -> str:
    """
    Format retrieved chunks into a structured context block for the LLM.

    1. Injects file headers for each unique source file (import context)
    2. Adds the retrieved chunks themselves
    3. If a dependency graph is available, expands by 1 hop —
       fetches file headers of imported files so the LLM sees
       the architecture around the retrieved code.
    """
    seen_files: set[str] = set()
    file_headers: list[CodeChunk] = []

    for chunk in chunks:
        if chunk.chunk_type != "file_header" and chunk.file_path not in seen_files:
            seen_files.add(chunk.file_path)
            header = _get_file_header(chunk.file_path, store)
            if header:
                file_headers.append(header)

    # Graph expansion: get headers of files imported by retrieved files
    dep_headers: list[CodeChunk] = []
    if graph:
        expanded_files = graph.expand(list(seen_files), max_extra=8)
        for dep_path in expanded_files:
            if dep_path not in seen_files:
                header = _get_file_header(dep_path, store)
                if header:
                    dep_headers.append(header)

    context_parts = []
    total_tokens = 0

    # 1. File headers from retrieved chunks
    for header in file_headers:
        section = _format_chunk(header, len(context_parts) + 1)
        tokens = int(len(section.split()) * 1.3)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            break
        context_parts.append(section)
        total_tokens += tokens

    # 2. Retrieved chunks
    for chunk in chunks:
        if chunk.chunk_type == "file_header":
            continue
        section = _format_chunk(chunk, len(context_parts) + 1)
        tokens = int(len(section.split()) * 1.3)
        if total_tokens + tokens > MAX_CONTEXT_TOKENS:
            break
        context_parts.append(section)
        total_tokens += tokens

    # 3. Dependency expansion headers (if budget remains)
    if dep_headers:
        for header in dep_headers:
            section = _format_chunk(header, len(context_parts) + 1, label_prefix="[dep] ")
            tokens = int(len(section.split()) * 1.3)
            if total_tokens + tokens > MAX_CONTEXT_TOKENS:
                break
            context_parts.append(section)
            total_tokens += tokens

    return "\n\n".join(context_parts)


def _format_chunk(chunk: CodeChunk, index: int, label_prefix: str = "") -> str:
    fence = LANG_FENCE.get(chunk.language, "")
    label = chunk.display_label()
    return f"### [{index}] {label_prefix}{label}\n```{fence}\n{chunk.content}\n```"


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
