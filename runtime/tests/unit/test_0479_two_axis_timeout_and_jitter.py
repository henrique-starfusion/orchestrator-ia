"""0.4.79 — política de execução em DOIS EIXOS (A1) e jitter no backoff (A2).

A1 — até a 0.4.78 havia UM número por papel (`agent_timeout_by_role`), teto de
relógio puro. Um agente que morreu mudo no segundo 5 e um agente que está
produzindo saída sem parar eram tratados IGUAL: os dois só morriam no teto.
Medido nesta frota na task 8ef95928104e — executor/codex em 1940s de um teto de
2400s, produzindo saída o tempo todo (arquivo de eventos passando de 33 mil
linhas, ~150 linhas a cada 20s), e a única forma de saber que estava vivo era
ler na mão o campo "sinal há Ns" do `task status`. O dono perguntou se tinha
travado. Adotado o desenho do `TimeoutPolicy` do LangGraph
(`libs/langgraph/langgraph/types.py`): `run_timeout` (teto duro, nunca renovado)
e `idle_timeout` (tempo sem progresso observável, renovado pelo sinal).

A2 — o backoff de retry de lançamento (bug-111, 0.4.76) tem intervalos FIXOS
(3s, 8s, 15s). O modo de falha que ele atende é 0xC0000142 STATUS_DLL_INIT_FAILED
— exaustão de recurso DA MÁQUINA: no trustsafe, 10/08, quatro lançamentos
falharam em ~1s. Com intervalo fixo todos esperam o mesmo tanto e colidem de
novo contra o mesmo recurso escasso. O backoff baixava a frequência sem quebrar
a sincronia, que é a causa.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator_runtime.agents.process import NO_OUTPUT_MARKER, CliExecutor
from orchestrator_runtime.config import load_config
from orchestrator_runtime.execution.timeouts import (
    MIN_AGENT_TIMEOUT_S,
    minimum_task_budget_s,
    resolve_agent_timeout,
    resolve_agent_timeout_policy,
    split_timeout_axes,
)
from orchestrator_runtime.tasks.service import TaskService

DOIS_EIXOS = {
    "planner": 900,
    "executor": {"run_timeout": 2400, "idle_timeout": 1200},
    "corrector": {"run_timeout": 2400, "idle_timeout": 1200},
    "validator": 1200,
    "tester": 600,
}

FORMATO_ANTIGO = {
    "planner": 900,
    "executor": 2400,
    "corrector": 2400,
    "validator": 1200,
    "tester": 600,
}


def _sleeper(seconds: float) -> list[str]:
    """Processo mudo: nem stdout nem stderr por N segundos."""
    return [sys.executable, "-c", f"import time; time.sleep({seconds})"]


def _talker(seconds: float, every: float = 0.2) -> list[str]:
    """Processo que dá sinal sem parar — o eixo ocioso não pode encostar nele."""
    code = (
        "import time\n"
        f"end=time.time()+{seconds}\n"
        "while time.time()<end:\n"
        f"    print('tick', flush=True); time.sleep({every})\n"
    )
    return [sys.executable, "-c", code]


# ---------------------------------------------------------------------------
# A1 — os dois eixos existem e são independentes
# ---------------------------------------------------------------------------


def test_a1_papel_tem_dois_eixos_distintos() -> None:
    politica = resolve_agent_timeout_policy(
        "executor", remaining_s=100_000, by_role=DOIS_EIXOS
    )
    assert politica.run_timeout_s == 2400
    assert politica.idle_timeout_s == 1200
    assert politica.idle_timeout_s < politica.run_timeout_s


def test_a1_agente_mudo_morre_no_eixo_ocioso_com_teto_duro_sobrando(
    tmp_path: Path,
) -> None:
    """AC-1: sem NENHUM sinal além do ocioso => encerrado, com run_timeout de sobra.

    O eixo ocioso do papel é pequeno neste teste (a mesma janela mínima que o
    watchdog acorda); o teto duro é 60s. O agente é morto sem chegar perto dele.
    """
    politica = resolve_agent_timeout_policy(
        "executor",
        remaining_s=100_000,
        by_role={"executor": {"run_timeout": 60, "idle_timeout": 2}},
    )
    assert politica.run_timeout_s == 60 and politica.idle_timeout_s == 2

    ex = CliExecutor(tmp_path, echo=False)
    ex.no_output_timeout_s = politica.idle_timeout_s
    comeco = time.monotonic()
    result = ex.run(_sleeper(55), timeout_s=politica.run_timeout_s)
    decorrido = time.monotonic() - comeco

    assert result.timed_out is True
    assert NO_OUTPUT_MARKER in result.stderr
    # Morreu pelo eixo OCIOSO: sobrou teto duro de verdade.
    assert decorrido < politica.run_timeout_s / 2, decorrido


def test_a1_quem_da_sinal_dentro_da_janela_nao_e_interrompido(
    tmp_path: Path,
) -> None:
    """AC-2: sinal dentro da janela renova o eixo ocioso — trabalho lento vive."""
    ex = CliExecutor(tmp_path, echo=False)
    ex.no_output_timeout_s = 2  # janela ociosa curtíssima
    result = ex.run(_talker(8), timeout_s=60)  # fala a cada 0.2s por 8s

    assert result.timed_out is False
    assert NO_OUTPUT_MARKER not in result.stderr
    assert "tick" in result.stdout


def test_a1_run_timeout_nunca_e_renovado_por_sinal(tmp_path: Path) -> None:
    """AC-3: sinal contínuo NÃO empurra a tentativa além do teto duro."""
    ex = CliExecutor(tmp_path, echo=False)
    ex.no_output_timeout_s = 2
    comeco = time.monotonic()
    # Falaria por 60s; o teto duro é 3s e não é renovado por nenhum tick.
    result = ex.run(_talker(60), timeout_s=3)
    decorrido = time.monotonic() - comeco

    assert result.timed_out is True
    assert NO_OUTPUT_MARKER not in result.stderr, "morte errada: foi o teto duro"
    assert decorrido < 30, decorrido
    assert "tick" in result.stdout, "estava produzindo e mesmo assim morreu no teto"


def test_a1_sinal_nao_estica_o_teto_duro_na_resolucao() -> None:
    """O eixo duro é função só do papel e do restante — sinal não entra nele."""
    a = resolve_agent_timeout_policy(
        "executor", remaining_s=100_000, by_role=DOIS_EIXOS
    )
    b = resolve_agent_timeout_policy(
        "executor",
        remaining_s=100_000,
        by_role={"executor": {"run_timeout": 2400, "idle_timeout": 99_999}},
    )
    assert a.run_timeout_s == b.run_timeout_s == 2400


# ---------------------------------------------------------------------------
# A1 — encerramento por ociosidade entra no fluxo de INFRA (AC-4)
# ---------------------------------------------------------------------------


def _service(tmp_path: Path) -> TaskService:
    root = tmp_path / ".orchestrator"
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    config = load_config(tmp_path, fake_agents=True)
    return TaskService(config, verbose=False)


def _result(stdout: str = "", stderr: str = "", duration: float = 100.0):
    return SimpleNamespace(
        stdout=stdout, stderr=stderr, duration_s=duration, timed_out=True
    )


def _task(max_duration: int = 8700):
    return SimpleNamespace(
        id="t1", constraints=SimpleNamespace(maximum_duration_seconds=max_duration)
    )


def test_a1_morte_por_ociosidade_e_infra_e_o_texto_fala_de_sinal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-4: mesmo rótulo de infra do watchdog, e o texto diz FALTA DE SINAL."""
    svc = _service(tmp_path)
    monkeypatch.setattr(svc, "_remaining_duration_s", lambda _t: 5000)

    issue_id, description, error_text = svc._timeout_issue(
        "executor", "codex", _result("", f"{NO_OUTPUT_MARKER} morto"), _task()
    )

    assert issue_id == "AGENT-NO-OUTPUT-HANG"
    assert "sem sinal de vida" in description
    assert "idle_timeout=1200s" in description
    assert "não qualidade" in description
    assert "sem sinal de vida" in error_text


