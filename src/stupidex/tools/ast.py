import asyncio
import difflib
import logging
import os
import tempfile
from pathlib import Path
from xml.sax.saxutils import escape

from stupidex.ast.indexer import ensure_indexed
from stupidex.ast.parser import lang_for_extension, load_query_file, parse_file, run_query
from stupidex.ast.store import ASTStore
from stupidex.domain.tool import ExecutorResult, Tool, ToolParameter, ToolParameterProperties

logger = logging.getLogger(__name__)

# Session-level hash tracking for get_function change detection (R15).
# Keyed by "{file_path}:{function_name}", values are FNV-1a hashes.
# NOT pre-populated by the indexer — only fires after the agent has received content.
_get_function_sent_hashes: dict[str, str] = {}

# Post-write callbacks registered by the AST indexer.
# edit and write tools call each callback after a successful file write.
post_write_callbacks: list = []

# FNV-1a constants (64-bit)
_FNV_OFFSET = 14695981039346656037
_FNV_PRIME = 1099511628211

# Language-specific import queries for get_function context resolution
_IMPORT_QUERIES = {
    "python": """
(import_statement) @import
(import_from_statement) @import
""",
    "javascript": """
(import_statement) @import
""",
    "typescript": """
(import_statement) @import
""",
}


def _fnv1a(text: str) -> str:
    h = _FNV_OFFSET
    for byte in text.encode("utf-8"):
        h ^= byte
        h = (h * _FNV_PRIME) & 0xFFFFFFFFFFFFFFFF
    return format(h, "016x")


def _xml_attr(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _cdata_text(value: str) -> str:
    return value.replace("]]>", "]]]]><![CDATA[>")


def _count_diff_changes(diff_text: str) -> tuple[int, int]:
    added = 0
    removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return added, removed


def _generate_diff(old: str, new: str, path: str) -> str:
    diff = difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"old/{path}",
        tofile=f"new/{path}",
        lineterm="",
    )
    return "\n".join(diff)


def _format_edit_result(
    file_path: str,
    *,
    success: bool,
    replacements: int,
    added: int,
    removed: int,
    diff_text: str = "",
    error: str | None = None,
    message: str | None = None,
) -> str:
    attrs = [
        f'path="{_xml_attr(file_path)}"',
        f'success="{str(success).lower()}"',
        f'replacements="{replacements}"',
        'replace_all="false"',
        f'added="{added}"',
        f'removed="{removed}"',
    ]
    if error:
        attrs.append(f'error="{_xml_attr(error)}"')

    lines = [f"<edit_result {' '.join(attrs)}>"]
    if message:
        lines.extend(["<message><![CDATA[", _cdata_text(message), "]]></message>"])
    if diff_text:
        lines.extend(['<diff format="unified"><![CDATA[', _cdata_text(diff_text), "]]></diff>"])
    else:
        lines.append('<diff format="unified" />')
    lines.append("</edit_result>")
    return "\n".join(lines)


def _find_extended_range(
    content_bytes: bytes, node, file_path: str
) -> tuple[int, int]:
    """Extend the node's range backward to include preceding decorators/comments."""
    start = node.start_byte
    text_before = content_bytes[:start].decode("utf-8", errors="replace")
    lines_before = text_before.split("\n")

    check_lines = 0
    for line in reversed(lines_before[:-1] if len(lines_before) > 1 else []):
        stripped = line.strip()
        if not stripped:
            break
        is_decorator = stripped.startswith("@")
        is_comment = stripped.startswith("#") or stripped.startswith("//")
        is_docstring = stripped.startswith('"""') or stripped.startswith("'''")
        is_export = stripped.startswith("export ")
        is_multiline_end = stripped.endswith("*/")
        if is_decorator or is_comment or is_docstring or is_export or is_multiline_end:
            check_lines += 1
        else:
            break

    if check_lines > 0:
        preceding = "\n".join(lines_before[-check_lines - 1:-1]) if check_lines < len(lines_before) else ""
        start = start - len(preceding.encode("utf-8")) - 1  # -1 for the newline

    return start, node.end_byte


