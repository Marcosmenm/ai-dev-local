# repo-assistant

Local AI assistant for querying any code repository using only local models (no cloud APIs).

## What it does
Point it at any project folder. Index once. Ask questions about the code in plain English.

## Stack
| Layer | Tool |
|---|---|
| Embeddings | `mxbai-embed-large` via Ollama |
| Vector DB | ChromaDB (local, persistent) |
| Chunking | Tree-sitter (PHP, TS/TSX) + fallback |
| LLM | `qwen2.5-coder:7b` via Ollama |
| CLI | typer + rich |

## Quick start
```bash
source ../repo-assistant-env/bin/activate
python main.py index --repo /path/to/project
python main.py ask "How does authentication work?"
python main.py stats
```

## Key commands
```bash
python main.py index --repo /path   # index a project
python main.py index --force        # wipe + re-index (asks confirmation)
python main.py ask "question"       # ask with streaming answer
python main.py ask "question" --debug   # show retrieved chunks first
python main.py stats --repo /path   # show index stats
```

## Config
Edit `.env` to change defaults (repo path, models, top-k values).
See `config.py` for all available settings.

## Architecture
→ See [docs/development-analysis.md](docs/development-analysis.md) for a complete analysis of what changed from the original plan and why.
→ See [docs/codebase-map.md](docs/codebase-map.md) for a map of every file and its purpose.
→ See [docs/architecture.md](docs/architecture.md) for full design details.
→ See [docs/decisions.md](docs/decisions.md) for why each key decision was made (keep this updated).
→ See [docs/adding-languages.md](docs/adding-languages.md) to add chunking support for new languages.

## Rules
- Never commit `.env` (contains local paths)
- Never commit `chroma_db/` (large binary data)
- Ollama must be running before any command (`ollama serve`)
- Do NOT parallelize embedding calls — serial only (16GB RAM constraint)
- Each repo gets its own ChromaDB collection (derived from folder name)
