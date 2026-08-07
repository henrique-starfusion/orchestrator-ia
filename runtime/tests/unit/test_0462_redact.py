"""0.4.62 — redação de segredos que não come a saída do agente (bug-088).

Caso real: task 143e8b2ca47b (documentação do próprio orquestrador). O JSON do
decompositor mencionava "NAO exponha secrets" e voltou como
`{"subtasks":[ [REDACTED] [REDACTED] ]}` — o fan-out não rodou porque o parse
não achou subtarefa nenhuma. Redação é para o VALOR, não para a linha.
"""

from __future__ import annotations

import json

from orchestrator_runtime.agents.process import redact

# --------------------------------------------------------- segredo some


def test_env_dump_perde_o_valor() -> None:
    out = redact("API_KEY=sk-live-abcdef123456\nOUTRA=coisa")
    assert "sk-live-abcdef123456" not in out
    assert "API_KEY=[REDACTED]" in out
    assert "OUTRA=coisa" in out


def test_json_com_token() -> None:
    out = redact('{"token": "ghp_1234567890abcdefgh"}')
    assert "ghp_1234567890abcdefgh" not in out
    assert "[REDACTED]" in out


def test_authorization_bearer() -> None:
    out = redact("Authorization: eyJhbGciOiJIUzI1NiJ9.abc")
    assert "eyJhbGciOiJIUzI1NiJ9.abc" not in out


def test_senha_curta_some() -> None:
    assert "hunter2" not in redact("password: hunter2")


def test_valor_sem_digito_tambem_some() -> None:
    """`supersecret` nao tem digito e e segredo do mesmo jeito."""
    assert "supersecret" not in redact("API_KEY=supersecret")


def test_chave_com_prefixo_de_ambiente() -> None:
    out = redact("PROD_DB_PASSWORD=p4ssw0rd-secreta")
    assert "p4ssw0rd-secreta" not in out


# --------------------------------------------- prosa e estrutura sobrevivem


def test_prosa_sobre_secrets_sobrevive() -> None:
    linha = "- NAO exponha secrets. Documente apenas: nome logico, finalidade"
    assert redact(linha) == linha


def test_o_json_do_decompositor_sobrevive() -> None:
    """A regressão exata que matou o fan-out."""
    payload = {
        "subtasks": [
            {
                "id": "s5",
                "title": "Configuracao",
                "scope": ["docs/configuracao.md"],
                "instruction": (
                    "Documentar as chaves. NAO exponha secrets: registre apenas "
                    "nome logico, finalidade e obrigatoriedade."
                ),
            },
            {
                "id": "s6",
                "title": "Integracao",
                "scope": ["docs/integracao-agentes.md"],
                "instruction": "Como cada CLI e acionado; token de sessao nao entra.",
            },
        ]
    }
    texto = "```json\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n```"
    saida = redact(texto)

    # A propriedade que importa: a ESTRUTURA sobrevive. Uma palavra da prosa
    # pode virar [REDACTED] (aqui, o que vem depois de "secrets:"), mas o JSON
    # continua parseável e as subtarefas continuam existindo — que era
    # exatamente o que a versão antiga destruía.
    corpo = saida.split("```json\n", 1)[1].rsplit("\n```", 1)[0]
    parsed = json.loads(corpo)
    assert [s["id"] for s in parsed["subtasks"]] == ["s5", "s6"]
    assert parsed["subtasks"][0]["scope"] == ["docs/configuracao.md"]
    assert parsed["subtasks"][1]["title"] == "Integracao"


def test_placeholder_de_documentacao_sobrevive() -> None:
    for linha in (
        "API_KEY=<sua-chave-aqui>",
        "token: ${GITHUB_TOKEN}",
        "password: nome",
        "SECRET_NAME: obrigatorio",
    ):
        assert redact(linha) == linha, linha


def test_linha_sem_marcador_intacta() -> None:
    linha = 'host: "db.interno.local"'
    assert redact(linha) == linha


def test_preserva_o_resto_da_linha() -> None:
    out = redact('cfg = {"api_key": "abcdef1234567890", "porta": 8080}')
    assert "porta" in out and "8080" in out
    assert "abcdef1234567890" not in out


def test_multilinha_preserva_quebras() -> None:
    entrada = "linha1\nAPI_KEY=segredo123456789\nlinha3"
    saida = redact(entrada)
    assert saida.splitlines()[0] == "linha1"
    assert saida.splitlines()[2] == "linha3"
