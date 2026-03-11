import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

from indexer.chunkers.base_chunker import BaseChunker, CodeChunk

TSX_LANGUAGE = Language(tsts.language_tsx())
TS_LANGUAGE = Language(tsts.language_typescript())

# Node types that represent meaningful code units in TS/TSX
FUNCTION_TYPES = {
    "function_declaration",
    "arrow_function",
    "method_definition",
}

EXPORT_WRAPPING_TYPES = {
    "export_statement",
    "lexical_declaration",
    "variable_declaration",
}


class TypescriptChunker(BaseChunker):
    def __init__(self, max_tokens: int = 400):
        super().__init__(max_tokens)
        self._tsx_parser = Parser(TSX_LANGUAGE)
        self._ts_parser = Parser(TS_LANGUAGE)

    def chunk(self, file_path: str, source: str) -> list[CodeChunk]:
        is_tsx = file_path.endswith(".tsx")
        parser = self._tsx_parser if is_tsx else self._ts_parser
        tree = parser.parse(source.encode())
        lines = source.splitlines()
        chunks: list[CodeChunk] = []

        for node in tree.root_node.children:
            extracted = self._extract_from_node(node, lines, file_path)
            chunks.extend(extracted)

        if not chunks:
            chunks.extend(self._split_by_tokens(source, file_path, "typescript"))

        return chunks

    def _extract_from_node(self, node, lines: list[str], file_path: str) -> list[CodeChunk]:
        chunks = []

        if node.type == "export_statement":
            inner = node.child_by_field_name("declaration") or (
                node.children[-1] if node.children else None
            )
            if inner:
                name = self._extract_name(inner, lines)
                if name:
                    content = self._node_source(node, lines)
                    token_est = int(len(content.split()) * 1.3)
                    if token_est > self.max_tokens:
                        chunks.extend(
                            self._split_by_tokens(
                                content, file_path, "typescript", node.start_point[0] + 1
                            )
                        )
                    else:
                        chunks.append(
                            CodeChunk(
                                content=content,
                                file_path=file_path,
                                chunk_type=self._chunk_type(inner),
                                symbol_name=name,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                                language="typescript",
                            )
                        )
                    return chunks

        elif node.type in ("function_declaration", "class_declaration"):
            name = self._extract_name(node, lines)
            content = self._node_source(node, lines)
            token_est = int(len(content.split()) * 1.3)
            if token_est > self.max_tokens:
                chunks.extend(
                    self._split_by_tokens(
                        content, file_path, "typescript", node.start_point[0] + 1
                    )
                )
            else:
                chunks.append(
                    CodeChunk(
                        content=content,
                        file_path=file_path,
                        chunk_type=self._chunk_type(node),
                        symbol_name=name or "",
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        language="typescript",
                    )
                )

        return chunks

    def _extract_name(self, node, lines: list[str]) -> str:
        # Try direct name field
        name_node = node.child_by_field_name("name")
        if name_node:
            return self._node_source(name_node, lines).strip()
        # For variable declarations like: const MyComponent = ...
        for child in node.children:
            if child.type == "variable_declarator":
                id_node = child.child_by_field_name("name")
                if id_node:
                    return self._node_source(id_node, lines).strip()
        return ""

    def _chunk_type(self, node) -> str:
        t = node.type
        if "class" in t:
            return "class"
        if "function" in t or "arrow" in t or "method" in t:
            return "function"
        return "component"

    def _node_source(self, node, lines: list[str]) -> str:
        start = node.start_point[0]
        end = node.end_point[0] + 1
        return "\n".join(lines[start:end])
