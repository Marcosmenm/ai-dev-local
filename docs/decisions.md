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
`MD5(file_path + chunk_type + symbol_name + start_line)` — stable across re-runs. Enables incremental updates via `upsert` instead of delete+insert. Also prevents duplicate chunks if a file is indexed twice.

**Bug found and fixed:** Original hash was `MD5(file_path + symbol_name + start_line)` — missing `chunk_type`. This caused a `DuplicateIDError` in ChromaDB for small files (e.g. `vite.config.js`) where the `file_header` chunk and the first `block` chunk both had: same file_path, empty symbol_name, start_line=1. Fix: include `chunk_type` in the hash.

### Why `clear_index()` is separated from `index()`
Deleting the ChromaDB collection is irreversible. The method is intentionally split from the normal index flow and only called after an explicit CLI confirmation (`typer.confirm()`). `--force` flag triggers the confirmation, normal `index` never touches it.

### Why `CodeChunk.symbol_name` matters
The `symbol_name` field (`CardController::getPublicCard`, `useCardEditor`, etc.) is stored in ChromaDB metadata and surfaced in the LLM context headers. This lets the model respond with precise references like "See `CardController::getPublicCard()` at line 45" rather than just a file name.

### Why skip `.claude/` folder during indexing
TagMyLink's `.claude/` contains session history, PRPs, and markdown documentation — not source code. Including it pollutes the vector index with non-executable content and inflates chunk counts.

---

## 2026-03-11 — Real-world indexing fixes (discovered running against TagMyLink)

### Root cause of all 500 errors: mxbai-embed-large context window is 512 tokens
**What the plan assumed:** The `MAX_CHUNK_TOKENS=250` setting in `.env` would keep chunks small enough.

**What actually happens:** The token estimation formula `len(text.split()) * 1.3` counts whitespace-separated words and multiplies by 1.3. This significantly **underestimates** real token counts for code because:
- The embedding model (mxbai-embed-large) uses **WordPiece tokenization**, not word-level
- Camel case identifiers like `CardController` split into multiple tokens
- PHP/JS dense syntax (operators, quotes, array syntax) creates 1 token per ~2 chars
- The language prefix added by the embedder (`"PHP code — CardController:\n"`) adds extra tokens on top of the chunk content
- Import-heavy TSX files with many `from 'package'` lines are especially dense

**Worst case tested:** `config/app.php` — a Laravel config file with dense nested arrays. At 1100 chars it still exceeded the 512-token limit. Required truncating to ~900 chars.

**Fix applied:** Hard character limit `MAX_EMBED_CHARS = 900` in `embedder.py`. Text is truncated before being sent to Ollama. This is applied **at the embedding layer**, not the chunking layer — so the full chunk content is still stored in ChromaDB and shown to the LLM; only the embedding vector is computed from the truncated text. This is the correct trade-off: retrieval precision may slightly drop for very long chunks, but accuracy of LLM answers is not affected.

### typer version incompatibility
**Plan used:** `typer==0.12.5`

**What broke:** `Parameter.make_metavar() missing 1 required positional argument: 'ctx'` — click version mismatch caused option parsing to fail with "Got unexpected extra argument" for `--repo /path`.

**Fix:** Downgrade to `typer==0.9.4 + click==8.1.7`. The `Annotated` syntax still works. Requirements.txt should reflect: `typer==0.9.4`, `click==8.1.7`.

### anyio version yanked
`anyio==4.6.2` was yanked from PyPI (incorrectly tagged release). Upgraded to `anyio==4.7.0`.

### Bundled/minified JS files in production folders
**What happened:** TagMyLink has a `testflowswebsite/Flows - Production_files/` directory containing a saved website snapshot. The file `main-GWYJEUO4.js` is a production bundle — minified, no whitespace — which tokenizes at worst case (1 token per 1-2 chars). Even at 900 chars it exceeded 512 tokens.

**Fix 1:** Added `testflowswebsite` and `Production_files` to `SKIP_DIRS` in `file_scanner.py`.

**Fix 2:** Added regex pattern `_BUNDLED_FILE_RE = re.compile(r"-[A-Z0-9]{7,}\.(js|ts|css)$")` to skip any file whose name contains a hash (Vite/webpack convention for content-addressed bundles like `chunk-ABC1234.js`).

**Lesson:** Every real-world repo will have unexpected non-source directories. The current hardcoded `SKIP_DIRS` is fragile — see proposed fixes below.

---

## What NOT to do

- **Do not parallelize Ollama embedding calls** — causes OOM on 16GB
- **Do not use LlamaIndex for this stack** — it fights custom chunking at every layer
- **Do not commit `.env`** — contains local absolute paths (public repo)
- **Do not commit `chroma_db/`** — large binary, machine-specific, regeneratable
- **Do not use L2 distance in ChromaDB** — set cosine at collection creation, cannot change after
- **Do not use `tree-sitter` < 0.23.x** — old API (`Language.build_library`) is deprecated
- **Do not rely on `len(text.split()) * 1.3` as a token estimate** — it underestimates by 2–3x for dense code. Use character limits at the embedding layer as a hard cap.
- **Do not assume all .js files in a repo are source code** — production builds, vendor bundles, and saved website snapshots exist in real repos

