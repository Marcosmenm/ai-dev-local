# Design Decisions & Lessons Learned

Running log of key decisions made during development. Update this whenever a non-obvious choice is made.

---

## 2026-03-11 — Initial architecture

### Why no LlamaIndex or LangChain
Both add 400–800MB of transitive dependencies and impose document abstractions that conflict with custom AST chunking. Direct ChromaDB + httpx gives full control with ~10 Python files.

### Why mxbai-embed-large over nomic-embed-text
Better benchmark performance on code and technical queries. 1024-dim vs 768-dim. Same install path (Ollama pull). Trade-off: ~670MB vs ~274MB download — worth it for code retrieval quality.

### Why Tree-sitter for chunking (not fixed token windows)
Code is not prose. A 500-token text split will break a function in the middle, destroying the semantic unit the LLM needs. Tree-sitter extracts complete functions/classes/components — retrieval returns exactly the right code unit. Used by GitHub Copilot and Sourcegraph Cody for the same reason.

**Tree-sitter 0.23.x API note:** Use `Language(tsphp.language_php())` — NOT the old `Language.build_library()`. The grammar packages must match the `tree-sitter` core version exactly (both pinned to 0.23.x).

### Why LLM reranking (not just vector search)
Embedding similarity finds semantically similar text but can miss functionally relevant code. The reranker asks `qwen2.5-coder:7b` to score each of the top-20 candidates (0–10). Adds ~2–3s per query but significantly improves answer quality, especially for architecture and dependency questions.

### Why file headers in context
Individual method chunks lack dependency context. `CardController::claim()` doesn't show `use StripeService`. The first 40 lines of each source file capture imports, namespace, and class declaration — the dependency map the LLM needs to give accurate answers.

### Why serial Ollama calls (no parallelism)
16GB RAM on M3. Running two LLM operations simultaneously causes memory thrashing. Serial queue is the right constraint for this hardware profile.

### Why cosine distance in ChromaDB
`metadata={"hnsw:space": "cosine"}` must be set at **collection creation** — cannot change later. Cosine performs better than L2 for semantic similarity in code search. Default is L2.

### Why deterministic chunk IDs
`MD5(file_path + symbol_name + start_line)` — stable across re-runs. Enables incremental updates via `upsert` instead of delete+insert. Also prevents duplicate chunks if a file is indexed twice.

### Why skip `.claude/` folder during indexing
TagMyLink's `.claude/` contains session history, PRPs, and markdown documentation — not source code. Including it pollutes the vector index with non-executable content and inflates chunk counts. Add `--include-docs` flag in Phase 2 if architecture Q&A from those docs is needed.

### Why `clear_index()` is separated from `index()`
Deleting the ChromaDB collection is irreversible. The method is intentionally split from the normal index flow and only called after an explicit CLI confirmation (`typer.confirm()`). `--force` flag triggers the confirmation, normal `index` never touches it.

### Why `CodeChunk.symbol_name` matters
The `symbol_name` field (`CardController::getPublicCard`, `useCardEditor`, etc.) is stored in ChromaDB metadata and surfaced in the LLM context headers. This lets the model respond with precise references like "See `CardController::getPublicCard()` at line 45" rather than just a file name.

---

## What NOT to do

- **Do not parallelize Ollama embedding calls** — causes OOM on 16GB
- **Do not use LlamaIndex for this stack** — it fights custom chunking at every layer
- **Do not commit `.env`** — contains local absolute paths (public repo)
- **Do not commit `chroma_db/`** — large binary, machine-specific, regeneratable
- **Do not use L2 distance in ChromaDB** — set cosine at collection creation, cannot change after
- **Do not use `tree-sitter` < 0.23.x** — old API (`Language.build_library`) is deprecated and incompatible with current grammar packages

---

## Open questions / Phase 2 decisions needed

- [ ] Add dependency graph (imports + function calls from Tree-sitter AST) for hybrid retrieval
- [ ] Model routing: route simple lookups to smaller model, complex reasoning to 7B
- [ ] `--include-docs` flag to optionally index `.claude/documentation/` for architecture Q&A
- [ ] Git hook for auto re-index on commit