def test_a1_agent_no_output_hang_vai_para_reject_iteration_infra() -> None:
    """O ramo que consome `_timeout_issue` é o de infra, não o de mérito.

    Guard estático: o rótulo nasce dentro do bloco que chama
    `_reject_iteration_infra`. Se alguém reencaminhar para julgamento de mérito,
    este teste cai.
    """
    import orchestrator_runtime.tasks.service as modulo

    fonte = Path(modulo.__file__).read_text(encoding="utf-8")
    trecho = fonte.split("issue_id, description, error_text = self._timeout_issue")[1]
    assert "_reject_iteration_infra" in trecho.split("continue")[0]


# ---------------------------------------------------------------------------
# A1 — retrocompatibilidade (AC-5) e aritmética do bug-104 (AC-7)
# ---------------------------------------------------------------------------


def test_a1_formato_antigo_vira_run_timeout_com_idle_nulo() -> None:
    """AC-5: inteiro puro = teto duro; eixo ocioso NULO (comportamento 0.4.78)."""
    for papel, esperado in FORMATO_ANTIGO.items():
        politica = resolve_agent_timeout_policy(
            papel, remaining_s=100_000, by_role=FORMATO_ANTIGO
        )
        assert politica.run_timeout_s == esperado, papel
        assert politica.idle_timeout_s is None, papel


