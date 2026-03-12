import os
import re
from pathlib import Path

# Matches bundled filenames like main-GWYJEUO4.js or chunk.abc123ef.js
_BUNDLED_FILE_RE = re.compile(r"-[A-Z0-9]{7,}\.(js|ts|css)$", re.IGNORECASE)

# Directories to always skip
SKIP_DIRS = {
    "vendor", "node_modules", "storage", ".git", "build", "dist",
    "chroma_db", "__pycache__", ".next", "coverage", "public/build",
    "bootstrap/cache", ".idea", ".vscode", ".claude",
    "DB Dump", "db_dump", "testflowswebsite", "Production_files",
}

# File extensions to index, mapped to language label
EXTENSION_MAP = {
    ".php": "php",
    ".tsx": "typescript",
    ".ts": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".py": "python",
    ".rb": "ruby",
    ".go": "go",
    ".java": "java",
    ".cs": "csharp",
    ".rs": "rust",
    ".swift": "swift",
    ".kt": "kotlin",
    ".vue": "vue",
}

# Skip files matching these suffixes
SKIP_SUFFIXES = {
    ".min.js", ".min.css", ".lock", ".log", ".map",
    ".svg", ".png", ".jpg", ".jpeg", ".gif", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".woff", ".woff2", ".ttf",
    ".snap", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx",
}


def scan_repo(repo_path: str) -> list[tuple[str, str]]:
    """
    Walk repo_path and return list of (absolute_file_path, language) tuples.
    Respects SKIP_DIRS and EXTENSION_MAP.
    """
    results = []
    root = Path(repo_path).resolve()

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place (modifies walk)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]

        for filename in filenames:
            filepath = Path(dirpath) / filename

            # Skip by suffix or bundled filename pattern
            name_lower = filename.lower()
            if any(name_lower.endswith(s) for s in SKIP_SUFFIXES):
                continue
            if _BUNDLED_FILE_RE.search(filename):
                continue

            # Blade templates: special case (.blade.php takes priority over .php)
            if filename.endswith(".blade.php"):
                results.append((str(filepath), "blade"))
                continue

            ext = filepath.suffix.lower()
            if ext in EXTENSION_MAP:
                results.append((str(filepath), EXTENSION_MAP[ext]))

    return results


def get_stats(repo_path: str) -> dict[str, int]:
    """Return count of indexable files per language."""
    files = scan_repo(repo_path)
    counts: dict[str, int] = {}
    for _, lang in files:
        counts[lang] = counts.get(lang, 0) + 1
    return counts
