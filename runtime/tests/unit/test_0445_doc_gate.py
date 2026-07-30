"""0.4.45 — gate documental + juiz (bug-066/067).

bug-066: a task c003522e25e2 (printbee) foi APROVADA com score 1.0 pelo
    validador e morreu em CONSOLIDATING ("validação documental não passou")
    por causa de um link legítimo que a própria task escreveu no README da
    feature: `/openapi/diagrams/<arquivo>.svg` — caminho de URL do dev
    server (dir public do frontend) com placeholder. O link checker tratava
    rota de servidor como path de filesystem, resolvia fora do projeto e
    falhava. Anchors de seção (file.md#ancora) morriam pelo mesmo motivo.
bug-067: o juiz LLM roda `git status` com as próprias ferramentas e via os
    arquivos de INFRA do orquestrador (update/propagação/adapters: .cursor,
    .orchestrator, .wolf, AGENTS.md...) como "alteração fora de escopo" —
    reprovou a iter 1 da mesma task (VAL-002) mesmo com changed_files do
    executor limpos. O prompt do validador agora lista a infra a ignorar.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator_runtime.config import load_config
from orchestrator_runtime.documentation.detector import DocumentationValidator
from orchestrator_runtime.tasks.service import TaskService


def _md(project: Path, name: str, body: str) -> str:
    (project / name).write_text(body, encoding="utf-8")
    return name


def test_link_site_absolute_com_placeholder_nao_reprova(tmp_path: Path) -> None:
    rel = _md(
        tmp_path,
        "README.md",
        "# Docs\n\nOs diagramas ficam em `/openapi/diagrams/<arquivo>.svg`.\n",
    )
    assert DocumentationValidator().validate(tmp_path, [rel]) == "passed"


def test_link_com_anchor_para_arquivo_existente_nao_reprova(tmp_path: Path) -> None:
    _md(tmp_path, "guia.md", "# Guia\n")
    rel = _md(tmp_path, "README.md", "Veja [o guia](guia.md#secao-final).\n")
    assert DocumentationValidator().validate(tmp_path, [rel]) == "passed"


def test_link_com_query_para_arquivo_existente_nao_reprova(tmp_path: Path) -> None:
    _md(tmp_path, "guia.md", "# Guia\n")
    rel = _md(tmp_path, "README.md", "Veja [o guia](guia.md?raw=true).\n")
    assert DocumentationValidator().validate(tmp_path, [rel]) == "passed"


def test_link_url_encoded_para_arquivo_existente_nao_reprova(tmp_path: Path) -> None:
    _md(tmp_path, "meu guia.md", "# Guia\n")
    rel = _md(tmp_path, "README.md", "Veja [o guia](meu%20guia.md).\n")
    assert DocumentationValidator().validate(tmp_path, [rel]) == "passed"


def test_link_relativo_quebrado_reprova(tmp_path: Path) -> None:
    rel = _md(tmp_path, "README.md", "Veja [o guia](nao-existe.md).\n")
    assert DocumentationValidator().validate(tmp_path, [rel]) == "failed"


def test_link_escapando_o_projeto_reprova(tmp_path: Path) -> None:
    rel = _md(tmp_path, "README.md", "Veja [fora](../../fora.md).\n")
    assert DocumentationValidator().validate(tmp_path, [rel]) == "failed"


def test_arquivo_revisado_inexistente_reprova(tmp_path: Path) -> None:
    assert DocumentationValidator().validate(tmp_path, ["FANTASMA.md"]) == "failed"


# ------------------------------------------------------------------ bug-067

def test_prompt_do_juiz_lista_infra_do_orquestrador(project) -> None:
    config = load_config(project, fake_agents=True)
    service = TaskService(config, verbose=False)
    task = service.create_task("ajuste qualquer 0445")
    prompt = service._build_validator_prompt(
        task,
        {"status": "approved", "score": 1.0, "blocking_issues": []},
        [],
        ["src/x.py"],
    )
    for marker in (".orchestrator/", ".wolf/", ".cursor/", "AGENTS.md"):
        assert marker in prompt, marker
    assert "NUNCA é escopo da task" in prompt