def test_a1_resolve_agent_timeout_antigo_intacto() -> None:
    """A assinatura antiga continua devolvendo o mesmo inteiro de sempre."""
    assert (
        resolve_agent_timeout("executor", remaining_s=1000, by_role=FORMATO_ANTIGO)
        == 400  # 1000 - VERDICT_RESERVE_S (bug-104)
    )
    assert (
        resolve_agent_timeout("planner", remaining_s=100_000, by_role=FORMATO_ANTIGO)
        == 900
    )
    assert resolve_agent_timeout("planner", remaining_s=10, by_role=FORMATO_ANTIGO) == 10


def test_a1_idle_nulo_cai_no_global_e_preserva_0478(tmp_path: Path) -> None:
    """Papel sem eixo próprio usa o `agent_no_output_timeout_s` — como na 0.4.78."""
    config_dir = tmp_path / ".orchestrator" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "policies.json").write_text(
        json.dumps(
            {
                "agent_no_output_timeout_s": 900,
                "maximum_duration_seconds": 8700,
                "agent_timeout_by_role": FORMATO_ANTIGO,
            }
        ),
        encoding="utf-8",
    )
    config = load_config(tmp_path, fake_agents=True)
    assert config.limits.agent_idle_timeout_by_role.get("executor") is None

    svc = TaskService(config, verbose=False)
    task = _task()
    assert svc._resolve_idle_timeout("executor", task) == 900
    assert svc._resolve_agent_timeout_policy("executor", task).idle_timeout_s is None


def test_a1_policies_com_dois_eixos_e_lido(tmp_path: Path) -> None:
    config_dir = tmp_path / ".orchestrator" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "policies.json").write_text(
        json.dumps(
            {"maximum_duration_seconds": 8700, "agent_timeout_by_role": DOIS_EIXOS}
        ),
        encoding="utf-8",
    )
    config = load_config(tmp_path, fake_agents=True)
    assert config.limits.agent_timeout_by_role["executor"] == 2400
    assert config.limits.agent_idle_timeout_by_role["executor"] == 1200
    assert "planner" not in config.limits.agent_idle_timeout_by_role

    svc = TaskService(config, verbose=False)
    assert svc._resolve_idle_timeout("executor", _task()) == 1200


def test_a1_idle_zero_desliga_o_eixo() -> None:
    politica = resolve_agent_timeout_policy(
        "executor",
        remaining_s=100_000,
        by_role={"executor": {"run_timeout": 2400, "idle_timeout": 0}},
    )
    assert politica.idle_timeout_s is None


