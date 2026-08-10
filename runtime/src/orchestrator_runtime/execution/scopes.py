"""Escopo de arquivos de uma task: o que decide se duas podem rodar juntas.

0.4.74 — até a 0.4.73 o projeto era serializado por inteiro: uma task ativa por
projeto, e a segunda esperava a primeira terminar (25-40 min). O que de fato
precisa ser exclusivo não é o projeto, é o CÓDIGO — duas tasks em pastas
diferentes nunca se atrapalham.

Como o trabalho todo acontece na árvore local (sem worktree), a garantia é de
ADMISSÃO: o runtime não deixa duas tasks ativas com escopo sobreposto. Não é
impossibilidade — um agente que ignore o escopo declarado escreve onde quiser, e
isso é DETECTADO depois (`outside_scope`), não impedido na hora. O bug-077
registrou seis quase-arrastões num dia com agentes lado a lado; a disciplina de
`_git_hygiene_block()` continua sendo parte da garantia, não um detalhe.

Regra que faz o resto funcionar: **escopo vazio significa DESCONHECIDO, e
desconhecido sobrepõe tudo.** Sem isso, uma task sem escopo declarado passaria
por "disjunta de todas" e rodaria em cima de qualquer outra. Vazio serializa —
exatamente o comportamento da 0.4.73.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath


def normalize_scope(paths: object) -> tuple[str, ...]:
    """Forma canônica de um escopo: posix, relativo, sem duplicata, ordenado.

    Aceita qualquer iterável de coisas conversíveis em str porque a origem varia
    (JSON do planner, `--scope` do dono, `plan` persistido).
    """
    if paths is None or isinstance(paths, (str, bytes)):
        paths = [paths] if paths else []
    try:
        cru = list(paths)  # type: ignore[arg-type]
    except TypeError:
        return ()
    saida: list[str] = []
    for item in cru:
        if item is None:
            continue
        texto = str(item).strip().replace("\\", "/")
        while texto.startswith("./"):
            texto = texto[2:]
        texto = texto.strip("/")
        # Caminho absoluto ou saindo da raiz não é escopo de projeto. Descartar é
        # mais seguro que "interpretar": um `..` aceito viraria escopo global, e
        # escopo global sobrepõe tudo — ou seja, silenciaria a concorrência toda.
        if not texto:
            continue
        if len(texto) >= 2 and texto[1] == ":":
            continue  # C:/... — absoluto do Windows
        partes = [p for p in texto.split("/") if p != "."]
        if not partes or any(p == ".." for p in partes):
            continue
        saida.append("/".join(partes))
    return tuple(sorted(dict.fromkeys(saida)))


def _cobre(prefixo: str, caminho: str) -> bool:
    """`prefixo` contém `caminho` — comparando SEGMENTOS, não texto.

    A armadilha clássica: `src/auth` é prefixo textual de `src/authz`, e não
    tem nada a ver com ele. Comparar `PurePosixPath.parts` elimina a classe
    inteira de falso positivo.
    """
    a = PurePosixPath(prefixo).parts
    b = PurePosixPath(caminho).parts
    return len(a) <= len(b) and b[: len(a)] == a


def paths_overlap(um: str, outro: str) -> bool:
    """Dois caminhos disputam o mesmo código (um contém o outro, ou são iguais)."""
    return _cobre(um, outro) or _cobre(outro, um)


def scopes_overlap(um: object, outro: object) -> bool:
    """Duas tasks disputam código?

    Escopo vazio é DESCONHECIDO e sobrepõe tudo: sem prova de disjunção, o
    runtime serializa. Conservador de propósito — o custo de errar para o lado
    da concorrência é dois agentes no mesmo arquivo.
    """
    a = normalize_scope(um)
    b = normalize_scope(outro)
    if not a or not b:
        return True
    return any(paths_overlap(x, y) for x in a for y in b)


def path_in_scope(caminho: str, escopo: object) -> bool:
    """O arquivo está dentro do escopo declarado?

    Escopo vazio aceita tudo: não há declaração contra a qual julgar, e acusar
    desvio de um escopo que ninguém declarou seria ruído.
    """
    alvos = normalize_scope(escopo)
    if not alvos:
        return True
    normalizado = normalize_scope([caminho])
    if not normalizado:
        return True
    return any(_cobre(prefixo, normalizado[0]) for prefixo in alvos)


# Token com barra e extensão/segmentos plausíveis de caminho de projeto.
_TOKEN_CAMINHO = re.compile(r"[A-Za-z0-9_.\-]+(?:[/\\][A-Za-z0-9_.\-]+)+")


def infer_scope(prompt: str, known_roots: object = None) -> tuple[str, ...]:
    """Escopo lido do que o PRÓPRIO PEDIDO nomeia, nada além.

    0.4.74 — só entra caminho que aparece literalmente no prompt E cuja primeira
    pasta existe no projeto. Prompt que não nomeia caminho devolve escopo vazio, e
    vazio serializa.

    Deliberadamente burro. A tentação é pedir o escopo a um modelo, mas nesta
    arquitetura o escopo é o que AUTORIZA duas tasks a rodarem juntas: um escopo
    inventado com confiança liberaria exatamente o par que não podia rodar junto.
    Adivinhar errado aqui custa dois agentes no mesmo arquivo (bug-077); não
    adivinhar custa só serializar, que é o comportamento de antes.
    """
    raizes = {str(r).strip().replace("\\", "/").strip("/") for r in (known_roots or [])}
    achados: list[str] = []
    for bruto in _TOKEN_CAMINHO.findall(prompt or ""):
        candidato = normalize_scope([bruto.rstrip(".,;:)")])
        if not candidato:
            continue
        caminho = candidato[0]
        primeira = caminho.split("/")[0]
        # Sem lista de raízes não há como conferir existência; aceitar tudo aí
        # inventaria escopo a partir de qualquer coisa com barra no texto
        # (URL, versão, comando) — e escopo errado é pior que escopo nenhum.
        if not raizes or primeira not in raizes:
            continue
        achados.append(caminho)
    return normalize_scope(achados)


def outside_scope(arquivos: object, escopo: object) -> list[str]:
    """Arquivos que a task tocou FORA do que declarou.

    É a metade de detecção da garantia: na árvore compartilhada o runtime não
    impede o desvio, então tem que medi-lo e contá-lo (degradação
    `scope_violation`, visível ao validator e ao dono).
    """
    alvos = normalize_scope(escopo)
    if not alvos:
        return []
    if arquivos is None or isinstance(arquivos, (str, bytes)):
        arquivos = [arquivos] if arquivos else []
    try:
        itens = list(arquivos)  # type: ignore[arg-type]
    except TypeError:
        return []
    fora: list[str] = []
    for arquivo in itens:
        normalizado = normalize_scope([arquivo])
        if not normalizado:
            continue
        if not path_in_scope(normalizado[0], alvos):
            fora.append(normalizado[0])
    return sorted(dict.fromkeys(fora))
