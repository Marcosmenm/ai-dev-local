# Codebase Map

Quick reference for every file, what it does, and its key components.
Keep this updated when files are added, renamed, or significantly changed.

---

## Root

| File | Purpose |
|---|---|
| `main.py` | CLI entry point. Three commands: `index`, `ask`, `stats`. Uses `typer` for args, `rich` for progress bars and tables. `--force` asks confirmation before clearing index. |
| `config.py` | Loads `.env` via `pydantic-settings`. All tunables in one place. `collection_name()` auto-derives ChromaDB collection from folder name. |
| `requirements.txt` | Pinned dependencies. Install with `pip install -r requirements.txt`. |
| `CLAUDE.md` | Orchestrator. Quick-start, key commands, rules. Links to docs instead of duplicating them. |

---

## `llm/`

| File | Key functionality |
|---|---|
| `ollama_client.py` | `health_check()` on startup, `embed(text)` → 1024-dim vector, `generate(prompt, stream=True)` → token generator, `score_relevance(query, chunk)` → int 0–10 for reranking |
| `prompt_templates.py` | `SYSTEM_PROMPT` (repo-agnostic instruction) + `QUERY_TEMPLATE` (context + question format) |

---

## `indexer/`

| File | Key functionality |
|---|---|
| `file_scanner.py` | Walks repo, skips `vendor/`, `node_modules/`, `.claude/`, etc. Returns `(path, language)` pairs. Handles `.blade.php` priority over `.php`. |
| `file_header.py` | Extracts first 40 lines of each file (imports, namespace, class decl) as a `file_header` chunk for dependency context |
| `embedder.py` | Calls Ollama `mxbai-embed-large` per chunk. Prepends language prefix before embedding (improves precision). Serial processing — no parallelism. |
| `vector_store.py` | ChromaDB wrapper. Cosine space collection, deterministic chunk IDs (MD5 hash), incremental indexing by mtime (`metadata.json`), `upsert_chunks()`, `query()`, `get_stats()` |

### `indexer/chunkers/`

| File | Key functionality |
|---|---|
| `base_chunker.py` | `CodeChunk` dataclass (`content`, `file_path`, `chunk_type`, `symbol_name`, `start_line`, `end_line`, `language`). `BaseChunker` ABC with `_split_by_tokens()` fallback. |
| `php_chunker.py` | Tree-sitter PHP. Extracts classes + methods. Small classes (≤5 methods) → one chunk. Large classes → method-per-chunk with class header prepended. |
| `typescript_chunker.py` | Tree-sitter TSX/TS. Extracts exported functions, React components, hooks, class declarations. |
| `blade_chunker.py` | Simple text splitter for `.blade.php` files (minimal in TagMyLink). |
| `fallback_chunker.py` | Line-based token-capped splitter for any unknown file type. |

---

## `retriever/`

| File | Key functionality |
|---|---|
| `vector_search.py` | Embeds the query → ChromaDB cosine search → returns top-20 candidates |
| `reranker.py` | Asks `qwen2.5-coder:7b` to score each of the 20 candidates (0–10) → keeps top-6. Adds ~2–3s, doubles answer quality. |
| `context_builder.py` | Formats top-6 chunks + their file headers into fenced code blocks under 6000 tokens. Pulls file headers from ChromaDB by metadata filter. |

---

## `agent/`

| File | Key functionality |
|---|---|
| `repo_agent.py` | Orchestrator. `index()` — scans, chunks, embeds, stores. `query()` — search → rerank → build context → stream answer. `clear_index()` — called only after CLI confirmation. `stats()` — returns collection metrics. |

---

## `docs/`

| File | Purpose |
|---|---|
| `codebase-map.md` | This file. What every file does. |
| `architecture.md` | Full design rationale, pipeline diagrams, key decisions explained |
| `decisions.md` | Running log of why each non-obvious decision was made. Keep updated. |
| `adding-languages.md` | Step-by-step guide to add Tree-sitter chunking support for a new language |
