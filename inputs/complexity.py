"""Static complexity metrics extracted from source files via AST.

Runs before the LLM stages so the pattern advisor has concrete numbers.
Only Python files are fully analysed (AST-based); other languages get
line-count estimates only.
"""
import ast
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FunctionMetrics:
    name: str
    file: str
    start_line: int
    end_line: int
    cyclomatic_complexity: int   # McCabe — 1 + branching nodes
    lines: int
    nesting_depth: int           # max nesting level inside the function


@dataclass
class ClassMetrics:
    name: str
    file: str
    start_line: int
    end_line: int
    lines: int
    method_count: int
    attribute_count: int         # instance attributes assigned in __init__
    imported_modules: list[str]  # modules referenced inside class methods


@dataclass
class FileMetrics:
    path: str
    language: str
    total_lines: int
    functions: list[FunctionMetrics] = field(default_factory=list)
    classes: list[ClassMetrics] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)   # all top-level imports


@dataclass
class ComplexityReport:
    files: list[FileMetrics] = field(default_factory=list)
    # coupling: module -> list[modules it imports]
    coupling: dict[str, list[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# McCabe cyclomatic complexity counter
# ---------------------------------------------------------------------------

_BRANCH_NODES = (
    ast.If, ast.For, ast.While, ast.ExceptHandler,
    ast.With, ast.Assert, ast.comprehension,
    # Boolean operators each add one path
)


class _CyclomaticVisitor(ast.NodeVisitor):
    def __init__(self):
        self.complexity = 1  # base = 1

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_With(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_Assert(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        # `and` / `or` with N values adds N-1 paths
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_comprehension(self, node):
        # each `if` inside a comprehension counts
        self.complexity += len(node.ifs)
        self.generic_visit(node)


def _cyclomatic(func_node: ast.FunctionDef) -> int:
    v = _CyclomaticVisitor()
    v.visit(func_node)
    return v.complexity


# ---------------------------------------------------------------------------
# Nesting depth counter
# ---------------------------------------------------------------------------

_NESTING_NODES = (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.ExceptHandler)


class _NestingVisitor(ast.NodeVisitor):
    def __init__(self):
        self._depth = 0
        self.max_depth = 0

    def _enter(self, node):
        self._depth += 1
        self.max_depth = max(self.max_depth, self._depth)
        self.generic_visit(node)
        self._depth -= 1

    visit_If = _enter
    visit_For = _enter
    visit_While = _enter
    visit_With = _enter
    visit_Try = _enter
    visit_ExceptHandler = _enter


def _max_nesting(func_node: ast.FunctionDef) -> int:
    v = _NestingVisitor()
    v.visit(func_node)
    return v.max_depth


# ---------------------------------------------------------------------------
# Module import collector
# ---------------------------------------------------------------------------

def _collect_imports(tree: ast.Module) -> list[str]:
    mods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.append(node.module.split(".")[0])
    return list(dict.fromkeys(mods))   # deduplicated, order preserved


def _imports_inside_class(class_node: ast.ClassDef) -> list[str]:
    mods = []
    for node in ast.walk(class_node):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.append(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.append(node.module.split(".")[0])
    return list(dict.fromkeys(mods))


# ---------------------------------------------------------------------------
# Python AST analyser
# ---------------------------------------------------------------------------

def _analyse_python(path: str, content: str) -> FileMetrics:
    lines = content.splitlines()
    fm = FileMetrics(path=path, language="python", total_lines=len(lines))

    try:
        tree = ast.parse(content, filename=path)
    except SyntaxError:
        return fm

    fm.imports = _collect_imports(tree)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Only top-level functions and class methods (one level deep)
            end = getattr(node, "end_lineno", node.lineno)
            fm.functions.append(FunctionMetrics(
                name=node.name,
                file=path,
                start_line=node.lineno,
                end_line=end,
                cyclomatic_complexity=_cyclomatic(node),
                lines=end - node.lineno + 1,
                nesting_depth=_max_nesting(node),
            ))

        elif isinstance(node, ast.ClassDef):
            end = getattr(node, "end_lineno", node.lineno)
            # Count instance attributes assigned in __init__
            attr_count = 0
            for item in ast.walk(node):
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    for stmt in ast.walk(item):
                        if (isinstance(stmt, ast.Assign) and
                                any(isinstance(t, ast.Attribute) and
                                    isinstance(t.value, ast.Name) and t.value.id == "self"
                                    for t in stmt.targets)):
                            attr_count += 1
                        elif isinstance(stmt, ast.AnnAssign):
                            if (isinstance(stmt.target, ast.Attribute) and
                                    isinstance(stmt.target.value, ast.Name) and
                                    stmt.target.value.id == "self"):
                                attr_count += 1

            method_count = sum(
                1 for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            fm.classes.append(ClassMetrics(
                name=node.name,
                file=path,
                start_line=node.lineno,
                end_line=end,
                lines=end - node.lineno + 1,
                method_count=method_count,
                attribute_count=attr_count,
                imported_modules=_imports_inside_class(node),
            ))

    return fm


# ---------------------------------------------------------------------------
# Line-count fallback for non-Python languages
# ---------------------------------------------------------------------------

def _analyse_generic(path: str, content: str, language: str) -> FileMetrics:
    lines = content.splitlines()
    return FileMetrics(path=path, language=language, total_lines=len(lines))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse_complexity(inputs: dict) -> ComplexityReport:
    """Compute complexity metrics for all files in the loader inputs dict.

    Returns a ComplexityReport with per-file metrics and module coupling map.
    """
    report = ComplexityReport()

    for f in inputs.get("files", []):
        path     = f.get("path", "")
        content  = f.get("content", "")
        language = f.get("language", "python")

        if language == "python":
            fm = _analyse_python(path, content)
        else:
            fm = _analyse_generic(path, content, language)

        report.files.append(fm)

        if fm.imports:
            report.coupling[path] = fm.imports

    return report


def complexity_summary(report: ComplexityReport, thresholds: dict | None = None) -> str:
    """Render a concise human-readable summary for injection into LLM prompts.

    thresholds: dict with keys max_cyclomatic, max_method_lines,
                max_class_lines, max_nesting_depth.
    """
    t = thresholds or {}
    max_cc   = t.get("max_cyclomatic_complexity", 10)
    max_ml   = t.get("max_method_lines", 50)
    max_cl   = t.get("max_class_lines", 300)
    max_nd   = t.get("max_nesting_depth", 4)

    lines_out = ["## Static Complexity Metrics\n"]

    for fm in report.files:
        lines_out.append(f"### {fm.path}  ({fm.total_lines} lines, {fm.language})")

        for fn in fm.functions:
            flags = []
            if fn.cyclomatic_complexity > max_cc:
                flags.append(f"cyclomatic={fn.cyclomatic_complexity} > threshold {max_cc}")
            if fn.lines > max_ml:
                flags.append(f"lines={fn.lines} > threshold {max_ml}")
            if fn.nesting_depth > max_nd:
                flags.append(f"nesting={fn.nesting_depth} > threshold {max_nd}")
            flag_str = f" ⚠ [{', '.join(flags)}]" if flags else ""
            lines_out.append(
                f"  fn {fn.name}:{fn.start_line}  "
                f"cc={fn.cyclomatic_complexity}  "
                f"lines={fn.lines}  "
                f"nesting={fn.nesting_depth}"
                f"{flag_str}"
            )

        for cls in fm.classes:
            flags = []
            if cls.lines > max_cl:
                flags.append(f"lines={cls.lines} > threshold {max_cl}")
            if cls.method_count > 20:
                flags.append(f"methods={cls.method_count}")
            flag_str = f" ⚠ [{', '.join(flags)}]" if flags else ""
            lines_out.append(
                f"  class {cls.name}:{cls.start_line}  "
                f"lines={cls.lines}  "
                f"methods={cls.method_count}  "
                f"attrs={cls.attribute_count}"
                f"{flag_str}"
            )

        if fm.imports:
            lines_out.append(f"  imports: {', '.join(fm.imports)}")

    if report.coupling:
        lines_out.append("\n## Module Coupling")
        for mod, deps in report.coupling.items():
            lines_out.append(f"  {mod} → {', '.join(deps)}")

    return "\n".join(lines_out)
