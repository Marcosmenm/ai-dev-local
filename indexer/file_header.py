from indexer.chunkers.base_chunker import CodeChunk

HEADER_LINES = 40  # Max lines to extract as file header


def extract_file_header(file_path: str, source: str, language: str) -> CodeChunk | None:
    """
    Extract the first HEADER_LINES lines of a file as a header chunk.
    This captures imports, namespace, class declarations, and use statements —
    the dependency context that individual method chunks lack.
    """
    lines = source.splitlines()
    if not lines:
        return None

    header = "\n".join(lines[:HEADER_LINES])
    end_line = min(HEADER_LINES, len(lines))

    return CodeChunk(
        content=header,
        file_path=file_path,
        chunk_type="file_header",
        symbol_name="",
        start_line=1,
        end_line=end_line,
        language=language,
    )
