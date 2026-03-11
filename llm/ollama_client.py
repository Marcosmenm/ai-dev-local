import json
from typing import Generator

import httpx

from config import settings


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")

    def health_check(self) -> None:
        try:
            httpx.get(f"{self.base_url}/api/tags", timeout=3.0)
        except httpx.ConnectError:
            raise SystemExit(
                "[ERROR] Ollama is not running. Start it with: ollama serve"
            )

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            f"{self.base_url}/api/embeddings",
            json={"model": settings.embedding_model, "prompt": text},
            timeout=30.0,
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def generate(self, prompt: str, stream: bool = True) -> Generator[str, None, None]:
        with httpx.stream(
            "POST",
            f"{self.base_url}/api/generate",
            json={"model": settings.chat_model, "prompt": prompt, "stream": stream},
            timeout=120.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    chunk = json.loads(line)
                    if token := chunk.get("response"):
                        yield token
                    if chunk.get("done"):
                        break

    def score_relevance(self, query: str, chunk_content: str) -> int:
        """Ask the model to score a chunk's relevance to a query (0-10)."""
        prompt = (
            f"Score the relevance of this code snippet to the query on a scale 0-10.\n"
            f"Reply with ONLY a single integer.\n\n"
            f"Query: {query}\n\n"
            f"Code snippet:\n{chunk_content[:800]}\n\n"
            f"Score:"
        )
        result = ""
        for token in self.generate(prompt, stream=True):
            result += token
            if len(result) > 5:
                break
        try:
            return int("".join(c for c in result if c.isdigit())[:1] or "0")
        except ValueError:
            return 0
