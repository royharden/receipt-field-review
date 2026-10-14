"""Dependency-free architecture and publication checks used by bootstrap tests."""

import ast
import importlib.util
import re
from pathlib import PurePosixPath, PureWindowsPath


def forbidden_shared_imports(module: str, source: str) -> list[str]:
    """Reject app imports or undeclared shared-module edges from a reusable module."""
    if not module.startswith("rfr.shared."):
        return []
    owner = module.split(".")[2]
    allowed = {f"rfr.shared.{owner}"}
    if owner == "fieldextract":
        allowed.add("rfr.shared.docio")
    dependencies = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            dependencies.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = importlib.util.resolve_name(
                    "." * node.level + base, module.rsplit(".", 1)[0]
                )
            dependencies.extend(f"{base}.{alias.name}" for alias in node.names)
    return sorted(
        {
            name
            for name in dependencies
            if name == "rfr" or name.startswith("rfr.")
            if not any(name == root or name.startswith(root + ".") for root in allowed)
        }
    )


SECRET_PATTERNS = (
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
PRIVATE_COMPONENTS = {
    "data",
    ".creds",
    ".thinking",
    ".chatexports",
    ".agent-registry",
    ".agent-work",
}


def publication_violations(path: str, content: str = "") -> list[str]:
    """Check a candidate public path and text; never opens private credential files."""
    normalized = PurePosixPath(path.replace("\\", "/"))
    issues = []
    if normalized.is_absolute() or PureWindowsPath(path).is_absolute() or ".." in normalized.parts:
        issues.append("nonportable_path")
    if PRIVATE_COMPONENTS.intersection(normalized.parts):
        issues.append("private_material")
    if normalized.name == ".env" or (
        normalized.name.startswith(".env.") and normalized.name != ".env.example"
    ):
        issues.append("environment_secret_file")
    if any(pattern.search(content) for pattern in SECRET_PATTERNS):
        issues.append("credential_pattern")
    return issues
