"""0.4.74 — comparacao de escopos: quem decide se duas tasks podem rodar juntas.

Toda a admissao de concorrencia depende destas funcoes acertarem. Dois erros aqui
tem custo oposto e os dois sao caros: dizer "sobrepoe" quando nao sobrepoe
serializa a frota de volta (o problema que estamos resolvendo); dizer "nao
sobrepoe" quando sobrepoe coloca dois agentes no mesmo arquivo (bug-077).

O caso que este tipo de codigo costuma errar e `src/auth` versus `src/authz`: um
e prefixo TEXTUAL do outro e nao tem nada a ver com ele.
"""

from __future__ import annotations

from orchestrator_runtime.execution.scopes import (
    normalize_scope,
    outside_scope,
    path_in_scope,
    paths_overlap,
    scopes_overlap,
)


# --------------------------------------------------------------------------
# normalizacao
# --------------------------------------------------------------------------


def test_normaliza_separador_e_prefixo() -> None:
    assert normalize_scope(["./src\\auth/", "src/auth"]) == ("src/auth",)


def test_normaliza_ordena_e_deduplica() -> None:
    assert normalize_scope(["tests", "src", "src"]) == ("src", "tests")


def test_normaliza_aceita_string_solta() -> None:
    assert normalize_scope("src/auth") == ("src/auth",)


def test_normaliza_descarta_vazio_e_none() -> None:
    assert normalize_scope([None, "", "   ", "/"]) == ()


def test_normaliza_descarta_caminho_que_sai_da_raiz() -> None:
    """`..` aceito viraria escopo global — e escopo global sobrepoe tudo, ou
    seja, silenciaria a concorrencia inteira."""
    assert normalize_scope(["../outro-projeto", "src/../../fora"]) == ()


def test_normaliza_descarta_absoluto_do_windows() -> None:
    assert normalize_scope(["D:/StarFusion/printbee/src"]) == ()


def test_normaliza_entrada_nao_iteravel() -> None:
    assert normalize_scope(42) == ()


# --------------------------------------------------------------------------
# sobreposicao entre caminhos
# --------------------------------------------------------------------------


def test_auth_nao_sobrepoe_authz() -> None:
    """O falso positivo classico de comparacao textual."""
    assert paths_overlap("src/auth", "src/authz") is False


def test_pasta_contem_arquivo() -> None:
    assert paths_overlap("src", "src/auth/login.py") is True


def test_arquivo_dentro_da_pasta_em_qualquer_ordem() -> None:
    assert paths_overlap("src/auth/login.py", "src") is True


def test_caminhos_iguais_sobrepoem() -> None:
    assert paths_overlap("src/a.py", "src/a.py") is True


def test_irmaos_nao_sobrepoem() -> None:
    assert paths_overlap("src/a.py", "src/b.py") is False
    assert paths_overlap("src/api", "src/web") is False


# --------------------------------------------------------------------------
# sobreposicao entre escopos de task
# --------------------------------------------------------------------------


def test_escopos_disjuntos_rodam_juntos() -> None:
    assert scopes_overlap(["src/api"], ["src/web", "docs"]) is False


def test_escopo_vazio_sobrepoe_tudo() -> None:
    """Desconhecido serializa: sem prova de disjuncao, nao ha concorrencia.

    Sem esta regra uma task sem escopo declarado passaria por "disjunta de
    todas" e rodaria em cima de qualquer outra.
    """
    assert scopes_overlap([], ["src/api"]) is True
    assert scopes_overlap(["src/api"], []) is True
    assert scopes_overlap([], []) is True


def test_sobreposicao_em_um_unico_par_basta() -> None:
    assert scopes_overlap(["src/api", "docs"], ["src/web", "docs"]) is True


def test_escopo_que_virou_vazio_na_normalizacao_serializa() -> None:
    """Escopo so com lixo (`..`, absoluto) e escopo desconhecido, nao global."""
    assert scopes_overlap(["../fora"], ["src/api"]) is True


# --------------------------------------------------------------------------
# deteccao de desvio — a outra metade da garantia
# --------------------------------------------------------------------------


def test_arquivo_no_escopo() -> None:
    assert path_in_scope("src/api/rotas.py", ["src/api"]) is True


def test_arquivo_fora_do_escopo() -> None:
    assert path_in_scope("src/web/app.py", ["src/api"]) is False


def test_sem_escopo_declarado_nada_e_desvio() -> None:
    """Acusar desvio de um escopo que ninguem declarou seria ruido."""
    assert path_in_scope("qualquer/coisa.py", []) is True
    assert outside_scope(["qualquer/coisa.py"], []) == []


def test_lista_o_que_saiu_do_escopo() -> None:
    fora = outside_scope(
        ["src/api/rotas.py", "src/web/app.py", "README.md"], ["src/api"]
    )

    assert fora == ["README.md", "src/web/app.py"]


def test_desvio_normaliza_antes_de_comparar() -> None:
    assert outside_scope([".\\src\\api\\rotas.py"], ["src/api"]) == []


def test_authz_conta_como_desvio_de_auth() -> None:
    assert outside_scope(["src/authz/perm.py"], ["src/auth"]) == ["src/authz/perm.py"]
