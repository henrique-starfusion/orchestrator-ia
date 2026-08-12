"""0.4.85 - fronteiras internas verificadas por grafo de imports AST (Issue #15)."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


PACKAGE_NAME = "orchestrator_runtime"
PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / PACKAGE_NAME

BOUNDARY_RULES = {
    "engine.core": {
        "members": ("tasks", "planning", "routing", "execution"),
        "importers": {"engine.core", "engine.server", "engine.cli"},
        "rule": (
            "engine.core pode ser importado somente dentro de engine.core "
            "ou por engine.server e engine.cli"
        ),
    },
    "engine.agents": {
        "members": ("agents",),
        "importers": {"engine.agents", "engine.core"},
        "rule": (
            "engine.agents pode ser importado somente dentro de engine.agents "
            "ou por engine.core"
        ),
    },
    "engine.memory": {
        "members": ("memory",),
        "importers": {"engine.memory", "engine.core"},
        "rule": (
            "engine.memory pode ser importado somente dentro de engine.memory "
            "ou por engine.core"
        ),
    },
    "engine.persistence": {
        "members": ("tasks.repository", "memory.database"),
        "importers": {"engine.persistence", "engine.core"},
        "rule": (
            "engine.persistence pode ser importado somente dentro de "
            "engine.persistence ou por engine.core"
        ),
    },
    "engine.server": {
        "members": ("server",),
        "importers": {"engine.server"},
        "rule": "nenhuma outra boundary interna pode importar engine.server",
    },
    "engine.cli": {
        "members": ("cli",),
        "importers": {"engine.cli"},
        "rule": "nenhuma outra boundary interna pode importar engine.cli",
    },
    "engine.mcp": {
        "members": ("mcp",),
        "importers": {"engine.mcp"},
        "rule": "nenhuma outra boundary interna pode importar engine.mcp",
    },
}

# Violações legadas aceitas temporariamente devem ser exatas e justificadas.
# O teste também falha quando uma exceção deixa de corresponder a uma violação.
EXISTING_BOUNDARY_EXCEPTIONS: dict[tuple[str, str], str] = {
    (
        "orchestrator_runtime.__main__",
        "orchestrator_runtime.cli",
    ): "O entry point de python -m encaminha a execução para o app Typer legado.",
    (
        "orchestrator_runtime.cli",
        "orchestrator_runtime.mcp.tools",
    ): "A CLI legada expõe comandos task usando a fachada MCP existente.",
    (
        "orchestrator_runtime.cli",
        "orchestrator_runtime.mcp.server",
    ): "A CLI legada ainda inicia os transportes MCP stdio e HTTP.",
    (
        "orchestrator_runtime.cli",
        "orchestrator_runtime.mcp.cursor_config",
    ): "A configuração Cursor ainda reside no pacote MCP legado.",
    (
        "orchestrator_runtime.config",
        "orchestrator_runtime.execution.timeouts",
    ): "RuntimeLimits ainda deriva orçamento das políticas de timeout do core.",
    (
        "orchestrator_runtime.manager_model.base",
        "orchestrator_runtime.planning.analyzer",
    ): "O contrato ManagerModel legado usa tipos e builders atuais de planning.",
    (
        "orchestrator_runtime.manager_model.base",
        "orchestrator_runtime.routing.manager",
    ): "O contrato ManagerModel legado referencia o roteador atual.",
    (
        "orchestrator_runtime.manager_model.base",
        "orchestrator_runtime.tasks.models",
    ): "O contrato ManagerModel legado usa os modelos atuais de task e plano.",
    (
        "orchestrator_runtime.mcp.tools",
        "orchestrator_runtime.agents.base",
    ): "A fachada MCP legada constrói AgentRequest diretamente.",
    (
        "orchestrator_runtime.mcp.tools",
        "orchestrator_runtime.agents.process",
    ): "A fachada MCP legada aplica o guard de agente filho do executor.",
    (
        "orchestrator_runtime.mcp.tools",
        "orchestrator_runtime.tasks.models",
    ): "A fachada MCP legada serializa TaskRecord diretamente.",
    (
        "orchestrator_runtime.mcp.tools",
        "orchestrator_runtime.tasks.service",
    ): "A fachada MCP legada instancia TaskService diretamente.",
    (
        "orchestrator_runtime.mcp.tools",
        "orchestrator_runtime.tasks.state_machine",
    ): "A fachada MCP legada expõe estado e retomada de tasks.",
    (
        "orchestrator_runtime.memory.retrieval",
        "orchestrator_runtime.tasks.repository",
    ): "MemoryRetrieval ainda recebe TaskRepository como dependência concreta.",
    (
        "orchestrator_runtime.tasks.repository",
        "orchestrator_runtime.tasks.models",
    ): "O mapper persistente atual materializa os modelos de domínio de task.",
    (
        "orchestrator_runtime.tasks.repository",
        "orchestrator_runtime.tasks.state_machine",
    ): "A transição persistente atual valida a máquina de estados de task.",
    (
        "orchestrator_runtime.testing.discovery",
        "orchestrator_runtime.agents.process",
    ): "O discovery legado reutiliza CliExecutor e descoberta de executáveis.",
    (
        "orchestrator_runtime.validation.deterministic",
        "orchestrator_runtime.tasks.models",
    ): "O validator legado avalia TaskRecord e AcceptanceCriterion diretamente.",
}


@dataclass(frozen=True)
class ImportEdge:
    source: str
    target: str
    path: Path
    line: int


def _module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT)
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join((PACKAGE_NAME, *parts))


def _internal_modules() -> dict[str, Path]:
    return {_module_name(path): path for path in PACKAGE_ROOT.rglob("*.py")}


def _relative_base(source: str, source_path: Path, level: int) -> list[str]:
    parts = source.split(".")
    package = parts if source_path.name == "__init__.py" else parts[:-1]
    keep = len(package) - (level - 1)
    return package[:keep]


def _import_from_targets(
    node: ast.ImportFrom,
    source: str,
    source_path: Path,
    known_modules: set[str],
) -> set[str]:
    if node.level:
        base_parts = _relative_base(source, source_path, node.level)
        if node.module:
            base_parts.extend(node.module.split("."))
        base = ".".join(base_parts)
    else:
        base = node.module or ""

    if not (base == PACKAGE_NAME or base.startswith(f"{PACKAGE_NAME}.")):
        return set()

    targets: set[str] = set()
    for alias in node.names:
        candidate = f"{base}.{alias.name}" if alias.name != "*" else base
        targets.add(candidate if candidate in known_modules else base)
    return targets


def _internal_import_graph() -> list[ImportEdge]:
    modules = _internal_modules()
    known_modules = set(modules)
    edges: list[ImportEdge] = []

    for source, path in modules.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets: set[str] = set()
            if isinstance(node, ast.Import):
                targets = {
                    alias.name
                    for alias in node.names
                    if alias.name == PACKAGE_NAME
                    or alias.name.startswith(f"{PACKAGE_NAME}.")
                }
            elif isinstance(node, ast.ImportFrom):
                targets = _import_from_targets(
                    node, source, path, known_modules
                )
            for target in targets:
                edges.append(ImportEdge(source, target, path, node.lineno))

    return sorted(edges, key=lambda edge: (str(edge.path), edge.line, edge.target))


def _boundary_for(module: str) -> str | None:
    relative = module.removeprefix(f"{PACKAGE_NAME}.")

    # Persistência é subconjunto de tasks/ e memory/; deve ganhar precedência.
    for member in BOUNDARY_RULES["engine.persistence"]["members"]:
        if relative == member or relative.startswith(f"{member}."):
            return "engine.persistence"

    for boundary, declaration in BOUNDARY_RULES.items():
        if boundary == "engine.persistence":
            continue
        for member in declaration["members"]:
            if relative == member or relative.startswith(f"{member}."):
                return boundary
    return None


def test_internal_imports_respect_declared_engine_boundaries() -> None:
    violations: list[str] = []
    matched_exceptions: set[tuple[str, str]] = set()

    for (source, target), reason in EXISTING_BOUNDARY_EXCEPTIONS.items():
        if not reason.strip():
            violations.append(
                f"exceção sem motivo: {source} -> {target}; "
                "documente a dívida em EXISTING_BOUNDARY_EXCEPTIONS"
            )

    for edge in _internal_import_graph():
        target_boundary = _boundary_for(edge.target)
        if target_boundary is None:
            continue
        source_boundary = _boundary_for(edge.source)
        allowed = BOUNDARY_RULES[target_boundary]["importers"]
        if source_boundary in allowed:
            continue

        exception_key = (edge.source, edge.target)
        if exception_key in EXISTING_BOUNDARY_EXCEPTIONS:
            matched_exceptions.add(exception_key)
            continue

        relative_path = edge.path.relative_to(PACKAGE_ROOT.parent.parent)
        violations.append(
            f"{relative_path}:{edge.line}: "
            f"{source_boundary or 'módulo interno não classificado'} -> "
            f"{target_boundary}; regra violada: "
            f"{BOUNDARY_RULES[target_boundary]['rule']} "
            f"({edge.source} importa {edge.target})"
        )

    unused_exceptions = set(EXISTING_BOUNDARY_EXCEPTIONS) - matched_exceptions
    for source, target in sorted(unused_exceptions):
        violations.append(
            "exceção obsoleta: "
            f"{source} -> {target}; remova-a de EXISTING_BOUNDARY_EXCEPTIONS"
        )

    assert not violations, "Violações de boundary:\n" + "\n".join(violations)
