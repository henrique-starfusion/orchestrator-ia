"""Decomposição de uma task em subtarefas paralelas com escopo disjunto.

O paralelismo só paga se as subtarefas não brigarem pelos mesmos arquivos:
patch que colide é rejeitado na fusão e vira retrabalho. Por isso a
decomposição é validada aqui, ANTES de gastar N agentes — escopo declarado que
se sobrepõe é fundido numa subtarefa só, e decomposição degenerada (0 ou 1
item) devolve lista vazia para o runtime seguir sequencial.

Nada aqui roda agente: recebe o texto do decompositor e devolve specs. Isso
mantém a regra de sobreposição testável sem processo filho.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class SubtaskSpec:
    id: str
    title: str
    instruction: str
    scope: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "instruction": self.instruction,
            "scope": list(self.scope),
        }


def _json_objects(text: str) -> list[dict]:
    """Todo objeto JSON embutido no texto (agente cerca com prosa/```json)."""
    decoder = json.JSONDecoder()
    out: list[dict] = []
    idx = 0
    while True:
        pos = text.find("{", idx)
        if pos < 0:
            return out
        try:
            obj, end = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            idx = pos + 1
            continue
        if isinstance(obj, dict):
            out.append(obj)
        idx = end


def _norm_scope(raw) -> list[str]:
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    for item in raw:
        path = str(item or "").strip().replace("\\", "/").lstrip("./")
        if path:
            out.append(path)
    return sorted(dict.fromkeys(out))


def _conflicts(a: list[str], b: list[str]) -> bool:
    """Escopos colidem se compartilham arquivo ou se um contém o outro.

    Prefixo conta: "docs/" e "docs/api.md" na mesma rodada produzem dois
    patches sobre o mesmo arquivo. Escopo VAZIO conflita com tudo — subtarefa
    que não declara onde escreve não pode rodar em paralelo às cegas.
    """
    if not a or not b:
        return True
    for x in a:
        for y in b:
            if x == y or x.startswith(f"{y}/") or y.startswith(f"{x}/"):
                return True
    return False


def parse_subtasks(text: str, *, max_subtasks: int = 4) -> list[SubtaskSpec]:
    """Extrai subtarefas do output do decompositor.

    Devolve [] quando a decomposição não justifica paralelismo (menos de duas
    subtarefas úteis) — o chamador segue no caminho sequencial de sempre.
    """
    raw_items: list[dict] = []
    for obj in _json_objects(text or ""):
        items = obj.get("subtasks")
        if isinstance(items, list) and items:
            raw_items = [i for i in items if isinstance(i, dict)]
            break
    if not raw_items:
        return []

    specs: list[SubtaskSpec] = []
    for idx, item in enumerate(raw_items, start=1):
        instruction = str(
            item.get("instruction") or item.get("description") or ""
        ).strip()
        if not instruction:
            continue
        title = str(item.get("title") or instruction[:60]).strip()
        sid = str(item.get("id") or f"s{idx}").strip() or f"s{idx}"
        specs.append(
            SubtaskSpec(
                id=sid,
                title=title,
                instruction=instruction,
                scope=_norm_scope(item.get("scope") or item.get("files")),
            )
        )

    merged = merge_overlapping(specs)
    if len(merged) < 2:
        return []
    return merged[:max_subtasks]


def merge_overlapping(specs: list[SubtaskSpec]) -> list[SubtaskSpec]:
    """Funde subtarefas de escopo sobreposto — elas não podem rodar juntas.

    Fundir em vez de descartar: o trabalho declarado continua sendo feito, só
    que por um agente só, na mesma ordem. Descartar perderia requisito.
    """
    out: list[SubtaskSpec] = []
    for spec in specs:
        target = next((o for o in out if _conflicts(o.scope, spec.scope)), None)
        if target is None:
            out.append(spec)
            continue
        target.title = f"{target.title}; {spec.title}"
        target.instruction = f"{target.instruction}\n\n{spec.instruction}"
        target.scope = sorted(dict.fromkeys([*target.scope, *spec.scope]))
    return out


def decomposition_prompt(prompt: str, *, max_subtasks: int) -> str:
    return (
        "Divida a tarefa abaixo em subtarefas INDEPENDENTES que possam ser "
        f"executadas em paralelo por agentes diferentes (no máximo {max_subtasks}).\n\n"
        f"TAREFA:\n{prompt}\n\n"
        "REGRAS DURAS:\n"
        "- Cada subtarefa declara em `scope` os arquivos/pastas que ela vai "
        "ESCREVER. Escopos NÃO podem se sobrepor entre subtarefas — duas "
        "subtarefas que tocam o mesmo arquivo serão fundidas numa só e o "
        "paralelismo se perde.\n"
        "- `instruction` precisa se bastar sozinha: o agente que a executa NÃO "
        "vê as outras subtarefas nem conversa com elas.\n"
        "- Se a tarefa não se divide de verdade (um arquivo só, mudanças "
        "encadeadas, refactor que atravessa tudo), devolva UMA subtarefa — é "
        "resposta legítima, não falha.\n"
        "- Não invente trabalho fora do pedido para encher o paralelismo.\n\n"
        "Responda APENAS JSON:\n"
        '{"subtasks":[{"id":"s1","title":"...","scope":["caminho/a.py"],'
        '"instruction":"..."}]}'
    )