def test_a1_split_axes_aceita_os_dois_formatos_juntos() -> None:
    run, idle = split_timeout_axes(DOIS_EIXOS)
    assert run == {
        "planner": 900,
        "executor": 2400,
        "corrector": 2400,
        "validator": 1200,
        "tester": 600,
    }
    assert idle == {"executor": 1200, "corrector": 1200}


def test_a1_piso_do_orcamento_usa_so_o_eixo_duro() -> None:
    """AC-7: bug-104 intacto — o piso deriva dos tetos DUROS, não dos ociosos."""
    assert minimum_task_budget_s(DOIS_EIXOS) == 8700
    assert minimum_task_budget_s(FORMATO_ANTIGO) == 8700
    # Ocioso gigante não pode inflar o piso.
    inflado = dict(DOIS_EIXOS)
    inflado["executor"] = {"run_timeout": 2400, "idle_timeout": 99_999}
    assert minimum_task_budget_s(inflado) == 8700


def test_a1_teto_da_task_continua_sendo_elevado_ao_piso(tmp_path: Path) -> None:
    config_dir = tmp_path / ".orchestrator" / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "policies.json").write_text(
        json.dumps(
            {"maximum_duration_seconds": 3600, "agent_timeout_by_role": DOIS_EIXOS}
        ),
        encoding="utf-8",
    )
    config = load_config(tmp_path, fake_agents=True)
    assert config.limits.maximum_duration_seconds == 8700
    assert config.limits.duration_floor_raised_from == 3600


def test_a1_orcamento_esgotado_ainda_devolve_o_restante() -> None:
    politica = resolve_agent_timeout_policy(
        "executor", remaining_s=10, by_role=DOIS_EIXOS
    )
    assert politica.run_timeout_s == 10 < MIN_AGENT_TIMEOUT_S


# ---------------------------------------------------------------------------
# A2 — jitter no backoff de lançamento
# ---------------------------------------------------------------------------


class _Sequencia:
    """Fonte de aleatoriedade determinística e injetável."""

    def __init__(self, *valores: float) -> None:
        self._valores = list(valores)
        self.chamadas = 0

    def __call__(self) -> float:
        valor = self._valores[self.chamadas % len(self._valores)]
        self.chamadas += 1
        return valor


def test_a2_duas_retentativas_do_mesmo_instante_nao_esperam_igual(
    tmp_path: Path,
) -> None:
    """AC-1: dois agentes que falharam juntos não voltam juntos."""
    svc = _service(tmp_path)
    base = svc._LAUNCH_RETRY_BACKOFF_S[0]

    agente_a = _service(tmp_path)
    agente_a._launch_retry_rand = _Sequencia(0.0)
    agente_b = _service(tmp_path)
    agente_b._launch_retry_rand = _Sequencia(0.9)

    espera_a = agente_a._launch_backoff_s(base)
    espera_b = agente_b._launch_backoff_s(base)

    assert espera_a != espera_b, (espera_a, espera_b)
    assert svc._LAUNCH_RETRY_JITTER_RATIO > 0


def test_a2_espera_fica_no_intervalo_documentado(tmp_path: Path) -> None:
    """AC-2: [base, base*(1+ratio)) — nunca encurta, nunca estica sem teto."""
    svc = _service(tmp_path)
    ratio = svc._LAUNCH_RETRY_JITTER_RATIO
    for base in svc._LAUNCH_RETRY_BACKOFF_S:
        for sorteio in (0.0, 0.25, 0.5, 0.999):
            svc._launch_retry_rand = _Sequencia(sorteio)
            espera = svc._launch_backoff_s(base)
            assert espera >= base, (base, sorteio, espera)
            assert espera <= base * (1 + ratio), (base, sorteio, espera)