---

## Proposed Enhancements (Next Steps)

### P1 — Folder selection UI before indexing
**Problem:** The current scanner uses a hardcoded `SKIP_DIRS` set. Every real project has unexpected directories (saved websites, legacy exports, test fixtures) that pollute the index with non-source content and cause embedding failures.

**Proposed solution:**
- New CLI command: `python main.py scan --repo /path`
- Walks the repo top-level directories, counts indexable files in each, displays a numbered table
- User ticks/unticks which subdirectories to include
- Saves exclusions to a `.repo-assistant-ignore` file at the repo root (one path per line, gitignore syntax)
- `scan_repo()` reads `.repo-assistant-ignore` on every run and merges with hardcoded `SKIP_DIRS`
- This solves the `testflowswebsite` problem permanently, without touching source code

**Why this matters:** Every project is different. TagMyLink had a website snapshot. Another project might have a `legacy_backup/` folder, `exports/`, or `docs/generated/`. You can't predict them all. User-driven ignore files scale to any repo.

### P2 — Per-file-type embedding limits
**Problem:** The global `MAX_EMBED_CHARS = 900` is set by the worst case (dense PHP config files). For most files (clean PHP classes, TypeScript components), 900 chars is overly conservative and loses context that would improve retrieval.

**Proposed solution:**
```python
MAX_EMBED_CHARS_BY_LANG = {
    "php": 900,        # config files are extremely dense
    "typescript": 1000, # imports are dense but body is readable
    "javascript": 900,  # bundled/minified risk
    "python": 1200,     # readable whitespace
    "blade": 1100,      # mostly HTML
    "file_header": 700, # always the most dense section — trim aggressively
}
```
The `file_header` type gets the tightest limit because headers (imports, namespace, use statements) are the densest section of any file — exactly what caused the failures in `config/app.php` and `bootstrap/app.php`.

### P3 — Smarter file header extraction
**Problem:** The current 40-line file header is a dumb line count. For PHP config files, 40 lines of nested arrays is not "import context" — it's config data that doesn't help the LLM understand dependencies.

**Proposed solution:** Language-aware header extraction:
- PHP: extract only `namespace`, `use` statements, and `class` declaration (stop at first method)
- TypeScript: extract only `import` statements (stop at first `export` or `function`)
- This naturally avoids the token limit problem because import sections are shorter

### P4 — `.repo-assistant-ignore` integration with existing `.gitignore`
**Problem:** Many things already excluded in `.gitignore` should also be excluded from indexing (`dist/`, `*.min.js`, generated files).

**Proposed solution:** On first `index` run, auto-read the repo's `.gitignore` and merge those patterns into the scanner's skip list. User can then override with `.repo-assistant-ignore`.

### P5 — Dependency graph expansion (Phase 1.5 — HIGH VALUE)
**Critical for professional answer quality.** External AI feedback strongly recommends this.

**Why important:** Vector search alone retrieves disconnected code snippets. A dependency graph expansion adds related files, reconstructing the full architecture flow.

**Example:** Query "How does NFC card activation work?"
- Without graph: Returns ActivateCardController alone
- With graph: Returns ActivateCardController + CardService + WalletPassGenerator + UserRepository → LLM sees the full picture

**Implementation:** ~150 lines. Build lightweight maps during indexing:
- imports: file → [imported files]
- calls: function → [called functions]
- symbols: "CardService::activate" → file_path

Then during retrieval, expand top-k chunks by 1 hop and add related files to context.

**Benefits:** Answer quality jumps 20-30%. Professional-grade retrieval (Sourcegraph, Cursor do this).

**Time:** ~4 hours. **Effort:** Medium. **Impact:** Very high.

### P6 — Phase 2 model integrations
- Model routing: classify query complexity → route to `qwen3.5-0.8B` (fast) vs `qwen3.5-2B` (standard) vs `qwen3.5-7B` (thorough)
- Multi-agent: planner decomposes large queries → worker agents run targeted sub-queries
- Git hook: auto re-index on commit using the existing incremental mtime-based updater

---

## Open questions / decisions needed

- [ ] P1: Folder selection — interactive CLI (`questionary` library?) or file-based ignore?
- [ ] P2: Per-language limits — implement as dict lookup or smarter tokenizer?
- [ ] P3: Smart header extraction — Tree-sitter already parsed, free to reuse for this
- [ ] P4: `.gitignore` merging — use `pathspec` library or implement subset manually?
- [ ] Phase 2: Which Qwen3.5 model variant to use for routing (0.8B likely sufficient for classification)
