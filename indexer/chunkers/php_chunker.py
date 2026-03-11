import tree_sitter_php as tsphp
from tree_sitter import Language, Parser

from indexer.chunkers.base_chunker import BaseChunker, CodeChunk

PHP_LANGUAGE = Language(tsphp.language_php())


class PhpChunker(BaseChunker):
    def __init__(self, max_tokens: int = 400):
        super().__init__(max_tokens)
        self._parser = Parser(PHP_LANGUAGE)

    def chunk(self, file_path: str, source: str) -> list[CodeChunk]:
        tree = self._parser.parse(source.encode())
        lines = source.splitlines()
        chunks: list[CodeChunk] = []

        # Find all class declarations
        classes = self._find_nodes(tree.root_node, "class_declaration")

        if not classes:
            # No classes — chunk top-level functions or fall back
            functions = self._find_nodes(tree.root_node, "function_definition")
            for fn in functions:
                chunks.append(self._node_to_chunk(fn, lines, file_path, "function"))
            if not functions:
                chunks.extend(self._split_by_tokens(source, file_path, "php"))
            return chunks

        for cls in classes:
            class_name = self._get_node_text(cls, lines, "name")
            methods = self._find_nodes(cls, "method_declaration")

            if len(methods) <= 5:
                # Small class — emit as one chunk
                chunks.append(self._node_to_chunk(cls, lines, file_path, "class", class_name))
            else:
                # Large class — emit class header + each method separately
                class_header = self._extract_class_header(cls, lines)
                for method in methods:
                    method_name = self._get_node_text(method, lines, "name")
                    content = class_header + "\n    // ...\n\n" + self._node_source(method, lines)
                    start = method.start_point[0] + 1
                    end = method.end_point[0] + 1
                    token_est = int(len(content.split()) * 1.3)
                    if token_est > self.max_tokens:
                        # Method too large — split it
                        chunks.extend(
                            self._split_by_tokens(
                                self._node_source(method, lines),
                                file_path,
                                "php",
                                start,
                            )
                        )
                    else:
                        chunks.append(
                            CodeChunk(
                                content=content,
                                file_path=file_path,
                                chunk_type="function",
                                symbol_name=f"{class_name}::{method_name}",
                                start_line=start,
                                end_line=end,
                                language="php",
                            )
                        )
        return chunks

    def _find_nodes(self, node, node_type: str) -> list:
        results = []
        if node.type == node_type:
            results.append(node)
        for child in node.children:
            results.extend(self._find_nodes(child, node_type))
        return results

    def _node_source(self, node, lines: list[str]) -> str:
        start = node.start_point[0]
        end = node.end_point[0] + 1
        return "\n".join(lines[start:end])

    def _node_to_chunk(self, node, lines: list[str], file_path: str, chunk_type: str, symbol_name: str = "") -> CodeChunk:
        return CodeChunk(
            content=self._node_source(node, lines),
            file_path=file_path,
            chunk_type=chunk_type,
            symbol_name=symbol_name,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            language="php",
        )

    def _get_node_text(self, node, lines: list[str], child_type: str) -> str:
        for child in node.children:
            if child.type == child_type:
                return self._node_source(child, lines).strip()
        return ""

    def _extract_class_header(self, cls_node, lines: list[str]) -> str:
        """Extract class declaration up to the opening brace."""
        start = cls_node.start_point[0]
        header_lines = []
        for line in lines[start:start + 8]:
            header_lines.append(line)
            if "{" in line:
                break
        return "\n".join(header_lines)
