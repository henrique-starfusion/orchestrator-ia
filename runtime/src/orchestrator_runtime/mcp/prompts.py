"""Prompts MCP reutilizáveis (não substituem tools)."""

PROMPTS: dict[str, dict] = {
    "orchestrate_complex_task": {
        "description": "Orientar o front controller a usar orchestrator_run",
        "template": (
            "A tarefa é complexa. Chame orchestrator_run com objective claro, "
            "routing=automatic, wait=false. Em seguida faça polling com "
            "orchestrator_status e finalize com orchestrator_result. "
            "Não simule agentes CLI."
        ),
    },
    "delegate_planning": {
        "description": "Delegar planejamento pontual",
        "template": (
            "Use orchestrator_delegate com agent=claude role=planner "
            "read_only=true e objective do usuário."
        ),
    },
    "delegate_code_review": {
        "description": "Delegar code review",
        "template": (
            "Use orchestrator_delegate com role adequado (validator/reviewer) "
            "e read_only=true. Não edite arquivos nesta etapa."
        ),
    },
    "validate_implementation": {
        "description": "Validar implementação via runtime",
        "template": (
            "Consulte orchestrator_status e orchestrator_result. "
            "Exija testes, score e documentation_review antes de declarar sucesso."
        ),
    },
    "investigate_failure": {
        "description": "Investigar falha de tarefa",
        "template": (
            "Use orchestrator_events e orchestrator_result. "
            "Identifique blocking_issues VAL-* e decida resume/cancel."
        ),
    },
}


def list_prompts() -> list[dict]:
    return [
        {"name": name, "description": meta["description"], "template": meta["template"]}
        for name, meta in PROMPTS.items()
    ]


def get_prompt(name: str) -> dict:
    if name not in PROMPTS:
        raise KeyError(name)
    meta = PROMPTS[name]
    return {"name": name, **meta}
