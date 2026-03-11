# Architecture

## Retrieval pipeline

```
User query
    ↓
Embed with mxbai-embed-large (Ollama)
    ↓
ChromaDB cosine search → top-20 candidates
    ↓
LLM reranker (qwen2.5-coder:7b scores each 0-10) → top-6
    ↓
Context builder (chunks + file headers, <6000 tokens)
    ↓
qwen2.5-coder:7b generates answer (streaming)
```

## Indexing pipeline

```
File scanner (skips vendor/, node_modules/, .claude/, etc.)
    ↓
Tree-sitter chunker (PHP: classes/methods, TSX: components/hooks)
    ↓
File header extractor (first 40 lines: imports, namespace, class decl)
    ↓
Embedder — mxbai-embed-large via Ollama (serial, no parallelism)
    ↓
ChromaDB upsert (cosine space, deterministic IDs, incremental by mtime)
```

## Key design decisions

**Why no LlamaIndex/LangChain?**
Both add 400-800MB of transitive dependencies and impose document abstractions that fight against custom AST chunking. Direct ChromaDB + httpx is 4 files and full control.

**Why semantic chunking (Tree-sitter)?**
Code is not text. Random 500-token splits break function boundaries. Tree-sitter extracts complete functions/classes/components — the LLM gets exactly the unit it needs.

**Why mxbai-embed-large over nomic-embed-text?**
Better benchmark performance on code and technical queries. 1024-dim vs 768-dim. ~670MB download via Ollama — no Python dependencies.

**Why LLM reranking?**
Embedding similarity finds semantically close text, but may miss functionally relevant code. The reranker uses the LLM itself to score relevance (0-10) and promotes the right chunks. Adds ~2-3s but doubles answer quality.

**Why file headers in context?**
Individual method chunks lack import/dependency context. A `CardController::claim()` chunk doesn't show `use StripeService`. The file header (first 40 lines) provides the dependency map the LLM needs.

**Why no parallelism in Ollama calls?**
16GB RAM. Running two models simultaneously causes thrashing. Serial queue is the right call.

## Phase 2 extensions
- Model routing: 0.8B for classification, 7B for reasoning
- Dependency graph: import chains + function calls from Tree-sitter AST → hybrid vector+graph retrieval
- Multi-agent: planner decomposes large queries → worker agents run targeted sub-queries
- Git hook: auto re-index on commit (incremental update already designed for this)
