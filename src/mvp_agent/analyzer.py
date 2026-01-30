"""Python source code analyzer.

Uses Python's ast module to extract structure from source files.
Reference: refact-agent/engine/src/tools/tool_ast_definition.rs
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class FunctionInfo:
    """Information about a function or method."""

    name: str
    args: list[str]
    return_type: str | None = None
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None
    start_line: int = 0
    end_line: int = 0
    is_method: bool = False
    is_async: bool = False


@dataclass
class ClassInfo:
    """Information about a class."""

    name: str
    bases: list[str] = field(default_factory=list)
    methods: list[FunctionInfo] = field(default_factory=list)
    attributes: list[str] = field(default_factory=list)
    docstring: str | None = None
    start_line: int = 0
    end_line: int = 0


@dataclass
class ModuleInfo:
    """Information about a Python module."""

    path: str
    imports: list[str] = field(default_factory=list)
    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)
    global_vars: list[str] = field(default_factory=list)


class Analyzer:
    """Analyzes Python source code using AST.

    Extracts classes, functions, imports, and structure information
    for planning refactoring tasks.
    """

    def analyze_file(self, file_path: str | Path) -> ModuleInfo:
        """Analyze a Python source file.

        Args:
            file_path: Path to the Python file.

        Returns:
            ModuleInfo containing extracted structure.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        source = file_path.read_text(encoding="utf-8")
        return self.analyze_source(source, str(file_path))

    def analyze_source(self, source: str, path: str = "<string>") -> ModuleInfo:
        """Analyze Python source code string.

        Args:
            source: Python source code.
            path: Optional path for reference.

        Returns:
            ModuleInfo containing extracted structure.
        """
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.error("Syntax error in %s: %s", path, e)
            return ModuleInfo(path=path)

        module = ModuleInfo(path=path)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                for alias in node.names:
                    module.imports.append(f"{module_name}.{alias.name}")

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                module.classes.append(self._extract_class(node))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                module.functions.append(self._extract_function(node))
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        module.global_vars.append(target.id)

        return module

    def _extract_class(self, node: ast.ClassDef) -> ClassInfo:
        """Extract class information from AST node.

        Args:
            node: AST ClassDef node.

        Returns:
            ClassInfo with extracted data.
        """
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{self._get_attribute_name(base)}")

        methods = []
        attributes = []

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_info = self._extract_function(item, is_method=True)
                methods.append(func_info)
            elif isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attributes.append(target.id)

        return ClassInfo(
            name=node.name,
            bases=bases,
            methods=methods,
            attributes=attributes,
            docstring=ast.get_docstring(node),
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
        )

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_method: bool = False,
    ) -> FunctionInfo:
        """Extract function information from AST node.

        Args:
            node: AST FunctionDef or AsyncFunctionDef node.
            is_method: Whether this is a class method.

        Returns:
            FunctionInfo with extracted data.
        """
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._get_annotation_str(arg.annotation)}"
            args.append(arg_str)

        return_type = None
        if node.returns:
            return_type = self._get_annotation_str(node.returns)

        decorators = []
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                decorators.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                decorators.append(self._get_attribute_name(dec))

        return FunctionInfo(
            name=node.name,
            args=args,
            return_type=return_type,
            decorators=decorators,
            docstring=ast.get_docstring(node),
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            is_method=is_method,
            is_async=isinstance(node, ast.AsyncFunctionDef),
        )

    def _get_annotation_str(self, node: ast.expr) -> str:
        """Get string representation of type annotation.

        Args:
            node: AST expression node.

        Returns:
            String representation of the annotation.
        """
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return str(node.value)
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_name(node)
        elif isinstance(node, ast.Subscript):
            value = self._get_annotation_str(node.value)
            slice_str = self._get_annotation_str(node.slice)
            return f"{value}[{slice_str}]"
        return ""

    def _get_attribute_name(self, node: ast.Attribute) -> str:
        """Get full attribute name.

        Args:
            node: AST Attribute node.

        Returns:
            Full attribute name as string.
        """
        parts = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def to_summary(self, module: ModuleInfo) -> str:
        """Generate a text summary of the module.

        Args:
            module: ModuleInfo to summarize.

        Returns:
            Human-readable summary string.
        """
        lines = [f"# Module: {module.path}", ""]

        if module.imports:
            lines.append("## Imports")
            for imp in module.imports:
                lines.append(f"- {imp}")
            lines.append("")

        if module.classes:
            lines.append("## Classes")
            for cls in module.classes:
                bases_str = f"({', '.join(cls.bases)})" if cls.bases else ""
                lines.append(f"### {cls.name}{bases_str}")
                if cls.docstring:
                    lines.append(f"  {cls.docstring.split(chr(10))[0]}")
                for method in cls.methods:
                    args_str = ", ".join(method.args)
                    ret_str = f" -> {method.return_type}" if method.return_type else ""
                    lines.append(f"  - {method.name}({args_str}){ret_str}")
            lines.append("")

        if module.functions:
            lines.append("## Functions")
            for func in module.functions:
                args_str = ", ".join(func.args)
                ret_str = f" -> {func.return_type}" if func.return_type else ""
                lines.append(f"- {func.name}({args_str}){ret_str}")

        return "\n".join(lines)
