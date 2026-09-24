"""Structural guards for conventions that previously depended on prose."""

import ast
import pathlib

ROOT = pathlib.Path(__file__).parents[2]


def _python_files(*parts: str) -> list[pathlib.Path]:
    root = ROOT.joinpath(*parts)
    return sorted(root.rglob("*.py"))


def _imports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(f"{node.module or ''}.{alias.name}".lstrip("."))
    return names


def test_api_routes_do_not_import_or_raise_httpexception():
    for path in _python_files("app", "api"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _imports(tree)
        assert not any(
            name.endswith(".HTTPException") for name in imports
        ), f"direct HTTPException import in {path}"
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "HTTPException"
            ):
                raise AssertionError(f"direct HTTPException raise in {path}")


def test_models_and_migrations_do_not_use_sqlalchemy_enum_columns():
    for path in (*_python_files("app", "models"), *_python_files("alembic", "versions")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = _imports(tree)
        assert not any(
            name in {"sqlalchemy.Enum", "sa.Enum"} for name in imports
        ), f"SQLAlchemy Enum column in {path}"


def test_scoring_does_not_use_eval():
    path = ROOT / "app" / "services" / "scoring.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "eval", "scoring.py must not use eval"
