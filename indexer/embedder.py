from indexer.chunkers.base_chunker import CodeChunk
from llm.ollama_client import OllamaClient

# Prefix that improves embedding precision for code retrieval
LANG_PREFIX = {
    "php": "PHP code",
    "typescript": "TypeScript/React code",
    "javascript": "JavaScript code",
    "python": "Python code",
    "blade": "Blade template",
    "file_header": "File header with imports",
}


def embed_chunks(
    chunks: list[CodeChunk],
    client: OllamaClient,
    progress_callback=None,
) -> list[tuple[CodeChunk, list[float]]]:
    """
    Embed a list of CodeChunks using the Ollama embedding model.
    Returns list of (chunk, embedding_vector) pairs.
    Processes serially — do NOT parallelize (16GB RAM constraint).
    """
    results = []
    for i, chunk in enumerate(chunks):
        prefix = LANG_PREFIX.get(chunk.language, "Code")
        if chunk.symbol_name:
            text = f"{prefix} — {chunk.symbol_name}:\n{chunk.content}"
        else:
            text = f"{prefix}:\n{chunk.content}"

        embedding = client.embed(text)
        results.append((chunk, embedding))

        if progress_callback:
            progress_callback(i + 1, len(chunks))

    return results
