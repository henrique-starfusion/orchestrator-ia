"""0.4.61 — decomposição em subtarefas: escopo disjunto ou não há paralelismo."""

from __future__ import annotations

from orchestrator_runtime.execution.fanout import (
    SubtaskSpec,
    decomposition_prompt,
    merge_overlapping,
    parse_subtasks,
)

TRES_DISJUNTAS = """
Claro! Segue o plano:
```json
{"subtasks":[
  {"id":"s1","title":"API","scope":["docs/api.md"],"instruction":"Documentar a API"},
  {"id":"s2","title":"Deploy","scope":["docs/deploy.md"],"instruction":"Documentar o deploy"},
  {"id":"s3","title":"Dados","scope":["docs/dados.md"],"instruction":"Documentar o modelo"}
]}
```
Pronto.
"""


def test_extrai_json_cercado_de_prosa() -> None:
    specs = parse_subtasks(TRES_DISJUNTAS)
    assert [s.id for s in specs] == ["s1", "s2", "s3"]
    assert specs[0].scope == ["docs/api.md"]


def test_respeita_teto() -> None:
    assert len(parse_subtasks(TRES_DISJUNTAS, max_subtasks=2)) == 2


def test_uma_subtarefa_significa_sequencial() -> None:
    """Tarefa indivisível é resposta legítima — e não vira fan-out."""
    texto = '{"subtasks":[{"id":"s1","scope":["app.py"],"instruction":"refatorar"}]}'
    assert parse_subtasks(texto) == []


def test_texto_sem_json_nao_paraleliza() -> None:
    assert parse_subtasks("não consegui dividir") == []
    assert parse_subtasks("") == []


def test_sem_instrucao_e_descartada() -> None:
    texto = (
        '{"subtasks":['
        '{"id":"s1","scope":["a.py"],"instruction":"faz A"},'
        '{"id":"s2","scope":["b.py"],"title":"só título"}]}'
    )
    # Sobra uma útil -> sem paralelismo.
    assert parse_subtasks(texto) == []


def test_escopos_sobrepostos_sao_fundidos() -> None:
    texto = (
        '{"subtasks":['
        '{"id":"s1","title":"A","scope":["app.py"],"instruction":"faz A"},'
        '{"id":"s2","title":"B","scope":["app.py"],"instruction":"faz B"},'
        '{"id":"s3","title":"C","scope":["outro.py"],"instruction":"faz C"}]}'
    )
    specs = parse_subtasks(texto)
    assert len(specs) == 2
    fundida = specs[0]
    assert fundida.title == "A; B"
    # Trabalho fundido, nunca descartado.
    assert "faz A" in fundida.instruction and "faz B" in fundida.instruction


def test_pasta_e_arquivo_dentro_dela_conflitam() -> None:
    specs = merge_overlapping(
        [
            SubtaskSpec("s1", "pasta", "faz tudo em docs", ["docs"]),
            SubtaskSpec("s2", "arquivo", "escreve api", ["docs/api.md"]),
        ]
    )
    assert len(specs) == 1


def test_escopo_vazio_conflita_com_tudo() -> None:
    """Quem não declara onde escreve não roda em paralelo às cegas."""
    specs = merge_overlapping(
        [
            SubtaskSpec("s1", "sem escopo", "mexe em algo", []),
            SubtaskSpec("s2", "api", "escreve api", ["docs/api.md"]),
        ]
    )
    assert len(specs) == 1


def test_normaliza_separador_e_prefixo() -> None:
    texto = (
        '{"subtasks":['
        '{"id":"s1","scope":["./docs\\\\api.md"],"instruction":"a"},'
        '{"id":"s2","scope":["docs/api.md"],"instruction":"b"}]}'
    )
    # Mesmo arquivo escrito de duas formas: tem que colidir.
    assert parse_subtasks(texto) == []


def test_prompt_tem_as_regras_duras() -> None:
    p = decomposition_prompt("documentar o projeto", max_subtasks=3)
    assert "documentar o projeto" in p
    assert "3" in p
    assert "scope" in p and "sobrepor" in p