def test_a2_sorteio_fora_da_faixa_nao_quebra_o_limite(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    ratio = svc._LAUNCH_RETRY_JITTER_RATIO
    for sorteio in (-5.0, 7.0):
        svc._launch_retry_rand = _Sequencia(sorteio)
        espera = svc._launch_backoff_s(8.0)
        assert 8.0 <= espera <= 8.0 * (1 + ratio), (sorteio, espera)


def test_a2_fonte_quebrada_cai_no_backoff_base(tmp_path: Path) -> None:
    """Sorteio nunca derruba retry: sem sorteio, o intervalo antigo."""

    def _boom() -> float:
        raise RuntimeError("sem entropia")

    svc = _service(tmp_path)
    svc._launch_retry_rand = _boom
    assert svc._launch_backoff_s(8.0) == 8.0


class _AdapterQueNuncaNasce:
    """Lançamento que falha sempre — o mesmo 0xC0000142 do trustsafe."""

    def __init__(self) -> None:
        self.execucoes = 0

    async def run(self, request):  # type: ignore[no-untyped-def]
        self.execucoes += 1
        return SimpleNamespace(
            status="failed",
            exit_code=0xC0000142,
            stdout="",
            stderr="",
            changed_files=[],
            duration_s=0.0,
        )


def _retry(
    svc: TaskService, adapter: _AdapterQueNuncaNasce, restante: int
) -> list[dict]:
    relatos: list[dict] = []
    inicial = SimpleNamespace(
        status="failed", exit_code=0xC0000142, stdout="", stderr="",
        changed_files=[], duration_s=0.0,
    )
    svc._remaining_duration_s = lambda _t: restante  # type: ignore[assignment]
    asyncio.run(
        svc._retry_launch_failure(
            adapter,
            SimpleNamespace(role="executor"),
            inicial,
            task=_task(),
            agent_id="codex",
            report=lambda **d: relatos.append(d),
        )
    )
    return relatos


def test_a2_guarda_de_orcamento_usa_a_espera_COM_jitter(tmp_path: Path) -> None:
    """AC-3: comparar contra a base e dormir o sorteado furaria o orçamento."""
    svc = _service(tmp_path)
    svc._LAUNCH_RETRY_BACKOFF_S = (100.0,)
    svc._launch_retry_rand = _Sequencia(1.0)  # espera final = 150s
    base, ratio = 100.0, svc._LAUNCH_RETRY_JITTER_RATIO
    esperado = base * (1 + ratio)
    # Orçamento que CABERIA a base (100+60=160) mas NÃO cabe a espera final.
    restante = int(base + MIN_AGENT_TIMEOUT_S + 1)
    assert restante < esperado + MIN_AGENT_TIMEOUT_S

    adapter = _AdapterQueNuncaNasce()
    relatos = _retry(svc, adapter, restante)

    assert adapter.execucoes == 0, "dormiu além do orçamento da task"
    assert any(r.get("retry_skipped") == "budget" for r in relatos), relatos


def test_a2_com_orcamento_folgado_a_retentativa_acontece(tmp_path: Path) -> None:
    svc = _service(tmp_path)
    svc._LAUNCH_RETRY_BACKOFF_S = (0.0, 0.0)
    svc._launch_retry_rand = _Sequencia(0.5)
    adapter = _AdapterQueNuncaNasce()
    relatos = _retry(svc, adapter, 8700)

    assert adapter.execucoes == 2
    tentativas = [r for r in relatos if r.get("backoff_s") is not None]
    assert len(tentativas) == 2
    assert all("backoff_base_s" in r for r in tentativas), tentativas


def test_a2_esgotadas_as_tentativas_continua_infra_e_nunca_merito(
    tmp_path: Path,
) -> None:
    """AC-4: o resultado devolvido segue sendo a falha de lançamento."""
    svc = _service(tmp_path)
    svc._LAUNCH_RETRY_BACKOFF_S = (0.0, 0.0)
    svc._launch_retry_rand = _Sequencia(0.3)
    adapter = _AdapterQueNuncaNasce()
    relatos = _retry(svc, adapter, 8700)

    final = [r for r in relatos if r.get("retry_exhausted")]
    assert final, relatos
    assert final[0]["exit_code"] == 0xC0000142
    assert "infra, não mérito" in final[0]["summary"]
