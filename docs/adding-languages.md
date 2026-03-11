# Adding a New Language

## 1. Install the tree-sitter grammar

```bash
pip install tree-sitter-<language>
```

Check available grammars at: https://github.com/tree-sitter

## 2. Create a chunker

Create `indexer/chunkers/<language>_chunker.py`:

```python
import tree_sitter_<language> as ts_lang
from tree_sitter import Language, Parser
from indexer.chunkers.base_chunker import BaseChunker, CodeChunk

LANG = Language(ts_lang.language())

class MyChunker(BaseChunker):
    def __init__(self, max_tokens=400):
        super().__init__(max_tokens)
        self._parser = Parser(LANG)

    def chunk(self, file_path: str, source: str) -> list[CodeChunk]:
        tree = self._parser.parse(source.encode())
        lines = source.splitlines()
        # Extract meaningful nodes (functions, classes, etc.)
        # Return list[CodeChunk]
        ...
```

Key points:
- Each `CodeChunk` needs: `content`, `file_path`, `chunk_type`, `symbol_name`, `start_line`, `end_line`, `language`
- Use `self._split_by_tokens()` (from `BaseChunker`) as fallback for oversized chunks
- Keep chunks under `self.max_tokens` (default 400 token estimate)

## 3. Register the chunker

In `agent/repo_agent.py`, add to `self._chunkers`:
```python
self._chunkers = {
    ...
    "go": GoChunker(settings.max_chunk_tokens),
}
```

## 4. Register the file extension

In `indexer/file_scanner.py`, add to `EXTENSION_MAP`:
```python
EXTENSION_MAP = {
    ...
    ".go": "go",
}
```

## 5. Test it

```bash
python main.py index --file /path/to/sample.go
python main.py ask "What does the main function do?" --debug
```
