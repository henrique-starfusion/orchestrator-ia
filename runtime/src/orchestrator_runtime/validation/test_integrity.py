"""Detecção de ENFRAQUECIMENTO DE TESTE no diff da iteração (0.4.68).

Inspirado no `fable-judge` (github.com/Sahir619/fable-method, MIT), cuja
heurística central é: *"um teste alterado é culpado até a justificativa remontar
a uma spec"*. A ideia é reimplementada aqui — não copiamos texto nem prompts.

Por que isto existe: o executor escreve o código **e** os testes, e o gate só
verifica se a suíte fica verde. Nada impedia baixar uma asserção, marcar um
teste como skip ou apagar um caso para o gate passar — e o resultado sairia
`COMPLETED score=1.0`, igual a um trabalho honesto.

Escolha deliberada de severidade: o que sai daqui é **não-bloqueante**. Refator
legítimo remove asserção o tempo todo, e esta sessão já pagou caro por
heurística de texto confiante demais (bug-097: o classificador leu código ecoado
como diagnóstico). O papel deste módulo é OBRIGAR o validador a justificar,
não reprovar sozinho.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Caminho de teste: cobre pytest, xunit/nunit (.NET), jest/karma (JS/TS), go.
_TEST_PATH_RE = re.compile(
    r"(^|[/\\])(tests?|spec|__tests__)([/\\]|$)|(test_|_test\.|\.test\.|\.spec\.|Tests?\.cs$)",
    re.IGNORECASE,
)

# Uma asserção — em qualquer das stacks da frota.
_ASSERT_RE = re.compile(
    r"\b(assert\w*|Assert\.\w+|expect\s*\(|should\b|\.Should\(\)|EXPECT_\w+)",
    re.IGNORECASE,
)

# Desligar um teste sem apagá-lo.
_SKIP_RE = re.compile(
    r"(@pytest\.mark\.skip|@unittest\.skip|pytest\.skip\(|"
    r"\b(it|test|describe)\.skip\s*\(|\bxit\s*\(|\bxdescribe\s*\(|"
    r"\[Ignore|\[Skip|Skip\s*=|\.Skip\(|t\.Skip\(|@Ignore)",
    re.IGNORECASE,
)

# Declaração de caso de teste.
_TEST_DECL_RE = re.compile(
    r"(def\s+test_\w+|\bit\s*\(|\btest\s*\(|\[Fact\]|\[Theory\]|func\s+Test\w+)",
)


def is_test_path(path: str) -> bool:
    """O caminho parece ser de arquivo de teste?"""
    return bool(_TEST_PATH_RE.search((path or "").replace("\\", "/")))


@dataclass
class IntegrityFinding:
    kind: str
    path: str
    detail: str

    def as_issue(self, issue_id: str) -> dict[str, str]:
        return {
            "id": issue_id,
            "severity": "non_blocking",
            "kind": "test_integrity",
            "description": f"{self.path}: {self.detail}",
        }


@dataclass
class _FileDelta:
    path: str = ""
    asserts_removed: int = 0
    asserts_added: int = 0
    skips_added: int = 0
    decls_removed: int = 0
    decls_added: int = 0
    skip_lines: list[str] = field(default_factory=list)


def _iter_file_deltas(diff: str):
    """Percorre um diff unificado agrupando por arquivo."""
    atual: _FileDelta | None = None
    for line in (diff or "").splitlines():
        if line.startswith("diff --git "):
            if atual is not None:
                yield atual
            atual = _FileDelta()
            continue
        if atual is None:
            continue
        if line.startswith("+++ "):
            caminho = line[4:].strip()
            if caminho.startswith("b/"):
                caminho = caminho[2:]
            atual.path = caminho
            continue
        if line.startswith("---") or line.startswith("@@"):
            continue
        # Conteúdo. '+'/'-' de verdade (o cabeçalho já foi filtrado acima).
        if line.startswith("+"):
            corpo = line[1:]
            if _ASSERT_RE.search(corpo):
                atual.asserts_added += 1
            if _SKIP_RE.search(corpo):
                atual.skips_added += 1
                atual.skip_lines.append(corpo.strip()[:120])
            if _TEST_DECL_RE.search(corpo):
                atual.decls_added += 1
        elif line.startswith("-"):
            corpo = line[1:]
            if _ASSERT_RE.search(corpo):
                atual.asserts_removed += 1
            if _TEST_DECL_RE.search(corpo):
                atual.decls_removed += 1
    if atual is not None:
        yield atual


def analyze_diff(diff: str) -> list[IntegrityFinding]:
    """Sinais de enfraquecimento num diff unificado. Só arquivos de teste.

    Três sinais, todos mecânicos — nada de julgar intenção:

    - ``assertions_removed``  saíram mais asserções do que entraram
    - ``tests_skipped``       apareceu marcador de skip/ignore
    - ``tests_deleted``       sumiram mais casos de teste do que foram criados
    """
    achados: list[IntegrityFinding] = []
    for d in _iter_file_deltas(diff):
        if not d.path or not is_test_path(d.path):
            continue
        if d.asserts_removed > d.asserts_added:
            achados.append(
                IntegrityFinding(
                    "assertions_removed",
                    d.path,
                    f"{d.asserts_removed} asserção(ões) removida(s) contra "
                    f"{d.asserts_added} adicionada(s) — justifique com a spec ou reverta",
                )
            )
        if d.skips_added:
            exemplo = d.skip_lines[0] if d.skip_lines else ""
            achados.append(
                IntegrityFinding(
                    "tests_skipped",
                    d.path,
                    f"{d.skips_added} teste(s) desligado(s) por skip/ignore: {exemplo!r}",
                )
            )
        if d.decls_removed > d.decls_added:
            achados.append(
                IntegrityFinding(
                    "tests_deleted",
                    d.path,
                    f"{d.decls_removed} caso(s) de teste removido(s) contra "
                    f"{d.decls_added} adicionado(s)",
                )
            )
    return achados


def summarize(achados: list[IntegrityFinding]) -> str:
    """Bloco para o prompt do validador. Vazio quando não há nada a explicar."""
    if not achados:
        return ""
    linhas = [f"- [{a.kind}] {a.path}: {a.detail}" for a in achados]
    return (
        "SUSPEITA DE ENFRAQUECIMENTO DE TESTE — o diff mexeu em arquivos de "
        "teste de um jeito que costuma mascarar falha. Um teste alterado é "
        "CULPADO até a justificativa remontar ao pedido ou à spec. Para cada "
        "item: confirme no diff e diga se é legítimo (refator/spec mudou) ou "
        "se é fraude de conclusão. Se for fraude, isso é blocking.\n"
        + "\n".join(linhas)
    )
