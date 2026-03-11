from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CodeChunk:
    content: str
    file_path: str
    chunk_type: str      # "function", "class", "component", "block", "file_header"
    symbol_name: str     # function/class name, or "" if not applicable
    start_line: int
    end_line: int
    language: str

    def token_estimate(self) -> int:
        return int(len(self.content.split()) * 1.3)

    def display_label(self) -> str:
        if self.symbol_name:
            return f"{self.file_path} :: {self.symbol_name}() (lines {self.start_line}-{self.end_line})"
        return f"{self.file_path} (lines {self.start_line}-{self.end_line})"


class BaseChunker(ABC):
    def __init__(self, max_tokens: int = 400):
        self.max_tokens = max_tokens

    @abstractmethod
    def chunk(self, file_path: str, source: str) -> list[CodeChunk]:
        pass

    def _split_by_tokens(
        self, content: str, file_path: str, language: str, start_line: int = 1
    ) -> list[CodeChunk]:
        """Fallback: split large content into token-capped blocks."""
        lines = content.splitlines()
        chunks = []
        current_lines: list[str] = []
        current_start = start_line

        for i, line in enumerate(lines):
            current_lines.append(line)
            approx_tokens = int(len(" ".join(current_lines).split()) * 1.3)
            if approx_tokens >= self.max_tokens:
                chunks.append(
                    CodeChunk(
                        content="\n".join(current_lines),
                        file_path=file_path,
                        chunk_type="block",
                        symbol_name="",
                        start_line=current_start,
                        end_line=current_start + len(current_lines) - 1,
                        language=language,
                    )
                )
                current_start = current_start + len(current_lines)
                current_lines = []

        if current_lines:
            chunks.append(
                CodeChunk(
                    content="\n".join(current_lines),
                    file_path=file_path,
                    chunk_type="block",
                    symbol_name="",
                    start_line=current_start,
                    end_line=current_start + len(current_lines) - 1,
                    language=language,
                )
            )
        return chunks
