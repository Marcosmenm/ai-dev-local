from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    repo_path: str = ""
    ollama_base_url: str = "http://localhost:11434"
    embedding_model: str = "mxbai-embed-large"
    chat_model: str = "qwen2.5-coder:7b"
    chroma_db_path: str = "./chroma_db"
    chroma_collection: str = "auto"
    top_k_candidates: int = 20
    top_k_results: int = 6
    max_chunk_tokens: int = 400

    def collection_name(self, repo_path: str | None = None) -> str:
        path = repo_path or self.repo_path
        return Path(path).name.lower().replace(" ", "_").replace("-", "_")


settings = Settings()
