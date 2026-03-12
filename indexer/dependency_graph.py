"""
Lightweight dependency graph built during indexing.

Extracts import relationships from source files and stores them as
simple maps. During retrieval, expands top-k chunks by 1 hop to
include related files the LLM needs for architecture understanding.

Only tracks project-local imports — framework/vendor imports are ignored.
"""
import json
import re
from pathlib import Path


# PHP: use App\Services\CardService  →  "CardService"
_PHP_USE_RE = re.compile(r"^use\s+App\\(.+);", re.MULTILINE)

# TypeScript/JS: import ... from "../../services/card-api"
# import ... from "../models/user"
# Matches relative imports only (starts with . or ..)
_TS_IMPORT_RE = re.compile(
    r"""^import\s+.*?\s+from\s+["'](\.[^"']+)["']""",
    re.MULTILINE,
)


class DependencyGraph:
    """
    Maps files to their project-local imports.

    Structure:
        imports_map: { "/abs/path/CardController.php": ["CardService", "Card", "UserService"] }
        symbol_to_files: { "CardService": ["/abs/path/CardService.php"] }
    """

    def __init__(self):
        self.imports_map: dict[str, list[str]] = {}
        self.symbol_to_files: dict[str, list[str]] = {}

    def add_file(self, file_path: str, source: str, language: str) -> None:
        """Extract imports from a source file and register its symbols."""
        if language == "php" or language == "blade":
            self._extract_php(file_path, source)
        elif language in ("typescript", "javascript"):
            self._extract_ts(file_path, source)

    def expand(self, file_paths: list[str], max_extra: int = 10) -> list[str]:
        """
        Given a list of file paths from retrieval results, return
        additional file paths that are imported by those files.

        Only returns files not already in the input list.
        Limited to max_extra results to keep context manageable.
        """
        original = set(file_paths)
        expanded = []

        for fp in file_paths:
            symbols = self.imports_map.get(fp, [])
            for sym in symbols:
                for candidate in self.symbol_to_files.get(sym, []):
                    if candidate not in original and candidate not in expanded:
                        expanded.append(candidate)
                        if len(expanded) >= max_extra:
                            return expanded

        return expanded

    def save(self, path: Path) -> None:
        """Persist graph to JSON file."""
        data = {
            "imports_map": self.imports_map,
            "symbol_to_files": self.symbol_to_files,
        }
        path.write_text(json.dumps(data, indent=2))

    def load(self, path: Path) -> bool:
        """Load graph from JSON file. Returns True if loaded successfully."""
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            self.imports_map = data.get("imports_map", {})
            self.symbol_to_files = data.get("symbol_to_files", {})
            return True
        except (json.JSONDecodeError, OSError, KeyError):
            return False

    # ── PHP extraction ────────────────────────────────────────────────────

    def _extract_php(self, file_path: str, source: str) -> None:
        r"""
        Extract from PHP:
            use App\\Services\\CardService      -> symbol "CardService"
            use App\\Models\\Card               -> symbol "Card"
            use App\\Enums\\UserTypes           -> symbol "UserTypes"
            use App\\Traits\\Passwords          -> symbol "Passwords"

        Skips: Illuminate, Carbon, Validator, etc.
        """
        # Register this file's own symbol (class name from filename)
        own_symbol = Path(file_path).stem  # CardController.php → CardController
        if own_symbol not in self.symbol_to_files:
            self.symbol_to_files[own_symbol] = []
        if file_path not in self.symbol_to_files[own_symbol]:
            self.symbol_to_files[own_symbol].append(file_path)

        # Extract imports
        imports = []
        for match in _PHP_USE_RE.finditer(source):
            fqn = match.group(1)  # "Services\CardService"
            symbol = fqn.split("\\")[-1]  # "CardService"

            # Handle aliased imports: use App\Models\File as ImageFile
            if " as " in symbol:
                symbol = symbol.split(" as ")[-1].strip()

            imports.append(symbol)

        if imports:
            self.imports_map[file_path] = imports

    # ── TypeScript/JS extraction ──────────────────────────────────────────

    def _extract_ts(self, file_path: str, source: str) -> None:
        """
        Extract from TypeScript/JS:
            import User from "../../models/user"        → symbol "user"
            import { toast } from "react-toastify"      → SKIP (package)
            import CardForm from "../components/CardForm" → symbol "CardForm"

        Only tracks relative imports (project-local).
        """
        # Register this file's own symbol
        own_symbol = Path(file_path).stem
        # Strip common suffixes for better matching
        for suffix in (".d", ".test", ".spec"):
            if own_symbol.endswith(suffix):
                own_symbol = own_symbol[: -len(suffix)]

        if own_symbol not in self.symbol_to_files:
            self.symbol_to_files[own_symbol] = []
        if file_path not in self.symbol_to_files[own_symbol]:
            self.symbol_to_files[own_symbol].append(file_path)

        # Extract relative imports
        imports = []
        for match in _TS_IMPORT_RE.finditer(source):
            import_path = match.group(1)  # "../../services/card-api"
            # Get the filename part as the symbol
            symbol = import_path.split("/")[-1]
            # Remove extension if present
            symbol = re.sub(r"\.(tsx?|jsx?|vue)$", "", symbol)
            imports.append(symbol)

        if imports:
            self.imports_map[file_path] = imports
