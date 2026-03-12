import time

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

# mxbai-embed-large has a 512-token context window.
# Dense PHP config/JS code tokenizes at ~1 token per 2 chars worst case.
# 900 chars ≈ 450 tokens — safely under the 512 limit for all code types.
MAX_EMBED_CHARS = 900


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

        # Truncate to stay within mxbai-embed-large's 512-token context window
        if len(text) > MAX_EMBED_CHARS:
            text = text[:MAX_EMBED_CHARS]

        try:
            embedding = client.embed(text)
            results.append((chunk, embedding))
        except Exception as e:
            print(f"[Warning] Failed to embed {chunk.file_path}: {e}")
            continue

        if progress_callback:
            progress_callback(i + 1, len(chunks))

        # Small delay to prevent Ollama overload
        time.sleep(0.1)

    return results