def _atomic_write(file_path: str, content: str) -> None:
    """Write content atomically: tmp + fsync + os.replace."""
    fd, tmp_path = tempfile.mkstemp(
        dir=str(Path(file_path).parent),
        prefix=".ast_edit_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, file_path)
        dir_fd = os.open(str(Path(file_path).parent), os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise


async def _trigger_post_write_callbacks(file_path: str) -> None:
    for cb in post_write_callbacks:
        try:
            await cb(file_path)
        except Exception as e:
            logger.warning("Post-write callback failed for %s: %s", file_path, e)


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

get_file_skeleton_tool = Tool(
    name="get_file_skeleton",
    description=(
        "Get a structural outline of a source file showing only definition lines "
        "(functions, classes, methods) without reading the entire file. Use this "
        "to understand a file's structure before reading specific functions. "
        "Returns definition names with line numbers and visual separators."
    ),
    parameters=ToolParameter(
        properties={
            "file_path": ToolParameterProperties(
                type="string",
                description="Path to the source file, relative to cwd",
            ),
        },
        required=["file_path"],
    ),
    action_label="Getting skeleton...",
)

get_function_tool = Tool(
    name="get_function",
    description=(
        "Extract specific function(s) by name from a source file, including "
        "relevant imports and parent class context. Use this instead of reading "
        "an entire file when you only need one or two functions. Reports "
        '"no changes" if the function body has not changed since last retrieval.'
    ),
    parameters=ToolParameter(
        properties={
            "file_path": ToolParameterProperties(
                type="string",
                description="Path to the source file, relative to cwd",
            ),
            "function_names": ToolParameterProperties(
                type="string",
                description="Comma-separated function names to extract",
            ),
        },
        required=["file_path", "function_names"],
    ),
    action_label="Extracting function...",
)

find_symbol_references_tool = Tool(
    name="find_symbol_references",
    description=(
        "Find all definitions and references of a symbol by name across the project. "
        "Use this to understand where a symbol is defined and used before renaming "
        "or refactoring. Returns file paths with line/column ranges."
    ),
    parameters=ToolParameter(
        properties={
            "name": ToolParameterProperties(
                type="string",
                description="The symbol name to search for",
            ),
            "type_filter": ToolParameterProperties(
                type="string",
                description='Filter by symbol type: "definition", "reference", or "both" (default: "both")',
            ),
        },
        required=["name"],
    ),
    action_label="Finding references...",
)

replace_symbol_tool = Tool(
    name="replace_symbol",
    description=(
        "Replace an entire symbol definition (function, class, method) including "
        "its docstring, decorators, and comments. Use this instead of the edit tool "
        "for replacing whole functions — it handles the full range automatically "
        "and supports multiple replacements in one call with correct offsets."
    ),
    parameters=ToolParameter(
        properties={
            "file_path": ToolParameterProperties(
                type="string",
                description="Path to the source file",
            ),
            "name": ToolParameterProperties(
                type="string",
                description="The symbol name to replace",
            ),
            "new_text": ToolParameterProperties(
                type="string",
                description="The complete replacement text for the symbol definition",
            ),
        },
        required=["file_path", "name", "new_text"],
    ),
    action_label="Replacing symbol...",
)

rename_symbol_tool = Tool(
    name="rename_symbol",
    description=(
        "Rename a symbol across all files in one call. Updates all definitions "
        "and references atomically per file. Use this instead of multiple edit "
        "calls for cross-file renames."
    ),
    parameters=ToolParameter(
        properties={
            "name": ToolParameterProperties(
                type="string",
                description="The current symbol name",
            ),
            "new_name": ToolParameterProperties(
                type="string",
                description="The new symbol name",
            ),
        },
        required=["name", "new_name"],
    ),
    action_label="Renaming symbol...",
)


# ---------------------------------------------------------------------------
# Executors
# ---------------------------------------------------------------------------


async def execute_get_file_skeleton(file_path: str) -> ExecutorResult:
    try:
        filepath = Path(file_path)
        if not filepath.exists():
            return ExecutorResult(
                display=f"File not found: {file_path}",
                content=f'<ast_error tool="get_file_skeleton" file="{_xml_attr(file_path)}">'
                f"File not found: {escape(file_path)}</ast_error>",
            )

        lang_name = lang_for_extension(file_path)
        content = filepath.read_text(encoding="utf-8", errors="replace")
        query_text = load_query_file(lang_name)
        tree = parse_file(file_path, content)
        captures = run_query(tree, lang_name, query_text, content)

        definitions = []
        for cap_name, results in captures.items():
            if cap_name.startswith("name.definition."):
                for r in results:
                    definitions.append((r.start_line, r.text))

        if not definitions:
            return ExecutorResult(
                display=f"No definitions in {file_path}",
                content=f'<file_skeleton file="{_xml_attr(file_path)}" definitions="0">\n'
                "No definitions found.\n</file_skeleton>",
            )

        definitions.sort(key=lambda x: x[0])

        lines = []
        lines.append(f'<file_skeleton file="{_xml_attr(file_path)}" definitions="{len(definitions)}">')
        prev_line = None
        for line_num, name in definitions:
            if prev_line is not None and line_num > prev_line + 1:
                lines.append("  |----")
            lines.append(f"  {line_num + 1:>4} │ {name}")
            prev_line = line_num
        lines.append("</file_skeleton>")

        return ExecutorResult(
            display=f"Skeleton of {file_path}: {len(definitions)} definitions",
            content="\n".join(lines),
        )

    except ValueError as e:
        return ExecutorResult(
            display=f"Unsupported file type: {file_path}",
            content=f'<ast_error tool="get_file_skeleton" file="{_xml_attr(file_path)}">'
            f"{escape(str(e))}</ast_error>",
        )
    except Exception as e:
        logger.warning("get_file_skeleton error: %s", e)
        return ExecutorResult(
            display=f"Error: {file_path}",
            content=f'<ast_error tool="get_file_skeleton" file="{_xml_attr(file_path)}">'
            f"{escape(str(e))}</ast_error>",
        )


async def execute_get_function(
    file_path: str, function_names: str
) -> ExecutorResult:
    try:
        filepath = Path(file_path)
        if not filepath.exists():
            return ExecutorResult(
                display=f"File not found: {file_path}",
                content=f'<ast_error tool="get_function" file="{_xml_attr(file_path)}">'
                f"File not found: {escape(file_path)}</ast_error>",
            )

        names = [n.strip() for n in function_names.split(",") if n.strip()]
        if not names:
            return ExecutorResult(
                display="No function names provided",
                content='<ast_error tool="get_function">'
                "No valid function names provided.</ast_error>",
            )

        content = filepath.read_text(encoding="utf-8", errors="replace")
        lang_name = lang_for_extension(file_path)
        query_text = load_query_file(lang_name)
        tree = parse_file(file_path, content)
        captures = run_query(tree, lang_name, query_text, content)

        import_query = _IMPORT_QUERIES.get(lang_name, "")
        imports_text = ""
        if import_query:
            import_captures = run_query(tree, lang_name, import_query, content)
            import_results = import_captures.get("import", [])
            if import_results:
                imports_text = "\n".join(r.text for r in import_results)

        name_caps = captures.get("name.definition.function", [])
        method_caps = captures.get("name.definition.method", [])

        found_functions = []
        for target_name in names:
            matched = False
            for r in name_caps + method_caps:
                if r.text != target_name:
                    continue
                if r.node.parent is None:
                    continue
                func_node = r.node.parent
                if func_node.type not in (
                    "function_definition",
                    "function_declaration",
                    "method_definition",
                ):
                    parent = func_node.parent
                    if parent and parent.type in (
                        "function_definition",
                        "function_declaration",
                        "method_definition",
                    ):
                        func_node = parent
                    else:
                        continue

                class_text = ""
                p = func_node.parent
                while p is not None:
                    if p.type in ("class_definition", "class_declaration"):
                        body_node = p.child_by_field_name("body")
                        end_byte = body_node.start_byte if body_node is not None else p.end_byte
                        class_text = content.encode("utf-8")[
                            p.start_byte : end_byte
                        ].decode("utf-8", errors="replace")
                        break
                    p = p.parent

                func_text = content.encode("utf-8")[
                    func_node.start_byte : func_node.end_byte
                ].decode("utf-8", errors="replace")

                hash_key = f"{file_path}:{target_name}"
                current_hash = _fnv1a(func_text)
                last_hash = _get_function_sent_hashes.get(hash_key)

                if last_hash is not None and last_hash == current_hash:
                    found_functions.append(
                        f'<function name="{_xml_attr(target_name)}" '
                        f'file="{_xml_attr(file_path)}">\n'
                        "No changes have been made since last retrieval.\n</function>"
                    )
                else:
                    parts = []
                    parts.append(
                        f'<function name="{_xml_attr(target_name)}" '
                        f'file="{_xml_attr(file_path)}">'
                    )
                    if imports_text:
                        parts.append("<imports>")
                        parts.append(escape(imports_text))
                        parts.append("</imports>")
                    if class_text:
                        parts.append("<class_context>")
                        parts.append(escape(class_text))
                        parts.append("</class_context>")
                    parts.append("<body>")
                    parts.append(escape(func_text))
                    parts.append("</body>")
                    parts.append("</function>")
                    found_functions.append("\n".join(parts))
                    _get_function_sent_hashes[hash_key] = current_hash

                matched = True

            if not matched:
                found_functions.append(
                    f'<function name="{_xml_attr(target_name)}" '
                    f'file="{_xml_attr(file_path)}" status="not_found">\n'
                    f"Function '{escape(target_name)}' not found.\n</function>"
                )

        content_xml = (
            f'<functions file="{_xml_attr(file_path)}" count="{len(found_functions)}">\n'
            + "\n".join(found_functions)
            + "\n</functions>"
        )

        return ExecutorResult(
            display=f"Extracted {len(found_functions)} function(s) from {file_path}",
            content=content_xml,
        )

    except ValueError as e:
        return ExecutorResult(
            display=f"Unsupported file type: {file_path}",
            content=f'<ast_error tool="get_function" file="{_xml_attr(file_path)}">'
            f"{escape(str(e))}</ast_error>",
        )
    except Exception as e:
        logger.warning("get_function error: %s", e)
        return ExecutorResult(
            display=f"Error: {file_path}",
            content=f'<ast_error tool="get_function" file="{_xml_attr(file_path)}">'
            f"{escape(str(e))}</ast_error>",
        )


async def execute_find_symbol_references(
    name: str, type_filter: str = "both"
) -> ExecutorResult:
    try:
        if not name or not name.strip():
            return ExecutorResult(
                display="Empty symbol name",
                content='<ast_error tool="find_symbol_references">'
                "Symbol name is required.</ast_error>",
            )

        if type_filter not in ("both", "definition", "reference"):
            return ExecutorResult(
                display="Invalid type_filter",
                content=f'<ast_error tool="find_symbol_references">'
                f'Invalid type_filter "{escape(type_filter)}". '
                f"Must be: definition, reference, or both.</ast_error>",
            )

        ensure_indexed()

        loop = asyncio.get_running_loop()
        project_path = str(Path.cwd())
        store = ASTStore(project_path)

        symbols = await loop.run_in_executor(
            None, store.get_symbols_by_name, name, type_filter
        )

        if not symbols:
            return ExecutorResult(
                display=f"No references for '{name}'",
                content=f'<symbol_references name="{_xml_attr(name)}" count="0" />',
            )

        e = escape
        parts = []
        for s in symbols:
            parts.append(
                f'  <symbol name="{_xml_attr(s["name"])}" '
                f'type="{s["type"]}" '
                f'kind="{s["kind"]}" '
                f'file="{_xml_attr(s["file_path"])}" '
                f'start_line="{s["start_line"]}" '
                f'start_column="{s["start_column"]}" '
                f'end_line="{s["end_line"]}" '
                f'end_column="{s["end_column"]}" />'
            )

        result_xml = (
            f'<symbol_references name="{_xml_attr(name)}" '
            f'type_filter="{type_filter}" count="{len(symbols)}">\n'
            + "\n".join(parts)
            + "\n</symbol_references>"
        )

        defs = sum(1 for s in symbols if s["type"] == "definition")
        refs = sum(1 for s in symbols if s["type"] == "reference")
        return ExecutorResult(
            display=f"Found {defs} definition(s), {refs} reference(s) for '{name}'",
            content=result_xml,
        )

    except Exception as e:
        logger.warning("find_symbol_references error: %s", e)
        return ExecutorResult(
            display=f"Error finding '{name}'",
            content=f'<ast_error tool="find_symbol_references">'
            f"{escape(str(e))}</ast_error>",
        )


async def execute_replace_symbol(
    file_path: str, name: str, new_text: str
) -> ExecutorResult:
    try:
        filepath = Path(file_path)
        if not filepath.exists():
            return ExecutorResult(
                display=f"File not found: {file_path}",
                content=_format_edit_result(
                    file_path,
                    success=False,
                    replacements=0,
                    added=0,
                    removed=0,
                    error="file_not_found",
                    message=f"File not found: {file_path}",
                ),
            )

        content = filepath.read_text(encoding="utf-8", errors="replace")
        content_bytes = content.encode("utf-8")
        lang_name = lang_for_extension(file_path)
        query_text = load_query_file(lang_name)
        tree = parse_file(file_path, content)
        captures = run_query(tree, lang_name, query_text, content)

        name_caps = captures.get("name.definition.function", [])
        method_caps = captures.get("name.definition.method", [])
        class_caps = captures.get("name.definition.class", [])

        target_caps = [r for r in name_caps + method_caps + class_caps if r.text == name]

        if not target_caps:
            return ExecutorResult(
                display=f"Symbol '{name}' not found in {file_path}",
                content=_format_edit_result(
                    file_path,
                    success=False,
                    replacements=0,
                    added=0,
                    removed=0,
                    error="symbol_not_found",
                    message=f"Symbol '{name}' not found in {file_path}",
                ),
            )

        replacements_list = []
        for r in target_caps:
            if r.node.parent is None:
                continue
            parent = r.node.parent
            if parent.type in (
                "function_definition",
                "function_declaration",
                "method_definition",
                "class_definition",
                "class_declaration",
            ):
                definition_node = parent
            else:
                grandparent = parent.parent
                if grandparent and grandparent.type in (
                    "function_definition",
                    "function_declaration",
                    "method_definition",
                    "class_definition",
                    "class_declaration",
                ):
                    definition_node = grandparent
                else:
                    continue

            start, end = _find_extended_range(content_bytes, definition_node, file_path)
            replacements_list.append((start, end))

        if not replacements_list:
            return ExecutorResult(
                display=f"Symbol '{name}' not found in {file_path}",
                content=_format_edit_result(
                    file_path,
                    success=False,
                    replacements=0,
                    added=0,
                    removed=0,
                    error="symbol_not_found",
                    message=f"Symbol '{name}' not found in {file_path}",
                ),
            )

        replacements_list.sort(key=lambda x: x[0], reverse=True)

        new_content_bytes = content_bytes
        for start, end in replacements_list:
            new_content_bytes = (
                new_content_bytes[:start]
                + new_text.encode("utf-8")
                + new_content_bytes[end:]
            )

        new_content = new_content_bytes.decode("utf-8", errors="replace")

        if new_content == content:
            return ExecutorResult(
                display=f"No changes for '{name}' in {file_path}",
                content=_format_edit_result(
                    file_path,
                    success=True,
                    replacements=0,
                    added=0,
                    removed=0,
                    message=f"No changes needed for '{name}' in {file_path}",
                ),
            )

        _atomic_write(file_path, new_content)

        diff_text = _generate_diff(content, new_content, file_path)
        added, removed = _count_diff_changes(diff_text)

        await _trigger_post_write_callbacks(file_path)

        return ExecutorResult(
            display=f"Replaced '{name}' in {file_path} (+{added} -{removed})",
            content=_format_edit_result(
                file_path,
                success=True,
                replacements=len(replacements_list),
                added=added,
                removed=removed,
                diff_text=diff_text,
            ),
        )

    except ValueError as e:
        return ExecutorResult(
            display=f"Unsupported file type: {file_path}",
            content=_format_edit_result(
                file_path,
                success=False,
                replacements=0,
                added=0,
                removed=0,
                error="unsupported_file",
                message=str(e),
            ),
        )
    except Exception as e:
        logger.warning("replace_symbol error: %s", e)
        return ExecutorResult(
            display=f"Error replacing '{name}'",
            content=_format_edit_result(
                file_path,
                success=False,
                replacements=0,
                added=0,
                removed=0,
                error="replace_error",
                message=f"Error replacing '{name}' in {file_path}: {e}",
            ),
        )


async def execute_rename_symbol(name: str, new_name: str) -> ExecutorResult:
    try:
        if not name or not name.strip():
            return ExecutorResult(
                display="Empty symbol name",
                content='<ast_error tool="rename_symbol">'
                "Symbol name is required.</ast_error>",
            )

        ensure_indexed()

        loop = asyncio.get_running_loop()
        project_path = str(Path.cwd())
        store = ASTStore(project_path)

        symbols = await loop.run_in_executor(
            None, store.get_symbols_by_name, name, "both"
        )

        if not symbols:
            return ExecutorResult(
                display=f"No references for '{name}'",
                content=f'<ast_error tool="rename_symbol">'
                f"No references found for '{escape(name)}'. "
                f"No files modified.</ast_error>",
            )

        by_file: dict[str, list[dict]] = {}
        for s in symbols:
            by_file.setdefault(s["file_path"], []).append(s)

        total_added = 0
        total_removed = 0
        edit_results = []

        for rel_path, file_symbols in by_file.items():
            abs_path = str(Path(project_path) / rel_path)
            if not Path(abs_path).exists():
                continue

            try:
                content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue

            lines = content.split("\n")
            sorted_syms = sorted(
                file_symbols,
                key=lambda s: (s["start_line"], s["start_column"]),
                reverse=True,
            )

            for s in sorted_syms:
                line_idx = s["start_line"]
                col = s["start_column"]
                if line_idx < len(lines):
                    line = lines[line_idx]
                    if line[col : col + len(name)] == name:
                        lines[line_idx] = line[:col] + new_name + line[col + len(name):]

            new_content = "\n".join(lines)

            if new_content == content:
                continue

            _atomic_write(abs_path, new_content)

            diff_text = _generate_diff(content, new_content, rel_path)
            added, removed = _count_diff_changes(diff_text)
            total_added += added
            total_removed += removed

            await _trigger_post_write_callbacks(rel_path)

            edit_results.append(
                f'<edit_result path="{_xml_attr(rel_path)}" success="true" '
                f'replacements="{len(file_symbols)}" replace_all="false" '
                f'added="{added}" removed="{removed}">\n'
                f'<diff format="unified"><![CDATA[{_cdata_text(diff_text)}]]></diff>\n'
                f"</edit_result>"
            )

        if not edit_results:
            return ExecutorResult(
                display=f"No changes for '{name}'",
                content=f'<ast_error tool="rename_symbol">'
                f"No changes made for '{escape(name)}'.</ast_error>",
            )

        result_xml = (
            f'<rename_result name="{_xml_attr(name)}" '
            f'new_name="{_xml_attr(new_name)}" '
            f'files="{len(edit_results)}" '
            f'total_added="{total_added}" total_removed="{total_removed}">\n'
            + "\n".join(edit_results)
            + "\n</rename_result>"
        )

        return ExecutorResult(
            display=f"Renamed '{name}' -> '{new_name}' in {len(edit_results)} file(s) (+{total_added} -{total_removed})",
            content=result_xml,
        )

    except Exception as e:
        logger.warning("rename_symbol error: %s", e)
        return ExecutorResult(
            display=f"Error renaming '{name}'",
            content=f'<ast_error tool="rename_symbol">'
            f"{escape(str(e))}</ast_error>",
        )
