"""Serviço principal de orquestração de tarefas."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import random
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger(__name__)

from orchestrator_runtime.agents import AgentRegistry
from orchestrator_runtime.agents.base import AgentRequest, AgentResult
from orchestrator_runtime.agents.health import auth_hint, classify_agent_failure
from orchestrator_runtime.agents.process import NO_OUTPUT_MARKER, CliExecutor
from orchestrator_runtime.agents.reaper import identity_matches, process_identity
from orchestrator_runtime.agents.repair import repair_agent
from orchestrator_runtime.callers import caller_profile, detect_caller
from orchestrator_runtime.config import RuntimeConfig, load_config
from orchestrator_runtime.documentation import DocumentationUpdater
from orchestrator_runtime.errors import CancelledError, TaskNotFoundError
from orchestrator_runtime.events import EventBus, EventType, RuntimeEvent
from orchestrator_runtime.execution.git_workspace import (
    GitBaseline,
    capture_baseline,
    changed_files_since,
    run_git,
)
from orchestrator_runtime.execution.fanout import (
    SubtaskSpec,
    decomposition_prompt,
    parse_subtasks,
)
from orchestrator_runtime.execution.locks import WriteLock, _pid_alive
from orchestrator_runtime.execution.scopes import (
    normalize_scope,
    outside_scope,
    path_in_scope,
    scopes_overlap,
)
from orchestrator_runtime.execution.worktrees import (
    WorktreeHandle,
    apply_patch,
    cleanup_task_worktrees,
    collect_patch,
    create_worktree,
    patch_files,
    worktrees_available,
)
from orchestrator_runtime.execution.timeouts import (
    MIN_AGENT_TIMEOUT_S,
    AgentTimeoutPolicy,
    resolve_agent_timeout_policy,
)
from orchestrator_runtime.manager_model import build_manager
from orchestrator_runtime.memory.database import dumps
from orchestrator_runtime.textutil import repair_mojibake
from orchestrator_runtime.planning.analyzer import Planner
from orchestrator_runtime.routing.manager import RulesRouter
from orchestrator_runtime.tasks.models import (
    OrchestrationPlan,
    TaskConstraints,
    TaskRecord,
)
from orchestrator_runtime.tasks.repository import TaskRepository
from orchestrator_runtime.tasks.state_machine import (
    MID_PIPELINE_STATES,
    TERMINAL_STATES,
    TaskState,
    can_resume,
)

TERMINAL_LIKE = TERMINAL_STATES
from orchestrator_runtime.testing import TestRunner
from orchestrator_runtime.testing.discovery import stack_test_commands
from orchestrator_runtime.validation.test_integrity import (
    analyze_diff,
    is_test_path,
    summarize,
)

# 0.4.73 — piso da cadência do heartbeat do loop. A cadência sai do perfil do
# chamador (20s bloqueante, 30s polling); o piso existe para um perfil futuro
# com valor agressivo não transformar sinal de vida em enchente de eventos.
LOOP_HEARTBEAT_MIN_S = 10


@dataclass
class TaskRunContext:
    """Estado do run de UMA task. Até a 0.4.73 isto vivia no serviço.

    Com uma única task ativa por projeto funcionava: `_execute_loop` reatribuía
    tudo no topo e ninguém competia. Mas o servidor MCP roda todas as tasks no
    MESMO processo — então, no instante em que duas rodam juntas, a task B zera
    o relógio, o baseline git, o `run_ctx` e a lista de modelos esgotados da
    task A. O resultado não é um erro: é `changed_files` atribuído à task
    errada, orçamento de tempo calculado do início errado e learning gravado com
    o contexto de outra. Falha silenciosa, que a serialização escondia.

    Um contexto por task_id, criado sob demanda e descartado no fim do run.
    """

    started_monotonic: float = field(default_factory=time.monotonic)
    git_baseline: GitBaseline = field(default_factory=GitBaseline)
    run_ctx: dict[str, Any] = field(default_factory=dict)
    exhausted_models: set[tuple[str, str]] = field(default_factory=set)
    # (role, agent_id) da última etapa despachada — o heartbeat do loop nomeia
    # quem está no ar, e com N tasks concorrentes isso é por task.
    current_agent: tuple[str, str] | None = None
    # 0.4.74 — executor de CLI próprio. `on_heartbeat` e `progress_probe` são
    # atributos do executor: compartilhá-lo entre tasks concorrentes faria a
    # última a despachar roubar o heartbeat das outras e substituir a sonda de
    # silêncio delas. Mesmo motivo do `_subtask_executor` do fan-out.
    executor: Any = None
from orchestrator_runtime.validation import (
    CompletionGate,
    DeterministicValidator,
    LlmReviewValidator,
)



def _collect_input_hashes(project_path, changed_files):
    """Hashes de auditoria da validação (prompts.md Type 7, 0.4.52-C2):
    sha256 por arquivo alterado (máx 20, pula ausentes e >2MB) +
    rev-parse HEAD quando o projeto for repo git. Tolerante a falhas:
    qualquer erro vira omissão da chave, nunca derruba a validação."""
    import hashlib
    import subprocess

    out = {}
    files = {}
    for rel in (changed_files or [])[:20]:
        try:
            p = project_path / rel
            if not p.is_file() or p.stat().st_size > 2 * 1024 * 1024:
                continue
            files[str(rel).replace(chr(92), "/")] = hashlib.sha256(
                p.read_bytes()
            ).hexdigest()
        except OSError:
            continue
    if files:
        out["files"] = files
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if rev.returncode == 0 and rev.stdout.strip():
            out["head"] = rev.stdout.strip()
    except Exception:
        pass
    return out


class TaskService:
    # Teto do refino de plano (advisory) — o workflow nunca fica preso em
    # SELECTING_AGENTS mais que isso; o plano determinístico já existe.
    PLANNER_REFINE_CAP_S = 300
    # 0.4.24 — teto total da fase SELECTING_AGENTS (skill_selector + planner refine)
    #
    # bug-101 — era 180, MENOR que o próprio `PLANNER_REFINE_CAP_S`. Como o teto
    # efetivo do refino é `min(300, 180 - decorrido)`, os 300s prometidos NUNCA
    # eram alcançáveis: o planner tinha ~180s reais. E o modelo preferido do
    # planner é `fable` (o mais deliberativo). Medido no printbee: 4 refinos,
    # 2 concluíram em 57s e 81s, 2 morreram em 180s cravados com ZERO byte —
    # `claude -p` só imprime no fim, então o timeout não deixa nem saída
    # parcial. 50% de perda, e a task seguia sem plano refinado.
    #
    # Agora a fase comporta o skill_selector + o refino inteiro, por construção.
    @property
    def selecting_agents_cap_s(self) -> int:
        return int(self.config.limits.skill_selection_timeout_s) + self.PLANNER_REFINE_CAP_S

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        verbose: bool = True,
    ) -> None:
        self.config = config
        # 0.4.29 — quem chamou define o tratamento: superficie sem console (MCP,
        # Cursor) nao ganha nada com eco no stdout e depende dos eventos;
        # sessao bloqueante (Claude Code, Codex) precisa ver saida ao vivo.
        self.caller = detect_caller()
        self.caller_profile = caller_profile(self.caller)
        echo = verbose and self.caller_profile.echo
        self.bus = EventBus(verbose=echo)
        self.repo = TaskRepository(str(config.db_path))
        self.executor = CliExecutor(
            config.project_path,
            echo=echo,
            infra_fail_fast_count=config.limits.agent_infra_fail_fast_count,
            heartbeat_s=self.caller_profile.heartbeat_s,
        )
        self.registry = AgentRegistry(config, self.executor)
        self.router = RulesRouter(config, self.registry)
        self.manager = build_manager(config, self.router)
        self.planner = Planner()
        self.tests = TestRunner(self.executor)
        self.det_validator = DeterministicValidator()
        self.llm_validator = LlmReviewValidator()
        self.gate = CompletionGate(config.limits.minimum_validation_score)
        # task_ids com _execute_loop ativo neste processo (anti double-start MCP)
        self._running_tasks: set[str] = set()
        # bug-085 — órfãs já adotadas por este processo: sem isto, cada poll de
        # status dispararia uma nova thread para a mesma task na janela entre o
        # start e a primeira transição de estado.
        self._adopted: set[str] = set()
        # bug-113 - o set evita repeticao neste TaskService; o lock curto
        # serializa a lease QUEUED entre processos. Gate separado cobre polls
        # concorrentes em threads do mesmo servidor MCP.
        self._queue_adoption_gate = threading.Lock()
        self._queue_adoption_lock = WriteLock(
            config.orchestrator_root / "runtime" / "locks" / "queue.adopt.lock",
            timeout_s=1,
        )
        # bug-119 - a ceifa de CLI orfao roda nos MESMOS polls da adocao de task
        # orfa. Gate de thread para os polls concorrentes deste processo; lock de
        # arquivo (curto) para os outros processos. A reivindicacao final e uma
        # transacao no SQLite, entao o lock e a primeira barreira, nao a unica.
        self._reap_gate = threading.Lock()
        self._reap_lock = WriteLock(
            config.orchestrator_root / "runtime" / "locks" / "agent.reap.lock",
            timeout_s=1,
        )
        self.docs = DocumentationUpdater()
        self.lock = WriteLock(
            config.orchestrator_root / "runtime" / "locks" / "workspace.write.lock"
        )
        # 0.4.74 — TESTING é o único trecho que continua exclusivo. Escopos
        # disjuntos separam CÓDIGO, não recurso de máquina: duas suítes no mesmo
        # diretório disputam build dir, cache e porta, e o resultado de uma
        # contamina o da outra independentemente de quais arquivos cada task
        # mexeu. Timeout largo porque suíte lenta é normal; a alternativa
        # (rodar junto) produz falha de teste que não existe.
        self._tests_lock = WriteLock(
            config.orchestrator_root / "runtime" / "locks" / "tests.run.lock",
            timeout_s=1800,
        )
        # As tasks concorrentes rodam cada uma em sua thread com seu event loop
        # (`_start_background` → `asyncio.run`), e o `WriteLock` recusa na hora
        # quando outro asyncio task o segura. Este portão de thread garante que
        # só um chamador deste processo chegue ao lock de arquivo por vez.
        self._tests_gate = threading.Lock()
        # 0.4.74 — contexto POR TASK (relógio, baseline git, run_ctx, modelos
        # esgotados, etapa corrente). Antes eram atributos do serviço, o que só
        # funcionava com uma task ativa por vez — ver `TaskRunContext`.
        self._contexts: dict[str, TaskRunContext] = {}
        # 0.4.63 — agentes já reparados neste processo. UM reparo por agente:
        # se reinstalar não resolveu, reinstalar de novo também não vai, e o
        # laço queimaria o orçamento da task instalando npm em círculos.
        self._repaired_agents: set[str] = set()
        # bug-098 — threads de dequeue/adoção iniciadas por ESTE processo.
        self._background_threads: list[threading.Thread] = []

    def _ctx(self, task: "TaskRecord | str") -> TaskRunContext:
        """Contexto do run desta task, criado sob demanda (0.4.74).

        Criar sob demanda é de propósito: o heartbeat do loop bate de uma thread
        e o `status` de outro processo — nenhum dos dois pode depender de o
        contexto já existir, e um contexto vazio é resposta honesta ("ainda não
        começou" / "já terminou").
        """
        task_id = task if isinstance(task, str) else task.id
        ctx = self._contexts.get(task_id)
        if ctx is None:
            ctx = TaskRunContext()
            self._contexts[task_id] = ctx
        return ctx

    def _cancel_stale_received(self) -> int:
        """Auto-cancel RECEIVED tasks older than stale_received_ttl_hours (P1-D 0.4.16)."""
        ttl_hours = self.config.limits.stale_received_ttl_hours
        if not ttl_hours:
            return 0
        cutoff_s = ttl_hours * 3600
        now = datetime.now(timezone.utc)
        cancelled = 0
        for task in self.repo.list_tasks(limit=200):
            if task.status != TaskState.RECEIVED:
                continue
            try:
                ts = task.created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                # Roundtrip pelo SQLite perde o tzinfo ("...+00:00" vira
                # string naïve); subtrair de `now` (aware) levantava TypeError
                # e o except engolia — a varredura nunca cancelava NADA lido
                # do DB. Assumir UTC quando naïve.
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                age_s = (now - dt).total_seconds()
            except Exception:
                continue
            if age_s > cutoff_s:
                self.repo.transition(
                    task,
                    TaskState.CANCELLED,
                    reason=f"auto-cancel: stale RECEIVED > {ttl_hours}h",
                    agent="runtime",
                )
                cancelled += 1
        return cancelled

    def _last_progress_event(self, task_id: str) -> dict[str, Any] | None:
        """Último sinal de vida da task (heartbeat do loop ou do agente)."""
        try:
            return self.repo.last_event(
                task_id,
                types=(
                    EventType.LOOP_PROGRESS.value,
                    EventType.AGENT_PROGRESS.value,
                ),
            )
        except Exception:  # noqa: BLE001
            return None

    def _legacy_workspace_owner_alive(self) -> bool:
        """Sinal de vida ANTIGO: o pid gravado no write lock do workspace.

        Até a 0.4.73 o loop segurava esse lock durante toda a execução, então o
        lock era a prova de que alguém trabalhava. A 0.4.74 deixou de segurá-lo
        (segurar era a própria serialização do projeto), mas isto continua aqui
        como ponte: durante a atualização da frota há processos na 0.4.73 rodando
        tasks, e eles não emitem `loop_progress` com pid. Sem esta ponte, o reaper
        de um processo novo cancelaria a task viva de um processo velho.
        """
        try:
            data = json.loads(self.lock.lock_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return False
        return _pid_alive(int(data.get("pid") or 0))

    def _task_owner_alive(self, task_id: str) -> bool:
        """O processo que roda ESTA task ainda existe?

        0.4.74 — antes a pergunta era do WORKSPACE, respondida pelo pid do write
        lock, calculada UMA vez e aplicada a todas as tasks. Isso desmonta de duas
        formas com concorrência: o lock deixou de ser segurado pelo loop, e mesmo
        que fosse, o dono da task A não diz nada sobre o da task B.

        O pid por task vem do heartbeat do loop (0.4.73), cuja primeira batida sai
        no instante em que o loop começa — então task viva SEMPRE tem dono
        conhecido. Sem pid nenhum, cai no sinal legado do lock; sem os dois,
        ninguém está trabalhando nela.
        """
        evento = self._last_progress_event(task_id)
        pid = (evento or {}).get("data", {}).get("pid") if evento else None
        if isinstance(pid, int) and pid > 0:
            return _pid_alive(pid)
        return self._legacy_workspace_owner_alive()

    @staticmethod
    def _age_seconds(stamp: str | None, now: datetime) -> float | None:
        """Idade em segundos de um timestamp ISO do DB (naïve = UTC)."""
        if not stamp:
            return None
        try:
            dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except ValueError:
            return None
        if dt.tzinfo is None:  # roundtrip pelo SQLite perde o tzinfo
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt).total_seconds()

    def _idle_seconds(self, task: TaskRecord, now: datetime) -> float | None:
        """Há quanto tempo a task não dá SINAL DE VIDA.

        bug-096 — não é `updated_at`: esse só muda em transição de estado, e um
        executor legítimo passa 40 min em EXECUTING sem tocá-lo. O heartbeat de
        30s é EVENTO. Usar só `updated_at` fez o reaper registrar "parada há
        1643s" numa task do printbee (`25ea69c8324a`) que estava emitindo
        heartbeat até 87s antes — a decisão até acertou (o processo dono tinha
        morrido mesmo), mas pelo motivo errado e com a margem inteira apoiada no
        arquivo de lock. Lock apagado à mão viraria execução saudável cancelada.

        O sinal honesto é o mais RECENTE entre os dois.

        O heartbeat do LOOP (0.4.73) fica FORA de propósito: ele nasce de uma
        thread do processo dono e continuaria batendo com o loop travado num
        lock — contá-lo aqui trocaria a fila parada de 11h do bug-090 por uma
        eterna. Ele serve para o dono ver a fase, não para o reaper julgar.
        """
        ages = [self._age_seconds(task.updated_at, now)]
        try:
            ages.append(
                self._age_seconds(
                    self.repo.last_event_at(
                        task.id, exclude_types=(EventType.LOOP_PROGRESS.value,)
                    ),
                    now,
                )
            )
        except Exception:  # noqa: BLE001
            pass
        valid = [a for a in ages if a is not None]
        return min(valid) if valid else None

    def _emit_loop_progress(self, task_id: str, *, pid: int, elapsed_s: int) -> None:
        """Uma batida do heartbeat do loop: fase, idade da fase e quem está no ar."""
        fresh = self.get(task_id)
        fase_s = self._age_seconds(fresh.updated_at, datetime.now(timezone.utc))
        ctx = self._ctx(task_id)
        # 0.4.74 — os PIDs vivos são do executor DESTA task: com concorrência,
        # ler o compartilhado faria a task A relatar "agente no ar" por causa do
        # agente da task B. Antes de a task despachar o primeiro agente ela ainda
        # não tem executor — aí o compartilhado é a única fonte, e sem
        # concorrência ele é a fonte certa de qualquer forma.
        dono = ctx.executor
        if dono is None and not self._concurrency_on():
            dono = getattr(self, "executor", None)
        ativos = sorted(getattr(dono, "_active_pids", None) or ())
        role, agent = ctx.current_agent or (None, None)
        if ativos:
            quem = f"{agent}/{role}" if agent else "agente"
            onde = f"{quem} no ar (pid={ativos[0]})"
        elif agent:
            onde = f"entre etapas, nenhum agente no ar (última: {agent}/{role})"
        else:
            onde = "preparando a primeira etapa, nenhum agente no ar"
        evento = RuntimeEvent(
            task_id=task_id,
            type=EventType.LOOP_PROGRESS,
            role=role,
            agent=agent,
            data={
                "phase": fresh.status.value,
                "phase_elapsed_s": None if fase_s is None else int(fase_s),
                "elapsed_s": elapsed_s,
                "iteration": fresh.iteration,
                "pid": pid,
                "agent_active": bool(ativos),
                "summary": (
                    f"{fresh.status.value} há {int(fase_s or 0)}s — {onde}"
                ),
            },
        )
        self.bus.emit(evento)
        self.repo.add_event(evento)

    @contextmanager
    def _test_lock(self):
        """Rodada de testes exclusiva no projeto (0.4.74).

        Escopo disjunto separa código, não recurso de máquina: duas suítes no
        mesmo diretório disputam build dir, cache e porta, e a falha resultante
        não existe no código de nenhuma das duas — é a pior classe de falha,
        porque manda o corrector caçar defeito que não está lá.

        Se o lock de arquivo não vier na janela, roda mesmo assim e registra:
        suíte serializada é o objetivo, mas travar a task por causa do lock
        seria trocar um resultado sujo por nenhum resultado.
        """
        self._tests_gate.acquire()
        pegou = False
        try:
            try:
                self._tests_lock.acquire()
                pegou = True
            except TimeoutError:
                self.bus.emit(
                    RuntimeEvent(
                        task_id="-",
                        type=EventType.TEST_STARTED,
                        agent="runtime",
                        data={
                            "serialized": False,
                            "summary": (
                                "lock de testes não veio na janela — rodando sem "
                                "exclusividade; resultado pode sofrer interferência"
                            ),
                        },
                    )
                )
            try:
                yield
            finally:
                if pegou:
                    self._tests_lock.release()
        finally:
            self._tests_gate.release()

    @contextmanager
    def _loop_heartbeat(self, task: TaskRecord):
        """Sinal de vida do PRÓPRIO loop, inclusive onde nenhum agente roda.

        O `agent_progress` só existe enquanto um CLI está no ar. Consolidação,
        gravação de memória, gate de documentação, escolha de agentes e a troca
        de uma etapa para a seguinte não emitem nada — e quem olha o `status`
        nesses vãos vê a mesma linha por minutos, sem como distinguir fase
        legítima de processo morto. Foi o que fez printbee e trustsafe parecerem
        travados enquanto trabalhavam.

        Vem de uma THREAD daemon: se o processo dono morre, o sinal para junto.
        Por isso o reaper o ignora (ver `_idle_seconds`) — prova que o processo
        vive, não que o trabalho anda.
        """
        cadencia = max(
            LOOP_HEARTBEAT_MIN_S, int(self.caller_profile.heartbeat_s or 30)
        )
        parar = threading.Event()
        inicio = time.monotonic()
        pid = os.getpid()

        def _bater() -> None:
            # 0.4.74 — a PRIMEIRA batida sai na hora, não depois de uma cadência.
            # É ela que registra o pid dono da task, e o reaper depende disso para
            # distinguir "processo morreu" de "não sei quem é o dono". Esperar 20s
            # deixava uma janela em que uma task viva não tinha dono conhecido.
            primeira = True
            while primeira or not parar.wait(cadencia):
                primeira = False
                try:
                    self._emit_loop_progress(
                        task.id, pid=pid, elapsed_s=int(time.monotonic() - inicio)
                    )
                except Exception:  # noqa: BLE001
                    pass  # sinal de vida nunca derruba a task
                if parar.is_set():
                    return

        thread = threading.Thread(
            target=_bater, daemon=True, name=f"loop-hb-{task.id[:8]}"
        )
        thread.start()
        try:
            yield
        finally:
            parar.set()
            thread.join(timeout=2)

    def _live_note(self, task_id: str) -> dict[str, Any]:
        """"Está andando ou travou?" respondido no próprio `status` (0.4.73).

        Sem isto a resposta exigia ler `task logs` inteiro e conferir o PID à
        mão — foi o que a frota fez três vezes para concluir "não travou".
        """
        try:
            evento = self.repo.last_event(
                task_id,
                types=(
                    EventType.LOOP_PROGRESS.value,
                    EventType.AGENT_PROGRESS.value,
                ),
            )
        except Exception:  # noqa: BLE001
            return {}
        if not evento:
            return {}
        dados = evento.get("data") or {}
        idade = self._age_seconds(evento.get("timestamp"), datetime.now(timezone.utc))
        pid = dados.get("pid")
        vivo: bool | None = None
        if isinstance(pid, int):
            try:
                vivo = _pid_alive(pid)
            except Exception:  # noqa: BLE001
                vivo = None
        return {
            "live": {
                "signal": evento.get("type"),
                "signal_age_s": None if idade is None else int(idade),
                "phase": dados.get("phase"),
                "phase_elapsed_s": dados.get("phase_elapsed_s"),
                "agent_active": dados.get("agent_active"),
                "role": evento.get("role"),
                "agent": evento.get("agent"),
                "pid": pid,
                "pid_alive": vivo,
                "summary": dados.get("summary"),
            }
        }

    def _verdict_lost_note(self, task_id: str) -> str:
        """O que a task JÁ tinha conquistado quando o reaper a pegou (bug-105).

        No trustsafe a `529cc0476c4e` foi cancelada com o veredito na mão: o
        validator tinha respondido `accepted score=1.0` 40 min antes, e o
        resultado disse só "auto-cancel". O dono lê "cancelada" e refaz do zero
        um trabalho que já tinha sido aprovado.

        Não muda a decisão — sem processo vivo não dá para concluir a task com
        honestidade. Muda o que o dono sabe ao decidir se reexecuta.
        """
        try:
            last = self.repo.last_validation_round(task_id)
        except Exception:  # noqa: BLE001
            return ""
        if not last:
            return ""
        status = str(last.get("status") or "")
        if status not in {"approved", "accepted"}:
            return ""
        score = last.get("score")
        return (
            f" | ATENÇÃO: a última validação já havia APROVADO "
            f"(score={score}) — o trabalho existe, só não foi consolidado"
        )

    def _cancel_stale_execution(self) -> int:
        """Cancela task NÃO-TERMINAL que nenhum processo vivo está tocando.

        bug-090 — defesa em profundidade para o deadlock de pipe: mesmo com o
        `process.py` corrigido, qualquer morte fora do caminho feliz (processo
        MCP derrubado, máquina reiniciada, kill manual) deixava a task em
        EXECUTING/PLANNING para sempre. ``_busy_task_id`` continuava devolvendo
        ela e TODA task nova entrava em QUEUED atrás de uma que nunca
        terminaria — foi o que custou ~11h de fila parada no printbee.

        ``_cancel_stale_received`` cuida do RECEIVED; QUEUED fica de fora de
        propósito (esperar na fila é o trabalho dela — quem a destrava é o
        cancelamento de quem está na frente).
        """
        grace = int(self.config.limits.stale_execution_grace_s or 0)
        if grace <= 0:
            return 0
        now = datetime.now(timezone.utc)
        cancelled = 0
        for task in self.repo.list_tasks(limit=200):
            if task.status in TERMINAL_STATES:
                continue
            if task.status in (TaskState.RECEIVED, TaskState.QUEUED):
                continue
            if task.id in self._running_tasks:
                continue  # este processo está rodando: viva por definição
            # bug-096 — silêncio de VERDADE (nem transição nem heartbeat), não
            # apenas ausência de transição de estado.
            idle_s = self._idle_seconds(task, now)
            if idle_s is None or idle_s < grace:
                continue  # jovem demais para julgar (ou timestamp ilegível)
            total_s = self._age_seconds(task.created_at, now) or idle_s
            hard_limit = int(task.constraints.maximum_duration_seconds) + grace
            # bug-105 — `total_s` conta desde `created_at`, NÃO desde a entrada no
            # estado. Escrever "VALIDATING há 4525s" fez a mensagem afirmar tempo
            # de fase com o número da idade da task (trustsafe `529cc0476c4e`:
            # 4525s de vida, 2963s em VALIDATING). Terceira vez que uma mensagem
            # deste reaper aponta o relógio errado — dizer QUAL relógio é o
            # conserto que faltava.
            if total_s > hard_limit:
                reason = (
                    f"auto-cancel: em {task.status.value}, criada há "
                    f"{int(total_s)}s e sem sinal de vida há {int(idle_s)}s "
                    f"(> maximum_duration_seconds + {grace}s)"
                )
            elif not self._task_owner_alive(task.id):
                # 0.4.74 — a pergunta é por TASK, não pelo workspace.
                reason = (
                    f"auto-cancel: em {task.status.value} sem processo dono vivo "
                    f"e sem sinal de vida há {int(idle_s)}s"
                )
            else:
                continue
            reason += self._verdict_lost_note(task.id)
            self.repo.transition(
                task, TaskState.CANCELLED, reason=reason, agent="runtime", error=reason
            )
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_CANCELLED,
                    agent="runtime",
                    data={"reason": reason, "summary": "stale execution reaped"},
                )
            )
            cancelled += 1
            # Destravar quem estava enfileirado atrás dela.
            try:
                self._maybe_start_next(task.project_path)
            except Exception:  # noqa: BLE001
                pass
        return cancelled

    # bug-064 — janela de idempotencia do create_task: double-submit (MCP/CLI
    # chamando create 2x seguidas; medido: 16s de intervalo no corehub) gerava
    # tasks gêmeas e uma travava RECEIVED sem dono.
    _DEDUP_WINDOW_S = 120

    def _find_recent_duplicate(self, prompt: str, *, dry_run: bool) -> TaskRecord | None:
        """Task nao-terminal recente com o MESMO prompt e mesmo dry_run."""
        now = datetime.now(timezone.utc)
        for task in self.repo.list_tasks(limit=50):
            if task.status in TERMINAL_STATES:
                continue
            if task.prompt != prompt:
                continue
            if bool(getattr(task.constraints, "dry_run", False)) != dry_run:
                continue
            try:
                ts = task.created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:  # roundtrip SQLite perde o tz; assumir UTC
                    dt = dt.replace(tzinfo=timezone.utc)
                age_s = (now - dt).total_seconds()
            except Exception:  # noqa: BLE001
                continue
            if 0 <= age_s <= self._DEDUP_WINDOW_S:
                return task
        return None

    def create_task(
        self,
        prompt: str,
        *,
        profile: str = "balanced",
        max_iterations: int | None = None,
        timeout: int | None = None,
        planner: str | None = None,
        executor: str | None = None,
        validator: str | None = None,
        dry_run: bool = False,
        scope: list[str] | None = None,
    ) -> TaskRecord:
        # bug-049 — prompt vindo de terminal CP1252 chega com mojibake UTF-8
        # ("exigÃªncia"); repara na ingestão, antes de persistir/analisar.
        prompt = repair_mojibake(prompt)
        self._cancel_stale_received()
        self._cancel_stale_execution()
        # bug-113 - criar outra task tambem e um poll duravel no MCP. Antes a
        # cabeca QUEUED orfa so podia andar no finally de outro run_task.
        self._adopt_orphan_received_safe()
        # bug-064 — idempotencia: mesmo prompt + mesmo dry_run em janela curta
        # com task nao-terminal devolve a existente (auditada com evento dedup)
        # em vez de criar duplicata que pode travar RECEIVED sem dono.
        existing = self._find_recent_duplicate(prompt, dry_run=dry_run)
        if existing is not None:
            event = RuntimeEvent(
                task_id=existing.id,
                type=EventType.TASK_CREATED,
                agent="runtime",
                data={"dedup": True, "prompt": prompt[:200]},
            )
            self.bus.emit(event)
            self.repo.add_event(event)
            return existing
        constraints = TaskConstraints(
            maximum_iterations=max_iterations
            or self.config.limits.maximum_iterations,
            maximum_duration_seconds=timeout
            or self.config.limits.maximum_duration_seconds,
            profile=profile,
            planner=planner,
            executor=executor,
            validator=validator,
            dry_run=dry_run,
            scope=list(normalize_scope(scope)),
        )
        task = TaskRecord(
            prompt=prompt,
            project_path=str(self.config.project_path),
            constraints=constraints,
        )
        prior_count = len(self.repo.list_tasks(limit=2))
        first_run = prior_count == 0
        self.repo.create(task)
        event = RuntimeEvent(
            task_id=task.id,
            type=EventType.TASK_CREATED,
            data={
                "prompt": prompt[:200],
                "first_run": first_run,
            },
        )
        self.bus.emit(event)
        self.repo.add_event(event)
        if first_run:
            self._onboard_first_run(task)
        # bug-103 — task nascida com o workspace OCUPADO entra na FILA aqui, não
        # fica esperando em RECEIVED.
        #
        # `_enqueue_task` só acontecia dentro do `run_task`; quem cria por MCP
        # (`orchestrator_run`, wait=false) ou por `task create` nunca chama
        # `run_task`, então a task ficava RECEIVED — e RECEIVED está FORA de
        # `list_queued`, ou seja, o dequeue (corrigido no bug-098) nem olha para
        # ela. Sobrava a adoção de órfã: uma por vez, só com o workspace livre e
        # só se alguém fizesse poll.
        #
        # Medido no printbee: `edeee9684e66` ficou 9899s (2h45min) entre o
        # `task_created` e o primeiro estado; `2d933db18554` passou 2h47min com
        # UM único evento — nunca começou. Em QUEUED as duas teriam sido
        # puxadas em ordem pela cadeia de dequeue, sem depender de ninguém.
        try:
            busy = self._blocking_task_id(task.project_path, task)
            if busy:
                return self._enqueue_task(task, blocked_by=busy)
        except Exception:  # noqa: BLE001
            pass  # enfileirar é otimização; nunca impede a criação
        return task

    def _onboard_first_run(self, task: TaskRecord) -> None:
        """0.4.24 — primeiro run no projeto: probe de agentes + índice legacy-import."""
        probe: dict[str, Any] = {"agents": []}
        try:
            for st in self.registry.list_statuses():
                probe["agents"].append(
                    {
                        "id": st.id,
                        "available": bool(st.available),
                        "path": st.path,
                        "notes": (st.notes or "")[:160] if getattr(st, "notes", None) else None,
                    }
                )
        except Exception as exc:  # noqa: BLE001
            probe["error"] = str(exc)
        idx_path = self._write_legacy_import_index()
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.MEMORY_UPDATED,
                agent="runtime",
                data={
                    "summary": "first_run_onboarding",
                    "agent_probe": probe,
                    "legacy_import_index": str(idx_path) if idx_path else None,
                },
            )
        )

    def _write_legacy_import_index(self) -> Path | None:
        """Gera índice das skills/rules em legacy-import (requires-review)."""
        root = self.config.project_path / ".orchestrator"
        skills_root = root / "skills" / "legacy-import"
        rules_root = root / "rules" / "legacy-import"
        if not skills_root.is_dir() and not rules_root.is_dir():
            return None
        lines = [
            "# Legacy import index",
            "",
            "Gerado no primeiro `orchestrator_run` do projeto (0.4.23+).",
            "Status: requires-review — promover manualmente para paths ativos.",
            "",
            "## Skills",
            "",
        ]
        if skills_root.is_dir():
            for skill_md in sorted(skills_root.rglob("SKILL.md")):
                rel = skill_md.relative_to(root).as_posix()
                lines.append(f"- `{rel}`")
        else:
            lines.append("- _(nenhuma)_")
        lines += ["", "## Rules", ""]
        if rules_root.is_dir():
            for rule in sorted(rules_root.rglob("*")):
                if rule.is_file() and rule.name != "LEGACY-IMPORT.md":
                    lines.append(f"- `{rule.relative_to(root).as_posix()}`")
        else:
            lines.append("- _(nenhuma)_")
        out = root / "memory" / "legacy-import" / "INDEX.md"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    def get(self, task_id: str) -> TaskRecord:
        task = self.repo.get(task_id)
        if not task:
            raise TaskNotFoundError(task_id)
        return task

    def list_tasks(self, limit: int = 50) -> list[TaskRecord]:
        # bug-064 — zumbis RECEIVED so eram varridos no create_task; quem
        # observa por MCP (list/status) agora tambem dispara a limpeza.
        self._cancel_stale_received()
        self._cancel_stale_execution()
        # bug-085 — e adota a orfã: cancelar depois de 6h resolvia o zumbi mas
        # nunca o trabalho; quem observa tem processo vivo, entao pode rodar.
        self._adopt_orphan_received_safe()
        return self.repo.list_tasks(limit=limit)

    def _adopt_orphan_received_safe(self, project_path: str | None = None) -> None:
        """Adoção nunca derruba leitura: observar é read-only para o chamador."""
        path = project_path or str(self.config.project_path)
        # bug-119 - CLI de agente órfão é ceifado ANTES de qualquer adoção e fora
        # do `try` da adoção: o `return` que a adoção QUEUED faz não pode pular a
        # ceifa, e processo órfão consome recurso da máquina enquanto existe.
        self._reap_orphan_agents_safe(path)
        try:
            # QUEUED vem primeiro: e fila explicita e sua cabeca nao pode ser
            # furada por uma RECEIVED encontrada na varredura legada.
            if self._adopt_orphan_queued(path):
                return
            if self._busy_task_id(path) is None:
                self._adopt_orphan_received(path)
        except Exception:  # noqa: BLE001
            pass

    def cancel(self, task_id: str, reason: str = "cancel requested") -> TaskRecord:
        task = self.get(task_id)
        task.cancel_requested = True
        reason_text = (reason or "cancel requested").strip() or "cancel requested"
        if not task.error:
            task.error = reason_text
        elif reason_text not in str(task.error):
            task.error = f"{task.error} | cancel: {reason_text}"
        # Propaga o cancel para os CLIs filhos ainda vivos — sem isso o Codex
        # órfão segue rodando e segurando o workspace após o cancelamento.
        killed: list[int] = []
        try:
            killed = self.executor.kill_active()
        except Exception:  # noqa: BLE001
            killed = []
        if killed:
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_CANCELLED,
                    data={
                        "killed_pids": killed,
                        "summary": "child CLIs killed",
                        "reason": reason_text,
                    },
                )
            )
        if can_resume(task.status):
            started = task.status not in {
                TaskState.RECEIVED,
                TaskState.QUEUED,
            }
            self.repo.transition(
                task,
                TaskState.CANCELLED,
                reason=reason_text,
                agent="runtime",
                error=reason_text,
            )
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_CANCELLED,
                    data={"reason": reason_text},
                )
            )
            # Learn-then-compact também no cancelamento após execução (0.4.14).
            if started:
                self._persist_episode(task, success=False)
        else:
            self.repo.save(task)
        # bug-059: cancelar quem segurava (ou encabeçava) a fila precisa
        # destravar quem está atrás — sem isto o dequeue só acontecia quando
        # alguma outra run_task terminasse.
        try:
            self._maybe_start_next(task.project_path)
        except Exception:  # noqa: BLE001
            pass
        return task

    def _ensure_runnable(self, task: TaskRecord) -> TaskRecord:
        """Recarrega do DB; aborta se cancel/terminal (bug-022 hard-stop)."""
        fresh = self.get(task.id)
        if fresh.cancel_requested and fresh.status not in TERMINAL_STATES:
            self.cancel(fresh.id, reason=fresh.error or "cancel requested")
            raise CancelledError(f"task {fresh.id} cancelled")
        if fresh.status in TERMINAL_STATES:
            raise CancelledError(
                f"task {fresh.id} terminal ({fresh.status.value})"
            )
        return fresh

    def status(self, task_id: str) -> dict[str, Any]:
        # bug-064 — zumbis RECEIVED so eram varridos no create_task; o poll de
        # status (MCP) tambem dispara a limpeza, senao task orfã fica eterna.
        self._cancel_stale_received()
        self._cancel_stale_execution()
        task = self.get(task_id)
        # bug-085 — o poll de status é o evento mais frequente da frota; é ele
        # que tira a órfã do limbo quando o processo criador não voltou.
        self._adopt_orphan_received_safe(task.project_path)
        # A adocao pode ter iniciado a task em outra thread. Nao devolver o
        # snapshot anterior se ela ja saiu da fila.
        task = self.get(task_id)
        out: dict[str, Any] = {
            "id": task.id,
            "status": task.status.value,
            "iteration": task.iteration,
            "last_score": task.last_score,
            "plan": task.plan,
            "error": task.error,
            "documentation_review": task.documentation_review,
        }
        if task.status == TaskState.QUEUED:
            out["queue_position"] = self._queue_position(task.id, task.project_path)
            out["blocked_by"] = self._blocked_by_from_error(task.error)
        # 0.4.73 — "está andando ou travou?" sem ler o log inteiro.
        if task.status not in TERMINAL_STATES:
            out.update(self._live_note(task.id))
        out.update(self._independence_note(task.id))
        # bug-095 — falta de credencial só o dono resolve; tem que chegar ao chat
        # a cada poll, não ficar enterrada no `task logs`.
        out.update(self._auth_note(task.id))
        # bug-102 — plano cru não pode se passar por plano refinado.
        out.update(self._plan_note(task.id))
        # 0.4.68 — e o registro único: "esta task rodou inteira?" numa pergunta.
        degradacoes = self.degradations(task.id)
        if degradacoes:
            out["degradations"] = degradacoes
        return out

    def follow_events(
        self, task_id: str, after_id: int = 0, *, limit: int = 500
    ) -> dict[str, Any]:
        """Uma volta de acompanhamento: o que chegou de novo e se já terminou.

        0.4.75 — o `task watch` é um laço fino em cima disto. A lógica mora aqui
        porque é o que precisa de teste: o comando em si é `print` e `sleep`.

        Devolve `cursor` para a próxima volta, e `terminal` para o laço saber
        quando parar sem inventar heurística de "parece pronto".
        """
        task = self.get(task_id)
        # bug-113 - `task watch` permanece vivo tempo suficiente para hospedar
        # a thread existente ate a execucao terminar.
        self._adopt_orphan_received_safe(task.project_path)
        eventos = self.repo.list_events_since(task_id, after_id, limit=limit)
        task = self.get(task_id)
        saida: dict[str, Any] = {
            "task_id": task.id,
            "status": task.status.value,
            "iteration": task.iteration,
            "events": eventos,
            "cursor": eventos[-1]["id"] if eventos else int(after_id),
            "terminal": task.status in TERMINAL_STATES,
        }
        if not saida["terminal"]:
            saida.update(self._live_note(task_id))
        return saida

    def _mark_plan_not_refined(self, task: TaskRecord, *, agent: str, detail: str) -> None:
        """Grava que o plano ficou só com o determinístico (bug-102).

        O refino é advisory de propósito, mas o resultado precisa distinguir
        "plano refinado por um modelo" de "plano cru". Persistido em `analysis`
        para sobreviver ao processo — evento sozinho some do `status`.
        """
        try:
            fresh = self.get(task.id)
            analysis = dict(fresh.analysis or {})
            analysis["plan_refined"] = False
            analysis["plan_refine_failure"] = f"{agent}: {detail}"
            fresh.analysis = analysis
            self.repo.save(fresh)
            task.analysis = analysis
        except Exception:  # noqa: BLE001
            pass  # observabilidade nunca derruba a task
        event = RuntimeEvent(
            task_id=task.id,
            type=EventType.AGENT_COMPLETED,
            role="planner",
            agent=agent,
            data={
                "status": "failed",
                "plan_refined": False,
                "summary": (
                    f"plano NÃO refinado ({agent}: {detail}) — a task segue com o "
                    "plano determinístico"
                ),
            },
        )
        self.bus.emit(event)
        try:
            self.repo.add_event(event)
        except Exception:  # noqa: BLE001
            pass

    def _plan_note(self, task_id: str) -> dict[str, Any]:
        try:
            analysis = self.get(task_id).analysis or {}
        except Exception:  # noqa: BLE001
            return {}
        if analysis.get("plan_refined") is not False:
            return {}
        return {
            "plan_refined": False,
            "plan_warning": (
                "o plano NÃO foi refinado por um modelo — a task rodou com o "
                f"plano determinístico ({analysis.get('plan_refine_failure')})"
            ),
        }

    def degradations(self, task_id: str) -> list[dict[str, str]]:
        """Tudo que o runtime aceitou degradar, num lugar só (0.4.68).

        Três vezes seguidas o mesmo padrão apareceu nesta frota — validação sem
        veredito independente (bug-089), agente sem credencial (bug-095), plano
        não refinado (bug-102) — e cada vez virou um campo novo com formato
        próprio. A quarta seria um quarto campo solto.

        Aqui o registro é UM: `kind`, o que se perdeu, e o que o dono pode
        fazer. Os campos antigos continuam saindo no `status` — cliente que já
        os consome não quebra —, mas quem quiser saber "esta task rodou
        inteira?" agora tem uma pergunta só.

        A regra que os três casos ensinaram: **degradação aceita precisa
        aparecer no resultado**. O runtime decidir certo não basta.
        """
        registro: list[dict[str, str]] = []

        nota = self._independence_note(task_id)
        if nota.get("independent_validation") is False:
            registro.append(
                {
                    "kind": "validation_not_independent",
                    "impact": "o score não reflete revisão de mérito",
                    "detail": str(nota.get("validation_warning") or ""),
                    "action": str(
                        nota.get("action")
                        or "reexecute a validação com um validator vivo"
                    ),
                }
            )

        for bloqueio in self.auth_blockers(task_id):
            registro.append(
                {
                    "kind": "agent_auth_required",
                    "impact": f"{bloqueio['agent']} não pôde trabalhar",
                    "detail": f"CLI sem credencial (papel {bloqueio['role'] or '?'})",
                    "action": bloqueio["command"],
                }
            )

        for parada in self.service_outages(task_id):
            registro.append(
                {
                    "kind": "agent_service_down",
                    "impact": f"{parada['agent']} não pôde trabalhar",
                    "detail": (
                        f"o serviço do provedor respondeu erro (papel "
                        f"{parada['role'] or '?'})"
                    ),
                    "action": (
                        "nada a instalar nem logar — tente de novo mais tarde "
                        "ou troque o agente deste papel"
                    ),
                }
            )

        for falha in self.launch_failures(task_id):
            registro.append(
                {
                    "kind": "agent_launch_failed",
                    "impact": f"{falha['agent']} não pôde trabalhar",
                    "detail": (
                        f"o processo não chegou a iniciar (exit="
                        f"{falha['exit_code'] or '?'}, papel {falha['role'] or '?'})"
                        " — falta de recurso da máquina, não do CLI"
                    ),
                    "action": (
                        "libere memória/processos na máquina (ou reinicie) e "
                        "reexecute; não há o que instalar nem logar"
                    ),
                }
            )

        premissa = self._premise_note(task_id)
        if premissa:
            registro.append(
                {
                    "kind": "premise_declared_unverified",
                    "impact": (
                        "a task encerrou pela alegação do EXECUTOR, sem validator"
                    ),
                    "detail": (
                        "nada foi entregue: o executor declarou que a premissa da "
                        f"tarefa está incorreta — {premissa['premise_mismatch'][:200]}"
                    ),
                    "action": (
                        "confira a alegação; se a premissa estava certa, reexecute "
                        "com o contexto que falta"
                    ),
                }
            )

        plano = self._plan_note(task_id)
        if plano.get("plan_refined") is False:
            registro.append(
                {
                    "kind": "plan_not_refined",
                    "impact": "a task rodou com o plano determinístico, sem refino de modelo",
                    "detail": str(plano.get("plan_warning") or ""),
                    "action": "reexecute se o plano importava para o resultado",
                }
            )

        desvio = self.scope_violations(task_id)
        if desvio:
            registro.append(
                {
                    "kind": "scope_violation",
                    "impact": (
                        "a task escreveu fora do escopo que a admitiu para rodar "
                        "em paralelo"
                    ),
                    "detail": (
                        f"{len(desvio)} arquivo(s) fora de "
                        f"{', '.join(self.task_scope(self.get(task_id))) or '?'}: "
                        f"{', '.join(desvio[:10])}"
                    ),
                    "action": (
                        "confira se o trabalho é legítimo (escopo declarado curto) "
                        "ou se atropelou outra task; ajuste o --scope na reexecução"
                    ),
                }
            )
        return registro

    def scope_violations(self, task_id: str) -> list[str]:
        """Arquivos que a task tocou FORA do escopo declarado (0.4.74).

        É a metade de DETECÇÃO da garantia. Como o trabalho acontece todo na
        árvore local, o runtime impede duas tasks de escopos sobrepostos serem
        admitidas juntas, mas não impede o agente de escrever onde quiser depois
        de admitido. O desvio então tem que ser medido e contado — invisível ele
        transforma a admissão numa garantia de fachada.

        Base é o que a task REPORTOU ter mudado (`agent_runs.changed_files`), não
        o `git status`: com duas tasks na mesma árvore, o git não sabe de quem é
        cada arquivo.
        """
        escopo = self.task_scope(self.get(task_id))
        if not escopo:
            return []
        try:
            tocados = self.repo.changed_files_reported(task_id)
        except Exception:  # noqa: BLE001
            return []
        return outside_scope(tocados, escopo)

    def _prior_rejection(self, task_id: str) -> dict[str, Any] | None:
        """Última validação gravada, se ela REJEITOU (bug-107)."""
        try:
            last = self.repo.last_validation_round(task_id)
        except Exception:  # noqa: BLE001
            return None
        if not last:
            return None
        return last if str(last.get("status")) == "rejected" else None

    def _premise_note(self, task_id: str) -> dict[str, Any]:
        """Outcome declarado pelo executor, sem juiz (bug-107)."""
        try:
            analysis = self.get(task_id).analysis or {}
        except Exception:  # noqa: BLE001
            return {}
        alegacao = analysis.get("premise_mismatch")
        if not alegacao or analysis.get("premise_verified"):
            return {}
        return {"premise_mismatch": str(alegacao)}

    def _repair_events_by_kind(self, task_id: str, kind: str) -> list[dict[str, str]]:
        """Agentes que pararam por `failure_kind`, deduplicados por agente.

        Mesma forma de `auth_blockers`, categorias diferentes — e é a diferença
        que importa: `auth` tem comando para digitar, `service` e `launch` não
        têm nada. Misturar mandaria fazer login num CLI autenticado ou
        reinstalar um CLI intacto, que foi exatamente o que a 0.4.63 fez.
        """
        try:
            events = self.repo.list_events(task_id)
        except Exception:  # noqa: BLE001
            return []  # observabilidade nunca derruba quem chamou
        paradas: dict[str, dict[str, str]] = {}
        for event in events:
            if event.get("type") != EventType.AGENT_REPAIR.value:
                continue
            data = event.get("data") or {}
            if data.get("failure_kind") != kind:
                continue
            agente = str(event.get("agent") or "?")
            paradas[agente] = {
                "agent": agente,
                "role": str(event.get("role") or ""),
                "exit_code": str(data.get("exit_code") or ""),
            }
        return list(paradas.values())

    def service_outages(self, task_id: str) -> list[dict[str, str]]:
        """Agentes que pararam porque o serviço do provedor caiu (bug-106)."""
        return self._repair_events_by_kind(task_id, "service")

    def launch_failures(self, task_id: str) -> list[dict[str, str]]:
        """Agentes cujo processo não chegou a nascer (bug-109)."""
        return self._repair_events_by_kind(task_id, "launch")

    def auth_blockers(self, task_id: str) -> list[dict[str, str]]:
        """Agentes que pararam por falta de credencial, prontos para o chat.

        bug-095 — o evento `agent_repair` já registrava isso, mas evento mora no
        `task logs`, e quem precisa agir é o DONO, que está olhando o chat. Sem
        credencial nenhum reparo automático resolve: reinstalar apaga a sessão e
        só a pessoa pode fazer login. Ficava invisível: na primeira execução real
        da 0.4.63 o `codex` caiu por `auth` duas vezes e o resultado da task não
        dizia uma palavra sobre isso.

        Deduplicado por agente — o mesmo CLI falha em vários papéis e o dono só
        precisa rodar o comando uma vez.
        """
        try:
            events = self.repo.list_events(task_id)
        except Exception:  # noqa: BLE001
            return []  # observabilidade nunca derruba quem chamou
        blockers: dict[str, dict[str, str]] = {}
        for event in events:
            if event.get("type") != EventType.AGENT_REPAIR.value:
                continue
            data = event.get("data") or {}
            if data.get("failure_kind") != "auth":
                continue
            agent = str(event.get("agent") or "?")
            blockers[agent] = {
                "agent": agent,
                "role": str(event.get("role") or ""),
                "command": str(data.get("auth_command") or auth_hint(agent)),
            }
        return list(blockers.values())

    @staticmethod
    def auth_action_text(blockers: list[dict[str, str]]) -> str:
        """Uma linha acionável — o que o dono tem que digitar."""
        alvos = "; ".join(f"{b['agent']} → {b['command']}" for b in blockers)
        return (
            f"AÇÃO DO DONO: agente(s) sem credencial. Reinstalar não resolve — "
            f"faça login: {alvos}"
        )

    def _auth_note(self, task_id: str) -> dict[str, Any]:
        blockers = self.auth_blockers(task_id)
        if not blockers:
            return {}
        return {
            "agent_auth_required": blockers,
            "action_required": self.auth_action_text(blockers),
        }

    # bug-089 — score 1.0 com validator morto lia-se como "revisado e aprovado".
    # Na task 143e8b2ca47b os DOIS validators (codex e opencode) sairam exit=1
    # com zero byte; a política manda não transformar falha de infra em
    # rejeição de mérito — correto — mas então o resultado tem que DIZER que
    # ninguém revisou. Só reporta; não muda gate nem score.
    def _independence_note(self, task_id: str) -> dict[str, Any]:
        try:
            last = self.repo.last_validation_round(task_id)
        except Exception:  # noqa: BLE001
            return {}
        if not last:
            return {}
        payload = last.get("payload") or {}
        if not payload.get("validator_infra_failure"):
            return {"independent_validation": True}
        if payload.get("validation_skipped") == "budget":
            # bug-104 — mesma degradação, remédio oposto: aqui nenhum agente
            # falhou, faltou relógio. Mandar "reexecute com um validator vivo"
            # manda o dono caçar um defeito que não existe.
            return {
                "independent_validation": False,
                "validation_warning": (
                    "o validator NÃO chegou a rodar — o orçamento da task "
                    "acabou antes. O score é só o determinístico e NÃO reflete "
                    "revisão de mérito."
                ),
                "action": (
                    "aumente maximum_duration_seconds em "
                    ".orchestrator/config/policies.json ou reduza o escopo"
                ),
            }
        return {
            "independent_validation": False,
            "validation_warning": (
                "aprovado só pela validação determinística — nenhum validator "
                "independente respondeu (falha de infra). O score NÃO reflete "
                "revisão de mérito."
            ),
            "action": "reexecute a validação com um validator vivo",
        }

    @staticmethod
    def _blocked_by_from_error(error: str | None) -> str | None:
        if not error:
            return None
        m = re.match(r"queued_behind:([^|\s]+)", error)
        return m.group(1) if m else None

    def _queue_position(self, task_id: str, project_path: str) -> int:
        for i, t in enumerate(self.repo.list_queued(project_path), start=1):
            if t.id == task_id:
                return i
        return len(self.repo.list_queued(project_path)) + 1

    def task_scope(self, task: TaskRecord) -> tuple[str, ...]:
        """Escopo de arquivos efetivo da task (0.4.74).

        O do DONO (`--scope`) vence o do planner: quem conhece o projeto é quem
        pede, e o planner erra o escopo com frequência suficiente para não ter a
        palavra final. Vazio nos dois = DESCONHECIDO, e desconhecido serializa.
        """
        do_dono = normalize_scope(getattr(task.constraints, "scope", None))
        if do_dono:
            return do_dono
        analise = task.analysis if isinstance(task.analysis, dict) else {}
        return normalize_scope(analise.get("scope"))

    def _active_tasks(self, project_path: str, exclude_id: str | None) -> list[TaskRecord]:
        """Tasks executando no projeto, do DB e deste processo, sem repetir."""
        ativas: dict[str, TaskRecord] = {}
        for t in self.repo.list_active_executions(project_path):
            if t.id != exclude_id:
                ativas[t.id] = t
        for rid in list(self._running_tasks):
            if rid == exclude_id or rid in ativas:
                continue
            other = self.repo.get(rid)
            # bug-059: coroutine zumbi (presa no pré-loop) mantém a task em
            # _running_tasks mesmo depois de CANCELLED no DB — a fila inteira
            # ficava QUEUED "behind <task cancelada>". Terminal nunca ocupa.
            if (
                other
                and other.project_path == project_path
                and other.status not in TERMINAL_STATES
            ):
                ativas[rid] = other
        return list(ativas.values())

    def _blocking_task_id(
        self, project_path: str, task: TaskRecord | None = None, *, exclude_id: str | None = None
    ) -> str | None:
        """Id da task que impede esta de começar agora, ou None se pode entrar.

        0.4.74 — duas barreiras, nesta ordem:

        1. **Teto** (`max_parallel_tasks`). Protege a máquina: cada task gasta ~6
           invocações de CLI, e foi exaustão de recurso que produziu o
           `0xC0000142` do bug-109.
        2. **Escopo**. Mesmo abaixo do teto, só entra quem for comprovadamente
           disjunto de TODAS as ativas. Escopo desconhecido sobrepõe tudo, então
           task sem escopo declarado continua serializando como na 0.4.73.

        Sem `task` (chamadas de "o workspace está livre?") a pergunta é só sobre
        haver alguém ativo — é o comportamento antigo e os chamadores dependem
        dele.
        """
        alvo_id = exclude_id if task is None else task.id
        ativas = self._active_tasks(project_path, alvo_id)
        if not ativas:
            return None
        if task is None:
            return ativas[0].id

        teto = max(1, int(self.config.limits.max_parallel_tasks or 1))
        if len(ativas) >= teto:
            return ativas[0].id

        meu = self.task_scope(task)
        for outra in ativas:
            if scopes_overlap(meu, self.task_scope(outra)):
                return outra.id
        return None

    def _busy_task_id(self, project_path: str, exclude_id: str | None = None) -> str | None:
        """Há alguém executando no projeto? (sem julgar escopo nem teto)"""
        return self._blocking_task_id(project_path, None, exclude_id=exclude_id)

    def _enqueue_task(self, task: TaskRecord, blocked_by: str) -> TaskRecord:
        """Coloca task na fila FIFO do workspace (estado QUEUED)."""
        task = self.get(task.id)
        if task.status in TERMINAL_LIKE:
            return task
        if task.status == TaskState.RECEIVED:
            self.repo.transition(
                task,
                TaskState.QUEUED,
                reason=f"workspace busy; behind {blocked_by}",
                agent="runtime",
            )
            task = self.get(task.id)
        elif task.status != TaskState.QUEUED:
            # Já saiu da fila / está em pipeline — não re-enfileirar.
            return task
        pos = self._queue_position(task.id, task.project_path)
        task.error = f"queued_behind:{blocked_by}|pos={pos}"
        self.repo.save(task)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.TASK_QUEUED,
                agent="runtime",
                data={
                    "to": TaskState.QUEUED.value,
                    "summary": f"QUEUED behind {blocked_by} pos={pos}",
                    "blocked_by": blocked_by,
                    "queue_position": pos,
                    "reason": "workspace_busy",
                },
            )
        )
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.STATE_CHANGED,
                data={
                    "to": TaskState.QUEUED.value,
                    "summary": f"QUEUED behind {blocked_by} pos={pos}",
                    "blocked_by": blocked_by,
                    "queue_position": pos,
                    "reason": "workspace_busy",
                },
            )
        )
        return task

    def _maybe_start_next(self, project_path: str) -> None:
        """Dequeue FIFO: puxa da fila tudo que couber agora.

        0.4.74 — antes puxava UMA e só se o workspace estivesse totalmente livre.
        Com teto > 1 a fila anda enquanto há vaga E escopo disjunto: a próxima
        pode estar bloqueada por sobreposição enquanto a seguinte entra
        tranquila, então a varredura não pára na primeira recusa — ela ignora
        quem não cabe e continua. Parar na primeira seria FIFO estrito e
        deixaria vaga ociosa por causa de uma task que não pode entrar.
        """
        queued = self.repo.list_queued(project_path)
        if not queued:
            if self._busy_task_id(project_path) is None:
                self._adopt_orphan_received(project_path)
            return

        # As admitidas nesta passada contam para o teto e para o escopo AQUI, em
        # memória: `transition` as deixa em RECEIVED, que não é estado ativo, e a
        # thread só entra em `_running_tasks` depois. Sem esta contagem local, um
        # laço com 5 na fila admitiria as 5 de uma vez e furaria o teto.
        ocupando = self._active_tasks(project_path, None)
        teto = max(1, int(self.config.limits.max_parallel_tasks or 1))
        for candidata in queued:
            if len(ocupando) >= teto:
                return
            atual = self.get(candidata.id)
            if atual.status != TaskState.QUEUED:
                continue
            meu = self.task_scope(atual)
            if any(scopes_overlap(meu, self.task_scope(o)) for o in ocupando):
                continue  # não cabe agora; a próxima da fila pode caber
            atual.error = None
            self.repo.save(atual)
            self.repo.transition(
                atual,
                TaskState.RECEIVED,
                reason="dequeued — há vaga e o escopo não colide",
                agent="runtime",
            )
            ocupando.append(self.get(atual.id))
            self._start_background(atual.id, name="dequeue")

    def _start_background(self, task_id: str, *, name: str) -> None:
        def _bg() -> None:
            try:
                asyncio.run(self.run_task(task_id))
            except Exception as exc:  # noqa: BLE001
                _log.exception("%s run_task %s failed: %s", name, task_id, exc)

        thread = threading.Thread(
            target=_bg, daemon=True, name=f"orch-{name}-{task_id[:8]}"
        )
        # bug-098 — a thread é daemon (o servidor MCP não pode ficar preso nela),
        # mas o CLI PRECISA esperá-la: quem sai do processo mata a thread junto.
        self._background_threads.append(thread)
        thread.start()

    def join_background(self, timeout_s: float | None = None) -> int:
        """Espera as tasks que ESTE processo tirou da fila. Devolve quantas.

        bug-098 — o dequeue roda em thread daemon, e quem o dispara é o
        ``finally`` do ``run_task``: no CLI, o processo sai no instante seguinte
        e leva a thread. A task já tinha sido transicionada de QUEUED para
        RECEIVED, então sai de ``list_queued`` e ninguém mais a enxerga pela
        fila — só a adoção de órfã, que depende de alguém fazer poll.

        Medido no printbee: `06d74af53ee0` terminou 17:35:53 e `a0a588e6937b`
        foi para RECEIVED no MESMO segundo; ficou 11,5 min parada até o dono
        cancelar. Em 07/08 a mesma coisa durou 47 HORAS.

        O servidor MCP segue vivo e não chama isto — só o CLI, que morreria.
        """
        pendentes = [t for t in self._background_threads if t.is_alive()]
        for thread in pendentes:
            thread.join(timeout=timeout_s)
        return len(pendentes)

    def _queued_orphan_head(
        self, project_path: str, after_s: int
    ) -> TaskRecord | None:
        """Return only the FIFO head when every adoption guard passes."""
        queued = self.repo.list_queued(project_path)
        if not queued:
            return None
        head = queued[0]
        if (
            head.cancel_requested
            or head.id in self._running_tasks
            or head.id in self._adopted
        ):
            return None
        age_s = self._age_seconds(head.updated_at, datetime.now(timezone.utc))
        if age_s is None or age_s < after_s:
            return None

        # Evidencia de orfandade: dono gravado terminou, OU nenhuma execucao
        # segue ativa. Bloqueador vivo vence mesmo quando o escopo e disjunto.
        active = self._active_tasks(project_path, head.id)
        blocked_by = self._blocked_by_from_error(head.error)
        blocker = self.repo.get(blocked_by) if blocked_by else None
        blocker_terminal = bool(blocker and blocker.status in TERMINAL_STATES)
        if active and not blocker_terminal:
            return None

        # Admissao normal continua soberana: teto e sobreposicao de escopo.
        if self._blocking_task_id(project_path, head) is not None:
            return None
        return head

    def _adopt_orphan_queued(self, project_path: str) -> bool:
        """Claim the orphaned QUEUED FIFO head with a persisted lease (bug-113).

        State remains QUEUED until the existing background path enters
        ``run_task``. Refreshing ``updated_at`` under a cross-process lock is a
        lease: another poll sees a recent head and cannot start it again. If the
        process dies before start, the same head becomes eligible after the
        configured window instead of disappearing from the queue.
        """
        after_s = self.config.limits.orphan_queued_adopt_after_s
        if after_s <= 0 or self._queued_orphan_head(project_path, after_s) is None:
            return False

        claimed: TaskRecord | None = None
        with self._queue_adoption_gate:
            with self._queue_adoption_lock:
                # Another poll may have claimed or dequeued between the cheap
                # read above and the lock. Re-read every guard under the lock.
                claimed = self._queued_orphan_head(project_path, after_s)
                if claimed is None:
                    return False
                self._adopted.add(claimed.id)
                self.repo.save(claimed)  # updates updated_at: persisted lease

        try:
            self._start_background(claimed.id, name="adopt-queued")
        except Exception:
            # Lease expires naturally; allow this process to retry afterwards.
            self._adopted.discard(claimed.id)
            raise

        event = RuntimeEvent(
            task_id=claimed.id,
            type=EventType.STATE_CHANGED,
            agent="runtime",
            data={
                "to": TaskState.QUEUED.value,
                "reason": "orphan_queued_adopted",
                "summary": "cabeca QUEUED sem dono adotada por poll do runtime",
            },
        )
        self.bus.emit(event)
        self.repo.add_event(event)
        return True

    def _register_process_tracking(
        self, executor: Any, task_id: str, *, role: str, agent: str
    ) -> None:
        """Liga o registro DURÁVEL dos CLIs que este executor lançar (bug-119).

        O único rastreador que existia era `CliExecutor._active_pids` — um set em
        memória, lido só por `kill_active()` no cancelamento ordenado. Ele cobre
        exatamente o caso em que o runtime ainda está vivo; órfão é o caso em que
        ele já não está. A linha em `agent_processes` sobrevive ao crash, ao
        `taskkill` e ao fim do terminal, e carrega a identidade lida do S.O.
        (`image` + `create_time`) sem a qual nenhum kill é autorizado.
        """
        if executor is None:
            return
        registros: dict[int, int] = {}

        def _on_launch(pid: int, image: str | None, create_time: float | None) -> None:
            try:
                row_id = self.repo.add_agent_process(
                    task_id=task_id,
                    project_path=str(self.config.project_path),
                    role=role,
                    agent=agent,
                    pid=int(pid),
                    image=image,
                    create_time=create_time,
                    owner_pid=os.getpid(),
                    started_at=datetime.now(timezone.utc).isoformat(),
                )
                registros[int(pid)] = row_id
            except Exception:  # noqa: BLE001
                pass  # registro nunca derruba a execução

        def _on_exit(pid: int) -> None:
            row_id = registros.pop(int(pid), None)
            if row_id is None:
                return
            try:
                self.repo.finish_agent_process(
                    row_id, datetime.now(timezone.utc).isoformat()
                )
            except Exception:  # noqa: BLE001
                pass

        try:
            executor.on_launch = _on_launch
            executor.on_exit = _on_exit
        except Exception:  # noqa: BLE001
            pass

    def _reap_orphan_agents_safe(self, project_path: str) -> None:
        """Ceifar nunca derruba leitura: observar é read-only para o chamador."""
        try:
            self._reap_orphan_agents(project_path)
        except Exception:  # noqa: BLE001
            pass

    def _agent_process_orphan(self, linha: dict[str, Any]) -> bool:
        """Evidência de orfandade: dono morto OU task já em estado terminal.

        As duas são suficientes sozinhas e por motivos diferentes. Dono morto
        significa que ninguém mais lê a saída daquele CLI nem o mataria no
        cancelamento — é órfão mesmo com a task em EXECUTING (aliás, é
        exatamente assim que ela ficaria presa lá). Task terminal significa que o
        trabalho acabou: qualquer CLI ainda vivo dela é sobra.
        """
        if not _pid_alive(int(linha.get("owner_pid") or 0)):
            return True
        task = self.repo.get(str(linha.get("task_id") or ""))
        return bool(task and task.status in TERMINAL_STATES)

    def _reap_orphan_agents(self, project_path: str) -> list[int]:
        """Mata os CLIs de agente que sobraram. Devolve os PIDs ceifados (bug-119).

        Acionada pelos pontos de poll que já existiam (`status`, `list_tasks`,
        `follow_events`, `create_task`), como a adoção de task órfã do bug-085 e
        do bug-113: sem daemon, sem processo novo, sem thread de poll periódico.

        Só é ceifado o que satisfaz TUDO junto:

        1. o PID foi registrado por nós ao lançar o agente (a linha existe);
        2. a identidade ATUAL do PID confere com a registrada — nome da imagem
           E instante de criação, lidos do S.O.;
        3. a task dona está terminal OU o processo do runtime que o lançou
           morreu;
        4. passou `orphan_agent_reap_after_s` desde o lançamento.

        O item 2 é o que separa ceifa de estrago. O Windows recicla PID: matar
        por número mataria o programa alheio que herdou o número. Sem identidade
        conferida — inclusive quando não dá para lê-la — ninguém morre.
        """
        after_s = int(self.config.limits.orphan_agent_reap_after_s or 0)
        if after_s < 0:
            return []
        abertos = self.repo.list_agent_processes(project_path, only_open=True)
        if not abertos:
            return []

        agora = datetime.now(timezone.utc)
        candidatos: list[dict[str, Any]] = []
        for linha in abertos:
            idade = self._age_seconds(linha.get("started_at"), agora)
            if idade is None or idade < after_s:
                continue
            pid = int(linha.get("pid") or 0)
            atual = process_identity(pid)
            if atual is None:
                # Sem identidade legível não se mata. Se o PID nem existe mais,
                # o registro cumpriu o papel dele e é fechado; se existe mas não
                # se deixa ler, a linha fica aberta para o próximo poll.
                if not _pid_alive(pid):
                    self.repo.finish_agent_process(linha["id"], agora.isoformat())
                continue
            if not identity_matches(linha.get("image"), linha.get("create_time"), atual):
                # PID reciclado por outro programa. O nosso processo já morreu —
                # fecha o registro — e o intruso NÃO é tocado.
                self.repo.finish_agent_process(linha["id"], agora.isoformat())
                continue
            if not self._agent_process_orphan(linha):
                continue
            candidatos.append(linha)

        if not candidatos:
            return []

        # A reivindicação é o ponto de idempotência entre pollers concorrentes:
        # quem grava `reaped_at` mata; quem chegou depois não vê mais a linha.
        ceifados: list[int] = []
        with self._reap_gate:
            try:
                self._reap_lock.acquire()
            except TimeoutError:
                return []  # outro processo está ceifando agora
            try:
                for linha in candidatos:
                    if not self.repo.claim_agent_process(
                        linha["id"], datetime.now(timezone.utc).isoformat()
                    ):
                        continue
                    pid = int(linha["pid"])
                    CliExecutor._kill_tree(pid)
                    ceifados.append(pid)
                    self._emit_reaped(linha)
            finally:
                self._reap_lock.release()
        return ceifados

    def _emit_reaped(self, linha: dict[str, Any]) -> None:
        evento = RuntimeEvent(
            task_id=str(linha.get("task_id") or ""),
            type=EventType.AGENT_COMPLETED,
            role=linha.get("role"),
            agent=linha.get("agent"),
            data={
                "status": "reaped_orphan",
                "pid": linha.get("pid"),
                "image": linha.get("image"),
                "owner_pid": linha.get("owner_pid"),
                "summary": (
                    "CLI de agente orfao ceifado: identidade conferida "
                    "(imagem + instante de criacao) e sem dono vivo"
                ),
            },
        )
        try:
            self.bus.emit(evento)
            self.repo.add_event(evento)
        except Exception:  # noqa: BLE001
            pass  # registro nunca derruba o poll

    def _adopt_orphan_received(self, project_path: str) -> None:
        """Assume task RECEIVED que ficou sem dono (bug-085).

        ``_maybe_start_next`` só olhava a fila QUEUED. Task criada por um
        processo que morreu antes de rodar o loop — cliente MCP recém-instalado
        que ainda não recarregou, CLI interrompido no meio do create — ficava
        em RECEIVED até o auto-cancel de 6h. Medido na trustsafe
        (c4b7a1d12d6b): criada 23:02, primeiro agente só 23:33, e nenhuma outra
        task ocupava o workspace — 30 min de fila parada sem motivo. Como
        `status`/`list` também chamam isto, qualquer poll adota a órfã.

        A janela ``orphan_received_adopt_after_s`` evita roubar a task de quem
        acabou de criá-la e vai chamar ``run_task`` em seguida.
        """
        after_s = self.config.limits.orphan_received_adopt_after_s
        if after_s <= 0:
            return
        now = datetime.now(timezone.utc)
        candidates: list[tuple[float, TaskRecord]] = []
        for task in self.repo.list_tasks(limit=100):
            if task.status != TaskState.RECEIVED:
                continue
            if task.project_path != project_path:
                continue
            if task.id in self._running_tasks or task.id in self._adopted:
                continue
            if task.cancel_requested:
                continue
            try:
                ts = task.created_at.replace("Z", "+00:00")
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:  # roundtrip SQLite perde o tz
                    dt = dt.replace(tzinfo=timezone.utc)
                age_s = (now - dt).total_seconds()
            except Exception:  # noqa: BLE001
                continue
            if age_s >= after_s:
                candidates.append((age_s, task))
        if not candidates:
            return
        # FIFO: a mais velha primeiro, como no dequeue.
        oldest = max(candidates, key=lambda pair: pair[0])[1]
        self._adopted.add(oldest.id)
        self.bus.emit(
            RuntimeEvent(
                task_id=oldest.id,
                type=EventType.STATE_CHANGED,
                agent="runtime",
                data={
                    "to": TaskState.RECEIVED.value,
                    "reason": "orphan_adopted",
                    "summary": (
                        "task RECEIVED sem dono adotada pelo runtime "
                        "(processo criador não rodou o loop)"
                    ),
                },
            )
        )
        self._start_background(oldest.id, name="adopt")

    def logs(self, task_id: str) -> list[dict[str, Any]]:
        self.get(task_id)
        return self.repo.list_events(task_id)

    def artifacts(self, task_id: str) -> list[dict[str, Any]]:
        self.get(task_id)
        return self.repo.list_artifacts(task_id)

    async def run_task(self, task_id: str) -> TaskRecord:
        task = self.get(task_id)
        if task.status == TaskState.CANCELLED:
            return task
        if task.status in {TaskState.COMPLETED, TaskState.FAILED, TaskState.INCOMPLETE}:
            return task
        if task_id in self._running_tasks:
            # Segunda invocação (MCP retry / poll) enquanto o loop já roda —
            # não contender o WriteLock nem marcar FAILED.
            return task
        if task.constraints.dry_run:
            return await self._dry_run(task)

        # 0.4.19 — não compete pelo workspace: enfileira.
        # 0.4.74 — "ocupado" deixou de ser "existe alguém rodando" e passou a ser
        # "não há vaga no teto OU o escopo colide com quem está rodando".
        busy = self._blocking_task_id(task.project_path, task)
        if busy:
            return self._enqueue_task(task, blocked_by=busy)
        if task.status == TaskState.QUEUED:
            # Dequeued (RECEIVED) ou liberou — segue; se ainda QUEUED e livre,
            # promove para RECEIVED antes do loop.
            task = self.get(task_id)
            if task.status == TaskState.QUEUED:
                task.error = None
                self.repo.save(task)
                self.repo.transition(
                    task,
                    TaskState.RECEIVED,
                    reason="workspace free — leaving queue",
                    agent="runtime",
                )
                task = self.get(task_id)

        project_path = task.project_path
        entrou = False
        result = task
        try:
            # 0.4.74 — o loop NÃO segura mais o write lock do workspace.
            # Segurá-lo por 25-40 min era a própria serialização do projeto: a
            # exclusão mútua agora é a admissão (teto + escopo disjunto), feita
            # antes de chegar aqui e válida entre processos porque olha o DB. O
            # lock passou a cobrir só o `TESTING`, onde duas suítes no mesmo
            # diretório se atrapalham de verdade (ver `_test_lock`).
            entrou = True
            self._running_tasks.add(task_id)
            try:
                # 0.4.73 — sinal de vida do loop cobre TODA a execução,
                # inclusive os vãos sem agente no ar.
                with self._loop_heartbeat(task):
                    result = await self._execute_loop(task)
            except CancelledError:
                result = self.get(task_id)
            finally:
                self._running_tasks.discard(task_id)
                # 0.4.74 — o contexto morre com o run. Um processo MCP de
                # vida longa acumularia baseline git de toda task já vista.
                self._contexts.pop(task_id, None)
            return result
        except CancelledError:
            return self.get(task_id)
        except TimeoutError as exc:
            # Lock de testes ocupado tempo demais: fila explícita QUEUED em vez
            # de FAILED. Antes era o lock do workspace inteiro.
            #
            # `entrou = False` importa: quem acabou de ser enfileirado não pode
            # disparar o próprio dequeue no `finally`. Até a 0.4.73 isso era
            # acidente do `held_lock` (a exceção vinha ANTES de ele virar True);
            # agora é explícito, senão a task volta da fila na mesma hora, bate no
            # mesmo timeout e gira para sempre.
            entrou = False
            task = self.get(task_id)
            blocked = (
                self._busy_task_id(project_path, exclude_id=task_id) or "unknown"
            )
            _log.debug("enqueue %s behind %s (%s)", task_id, blocked, exc)
            return self._enqueue_task(task, blocked_by=blocked)
        except Exception as exc:  # noqa: BLE001
            task = self.get(task_id)
            if can_resume(task.status):
                self.repo.transition(
                    task,
                    TaskState.FAILED,
                    reason="unhandled error",
                    error=str(exc),
                )
            else:
                task.error = str(exc)
                self.repo.save(task)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_FAILED,
                    data={"error": str(exc)},
                )
            )
            self._persist_episode(task, success=False)
            raise
        finally:
            # Só dequeue se realmente rodamos o loop (não no caminho QUEUED).
            if entrou:
                self._maybe_start_next(project_path)

    async def resume(self, task_id: str) -> TaskRecord:
        task = self.get(task_id)
        if not can_resume(task.status):
            return task
        return await self.run_task(task_id)

    async def run_prompt(self, prompt: str, **kwargs: Any) -> TaskRecord:
        task = self.create_task(prompt, **kwargs)
        return await self.run_task(task.id)

    async def _dry_run(self, task: TaskRecord) -> TaskRecord:
        analysis = await self.manager.analyze_task(task.prompt)
        plan_roles = await self.manager.select_strategy(task, analysis)
        _a = analysis.model_dump()
        _a["caller"] = self.caller
        task.analysis = _a
        task.plan = self.planner.plan(task, analysis, plan_roles)
        task.acceptance_criteria = analysis.acceptance_criteria
        self.repo.save(task)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.PLAN_CREATED,
                data={"dry_run": True, "plan": task.plan},
            )
        )
        return task

    async def _execute_loop(self, task: TaskRecord) -> TaskRecord:
        # bug-059: cancel chegando durante o pré-loop (baseline git etc.) tem
        # que abortar AQUI — o objeto task recebido é snapshot e o check
        # antigo de cancel_requested só rodava depois do primeiro transition.
        task = self._ensure_runnable(self.get(task.id))
        # 0.4.74 — contexto NOVO desta task. Antes estes quatro eram atributos do
        # serviço, então esta linha zerava o run de qualquer task concorrente.
        self._contexts[task.id] = TaskRunContext(
            started_monotonic=time.monotonic(),
            git_baseline=capture_baseline(self.config.project_path),
        )

        # Toda entrada no loop começa em ANALYZING — inclusive o resume de uma
        # task ÓRFÃ, parada no meio do pipeline porque o processo dono morreu.
        #
        # bug-110: até a 0.4.75 só RECEIVED e WAITING_FOR_USER transicionavam
        # aqui. Retomar de VALIDATING pulava a re-entrada e batia adiante em
        # `VALIDATING -> RETRIEVING_MEMORY` (task e9803cf77a43 do printbee).
        # O motivo continua distinto por caso: quem lê `task logs` precisa
        # saber se foi início, resposta de usuário ou recuperação de órfã.
        if task.status == TaskState.RECEIVED:
            self.repo.transition(task, TaskState.ANALYZING, reason="start analysis")
        elif task.status == TaskState.WAITING_FOR_USER:
            self.repo.transition(
                task, TaskState.ANALYZING, reason="resume after user input"
            )
        elif task.status in MID_PIPELINE_STATES:
            self.repo.transition(
                task,
                TaskState.ANALYZING,
                reason=f"restart after orphan ({task.status.value})",
            )
        if task.error and (
            str(task.error).startswith("blocked_by_lock")
            or str(task.error).startswith("queued_behind:")
        ):
            task.error = None
            self.repo.save(task)

        if task.cancel_requested:
            return self.cancel(task.id, reason=task.error or "cancel requested")

        project_files = [p.name for p in self.config.project_path.iterdir()]
        analysis = await self.manager.analyze_task(task.prompt, project_files)
        task = self._ensure_runnable(task)
        task.task_type = analysis.task_type
        task.languages = analysis.languages
        task.risk = analysis.risk
        task.complexity = analysis.complexity
        task.requirements = analysis.requirements
        task.acceptance_criteria = analysis.acceptance_criteria
        # Preserva contexto de requires_input/resume — o re-analyze não pode
        # apagar a resposta do usuário nem o contador de perguntas.
        prior_analysis = task.analysis if isinstance(task.analysis, dict) else {}
        merged_analysis = analysis.model_dump()
        for key in (
            "user_message",
            "user_question",
            "user_options",
            "resume_instruction",
            "requires_input_count",
        ):
            if key in prior_analysis:
                merged_analysis[key] = prior_analysis[key]
        # 0.4.29 — origem da chamada fica registrada na task (relatorio/auditoria)
        merged_analysis["caller"] = self.caller
        task.analysis = merged_analysis
        self.repo.save(task)

        task = self._ensure_runnable(task)
        self.repo.transition(task, TaskState.RETRIEVING_MEMORY, reason="memory lookup")
        memories = self.repo.search_memories(task.prompt, limit=5)
        # 0.4.14 — aprendizados de tarefas anteriores (kind=learning) além dos episodes
        learnings = self.repo.search_memories(task.prompt, limit=3, kind="learning")
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.MEMORY_UPDATED,
                data={"retrieved": len(memories), "learnings": len(learnings)},
            )
        )

        task = self._ensure_runnable(task)
        # SKILL SELECTION (0.4.13): fast model picks installed skills before heavy models
        await self._select_skills(task)

        task = self._ensure_runnable(task)
        self.repo.transition(task, TaskState.PLANNING, reason="planning")
        plan_roles = await self.manager.select_strategy(task, analysis)
        task.plan = self.planner.plan(task, analysis, plan_roles)
        self._ctx(task).run_ctx["strategy"] = plan_roles.strategy
        self.repo.save(task)
        self.repo.add_routing_decision(task.id, plan_roles.strategy, plan_roles.model_dump())
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.PLAN_CREATED,
                data={"plan": task.plan},
            )
        )

        task = self._ensure_runnable(task)
        selecting_started = time.monotonic()
        self.repo.transition(task, TaskState.SELECTING_AGENTS, reason="select agents")
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.ROUTING_DECIDED,
                data=plan_roles.model_dump(),
            )
        )

        # Planner agent (Claude no MVP) — refina plano; falha nao aborta se dry artifacts ok
        try:
            selecting_elapsed = time.monotonic() - selecting_started
            if selecting_elapsed >= self.selecting_agents_cap_s:
                raise TimeoutError(
                    f"SELECTING_AGENTS excedeu {self.selecting_agents_cap_s}s "
                    f"(elapsed={selecting_elapsed:.0f}s)"
                )
            task = self._ensure_runnable(task)
            _tooling = self._required_tooling_block()
            _skills = self._skills_block(task)
            _learnings = self._learnings_block(learnings)
            _child = self._child_agent_restriction_block()
            plan_prompt = (
                f"{_child}\n"
                + (f"{_tooling}\n" if _tooling else "")
                + (f"{_skills}\n" if _skills else "")
                + (f"{_learnings}\n" if _learnings else "")
                + (
                    f"Refine o plano para: {task.prompt}\n"
                    f"Plano atual: {dumps(task.plan)}\n"
                    "Responda com passos objetivos sem abreviação. "
                    "NÃO delegue a subagentes — refine o plano sozinho."
                )
            )
            # O plano determinístico já existe; o refino é advisory.
            # 0.4.24: teto = min(PLANNER_REFINE_CAP, restante SELECTING_AGENTS_CAP).
            remaining_selecting = max(
                30,
                int(self.selecting_agents_cap_s - (time.monotonic() - selecting_started)),
            )
            refine_cap = min(self.PLANNER_REFINE_CAP_S, remaining_selecting)
            refino = await self._run_agent(
                plan_roles.planner,
                "planner",
                plan_prompt,
                task,
                timeout_cap_s=refine_cap,
            )
            # bug-102 — refino perdido tem que APARECER. Ele é advisory, então a
            # task segue com o plano determinístico e termina COMPLETED score
            # 1.0 — idêntica a uma que FOI refinada. No printbee 2 de 4 tasks
            # rodaram sem plano refinado e nada no resultado dizia isso.
            if refino is None or getattr(refino, "status", None) != "completed":
                self._mark_plan_not_refined(
                    task,
                    agent=plan_roles.planner,
                    detail=(
                        f"timeout em {refine_cap}s"
                        if getattr(refino, "timed_out", False)
                        else f"status={getattr(refino, 'status', 'sem resultado')}"
                    ),
                )
        except CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            self._mark_plan_not_refined(task, agent=plan_roles.planner, detail=str(exc))
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_COMPLETED,
                    role="planner",
                    agent=plan_roles.planner,
                    data={"status": "failed", "error": str(exc)},
                )
            )

        changed_files: list[str] = []
        last_validation: dict[str, Any] = {}
        last_test_results: list[dict[str, Any]] = []
        issue_counts: dict[str, int] = {}
        # 0.4.28 — continuação de plano incompleto (não é iteração de validação)
        continuations = 0
        continuation_note = ""

        while True:
            task = self._ensure_runnable(self.get(task.id))

            remaining = self._remaining_duration_s(task)
            if remaining < MIN_AGENT_TIMEOUT_S:
                self.repo.transition(
                    task,
                    TaskState.INCOMPLETE,
                    reason="maximum_duration_seconds",
                    error=(
                        f"Orçamento de tempo esgotado "
                        f"(restante={remaining}s < {MIN_AGENT_TIMEOUT_S}s)"
                    ),
                )
                self.bus.emit(
                    RuntimeEvent(task_id=task.id, type=EventType.TASK_INCOMPLETE)
                )
                self._persist_episode(task, success=False)
                return task

            if task.iteration >= task.constraints.maximum_iterations:
                self.repo.transition(
                    task,
                    TaskState.INCOMPLETE,
                    reason="maximum_iterations",
                )
                self.bus.emit(
                    RuntimeEvent(task_id=task.id, type=EventType.TASK_INCOMPLETE)
                )
                self._persist_episode(task, success=False)
                return task

            task.iteration += 1
            self.repo.save(task)

            task = self.get(task.id)
            if task.status == TaskState.SELECTING_AGENTS:
                self.repo.transition(
                    task,
                    TaskState.EXECUTING,
                    reason=f"start execute iter={task.iteration}",
                    agent=plan_roles.executor,
                )
            elif task.status == TaskState.CORRECTING:
                self.repo.transition(
                    task,
                    TaskState.EXECUTING,
                    reason=f"retry execute iter={task.iteration}",
                    agent=plan_roles.executor,
                )
            elif task.status != TaskState.EXECUTING:
                raise RuntimeError(f"Estado inesperado antes de executar: {task.status}")

            role = "corrector" if task.iteration > 1 else "executor"
            # bug-065 — baseline de testes ANTES de o executor tocar a árvore.
            # Suite já quebrada na entrada (corehub: restore NuGet falho no
            # CLI; printbee: suite da raiz quebrada — INCOMPLETE 1d63d2a5cb28)
            # era cobrada como "introduced" e a task estava condenada por
            # mérito alheio. Assinatura igual na iteração vira "preexisting".
            if task.iteration == 1 and "test_baseline" not in self._ctx(task).run_ctx:
                try:
                    with self._test_lock():
                        baseline = self.tests.run_all(self.config.project_path)
                    self._ctx(task).run_ctx["test_baseline"] = baseline
                    for br in baseline:
                        self.repo.add_test_run(
                            task_id=task.id,
                            **{
                                **br,
                                "discovery_source": f"baseline:{br.get('discovery_source')}",
                            },
                        )
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.TEST_COMPLETED,
                            data={
                                "phase": "baseline",
                                "results": [
                                    {"command": t["command"], "status": t["status"]}
                                    for t in baseline
                                ],
                            },
                        )
                    )
                except Exception as base_exc:  # noqa: BLE001
                    # Infra no baseline: segue sem ele (comportamento estrito
                    # de antes da 0.4.44) em vez de derrubar a task.
                    self._ctx(task).run_ctx["test_baseline_error"] = str(base_exc)
            exec_prompt = self._build_executor_prompt(
                task,
                last_validation,
                memories,
                test_results=last_test_results,
                learnings=learnings,
                continuation_note=continuation_note,
            )
            try:
                # 0.4.61 — fan-out só na PRIMEIRA passada: correção existe para
                # fechar issue específica do validator, e dividir isso entre
                # agentes cegos uns aos outros multiplica o conflito em vez do
                # trabalho. Desligado por padrão
                # (allow_parallel_workspace_writes).
                exec_result = None
                if role == "executor" and self._fanout_enabled():
                    specs = await self._decompose(task, plan_roles)
                    if specs:
                        exec_result = await self._run_fanout(
                            task, plan_roles, exec_prompt, specs
                        )
                if exec_result is None:
                    exec_result = await self._run_agent(
                        plan_roles.executor, role, exec_prompt, task
                    )
            except Exception as exec_exc:  # noqa: BLE001
                # Spawn/CLI falhou: não abortar o workflow — tratar como iteração
                # rejeitada para entrar em CORRECTING / fallback na próxima volta.
                task = self.get(task.id)
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=plan_roles.executor,
                        data={"status": "failed", "error": str(exec_exc)},
                    )
                )
                last_validation = {
                    "status": "rejected",
                    "score": 0.0,
                    "blocking_issues": [
                        {
                            "id": "EXEC-FAIL",
                            "severity": "blocking",
                            "description": f"Falha ao executar {role}/{plan_roles.executor}: {exec_exc}",
                        }
                    ],
                    "summary": f"executor failed: {exec_exc}",
                }
                decision = await self.manager.evaluate_iteration(
                    task, last_validation, task.iteration
                )
                self.repo.add_iteration(
                    task.id,
                    task.iteration,
                    0.0,
                    decision.action,
                    {"reason": decision.reason, "error": str(exec_exc)},
                )
                if decision.action in {"stop_incomplete", "fail"}:
                    target = (
                        TaskState.FAILED
                        if decision.action == "fail"
                        else TaskState.INCOMPLETE
                    )
                    self.repo.transition(task, target, reason=decision.reason, error=str(exec_exc))
                    self._persist_episode(task, success=False)
                    return task
                self.repo.transition(
                    task,
                    TaskState.CORRECTING,
                    reason=f"executor error → correct: {exec_exc}",
                    agent=plan_roles.executor,
                )
                continue

            task = self.get(task.id)
            if task.cancel_requested:
                return self.cancel(task.id)

            premise_mismatch = self._parse_premise_mismatch(exec_result.stdout)
            if premise_mismatch:
                # Outcome terminal honrado: não há mudança, teste ou documentação
                # a exigir quando a própria premissa da tarefa está incorreta.
                #
                # bug-107 — mas é o EXECUTOR declarando o próprio resultado, sem
                # validator nenhum, com `require_independent_validation` ligado
                # em toda a frota. Duas coisas estavam erradas aqui:
                #
                # 1. `last_score = 1.0` era FABRICADO. Ninguém validou nada, e
                #    esse número chega ao dono (`task status`, `orchestrator_result`)
                #    e entra em `strategy_performance` como sucesso perfeito. No
                #    printbee a tabela virou `19 runs / 19 successes / avg 0.997`
                #    num projeto com 4 CANCELLED e 1 FAILED.
                # 2. Depois de uma REJEIÇÃO gravada, honrar a alegação lavava o
                #    veredito: a `efeaee6fd306` fechou COMPLETED score=1.0 com
                #    `rejected score=0.1` e issues bloqueantes em disco.
                #
                # Agora: score fica NULO (o campo é nullable e só serve para
                # relatório — inventar 1.0 é pior que não ter), e alegação que
                # contradiz rejeição gravada NÃO fecha como sucesso.
                rejeicao = self._prior_rejection(task.id)
                analysis_d = dict(task.analysis or {})
                analysis_d["premise_mismatch"] = premise_mismatch
                analysis_d["premise_verified"] = False
                task.analysis = analysis_d
                task.last_score = None
                self.repo.save(task)
                if rejeicao:
                    motivo = (
                        f"executor alegou premissa incorreta DEPOIS de validação "
                        f"rejeitada (score={rejeicao.get('score')}): a alegação "
                        f"contradiz o veredito em disco e não fecha como sucesso "
                        f"— {premise_mismatch[:200]}"
                    )
                    self.repo.transition(
                        task,
                        TaskState.INCOMPLETE,
                        reason="premise_mismatch_after_rejection",
                        agent=plan_roles.executor,
                        error=motivo,
                    )
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.TASK_INCOMPLETE,
                            role=role,
                            agent=plan_roles.executor,
                            data={
                                "reason": "premise_mismatch_after_rejection",
                                "summary": motivo,
                            },
                        )
                    )
                    self._persist_episode(
                        task, success=False, strategy=plan_roles.strategy
                    )
                    self._export_memory_markdown(task)
                    return task
                self.repo.transition(
                    task,
                    TaskState.COMPLETED,
                    reason="premise_mismatch",
                    agent=plan_roles.executor,
                )
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.STATE_CHANGED,
                        role=role,
                        agent=plan_roles.executor,
                        data={
                            "to": TaskState.COMPLETED.value,
                            "reason": "premise_mismatch",
                            "summary": premise_mismatch[:200],
                        },
                    )
                )
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.TASK_COMPLETED,
                        data={"reason": "premise_mismatch"},
                    )
                )
                self._persist_episode(
                    task, success=True, strategy=plan_roles.strategy
                )
                self._export_memory_markdown(task)
                return task

            requires_input = (
                None
                if exec_result.changed_files
                else self._parse_requires_input(exec_result.stdout)
            )
            if requires_input:
                analysis_d = dict(task.analysis or {})
                count = int(analysis_d.get("requires_input_count") or 0) + 1
                analysis_d["requires_input_count"] = count
                analysis_d["user_question"] = requires_input["question"]
                analysis_d["user_options"] = requires_input["options"]
                task.analysis = analysis_d
                if count == 1:
                    # Pergunta estruturada pausa a task sem queimar a iteração.
                    task.iteration = max(0, task.iteration - 1)
                    self.repo.save(task)
                    self.repo.transition(
                        task,
                        TaskState.WAITING_FOR_USER,
                        reason="executor requires_input",
                        agent=plan_roles.executor,
                    )
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.STATE_CHANGED,
                            role=role,
                            agent=plan_roles.executor,
                            data={
                                "to": TaskState.WAITING_FOR_USER.value,
                                "summary": requires_input["question"][:200],
                            },
                        )
                    )
                    return task
                # Repetiu a pergunta após resposta do usuário: infra reject +
                # rotação de executor (não fica em loop de perguntas).
                self.repo.save(task)
                terminal, last_validation = await self._reject_iteration_infra(
                    task,
                    plan_roles,
                    issue_id="AGENT-REQUIRES-INPUT",
                    description=(
                        f"{role}/{plan_roles.executor} voltou a pedir decisão em "
                        f"vez de implementar: {requires_input['question'][:200]}"
                    ),
                    summary="executor asked instead of implementing",
                    error_text=(
                        "AGENT-REQUIRES-INPUT: executor repetiu pergunta após "
                        "resposta do usuário"
                    ),
                    issue_counts=issue_counts,
                )
                if terminal is not None:
                    return terminal
                continue

            spawn_failed = exec_result.exit_code == 127 or (
                exec_result.status == "failed"
                and "FileNotFoundError" in (exec_result.stderr or "")
            )
            # CLI "completou" mas não produziu nada (stdout vazio + nenhum arquivo
            # alterado, mesmo após fallback git). Sem este guard a iteração segue
            # para VALIDATING e vira rejeição falsa de AC workspace_changes.
            empty_output = (
                not spawn_failed
                and exec_result.status == "completed"
                and not (exec_result.stdout or "").strip()
                and not exec_result.changed_files
            )
            # bug-078 - CLI falhou (exit != 0) sem produzir NADA e a iteracao
            # seguia para validacao: task C (0.4.52) teve executor E corrector
            # codex morrendo exit 1 com changed=[] e o validador APROVOU 1.0
            # confundindo com o diff de outra task no mesmo arquivo -
            # fechamento falso com zero codigo entregue. failed + sem changed
            # (mesmo apos fallback git) e infra, nunca merito a validar.
            failed_no_output = (
                not spawn_failed
                and exec_result.status == "failed"
                and not exec_result.changed_files
            )
            if spawn_failed or empty_output or failed_no_output:
                if spawn_failed:
                    issue_id = "EXEC-SPAWN"
                    description = (
                        f"Falha ao iniciar CLI {plan_roles.executor}: "
                        f"{(exec_result.stderr or '')[:300]}"
                    )
                    summary = "executor spawn failed"
                    error_text = exec_result.stderr
                elif failed_no_output:
                    issue_id = "AGENT-FAILED-NO-OUTPUT"
                    description = (
                        f"{role}/{plan_roles.executor} falhou "
                        f"(exit={exec_result.exit_code}) sem alterar arquivos: "
                        f"{(exec_result.stderr or '')[:200]}"
                    )
                    summary = "agent failed without output"
                    error_text = (
                        f"AGENT-FAILED-NO-OUTPUT: {role}/{plan_roles.executor} "
                        f"exit={exec_result.exit_code} sem mudancas"
                    )
                else:
                    issue_id = "AGENT-EMPTY-OUTPUT"
                    description = (
                        f"{role}/{plan_roles.executor} terminou exit=0 sem stdout "
                        "e sem arquivos alterados (saída vazia do CLI)"
                    )
                    summary = "agent empty output"
                    error_text = (
                        f"AGENT-EMPTY-OUTPUT: {role}/{plan_roles.executor} "
                        "retornou saída vazia"
                    )
                terminal, last_validation = await self._reject_iteration_infra(
                    task,
                    plan_roles,
                    issue_id=issue_id,
                    description=description,
                    summary=summary,
                    error_text=error_text,
                    issue_counts=issue_counts,
                )
                if terminal is not None:
                    return terminal
                continue

            changed_files = list(
                dict.fromkeys(changed_files + exec_result.changed_files)
            )
            self._ctx(task).run_ctx["changed_files"] = changed_files

            # ---------------------------------------------------------------
            # 0.4.28 — plano incompleto: mandar CONTINUAR em vez de validar.
            # Agentes de CLI param no meio de planos longos ("concluí 1-3, quer
            # que eu siga?"). Sem isto o runtime tratava a parada como execução
            # terminada e ia validar trabalho pela metade.
            # ---------------------------------------------------------------
            plan_status = self._parse_plan_status(exec_result.stdout)
            plan_incomplete = self._is_plan_incomplete(plan_status, exec_result.stdout)
            if plan_incomplete and not exec_result.timed_out:
                if continuations < self.config.limits.max_plan_continuations:
                    continuations += 1
                    remaining = []
                    if isinstance(plan_status, dict):
                        remaining = [str(x) for x in (plan_status.get("remaining") or [])]
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.AGENT_COMPLETED,
                            role=role,
                            agent=plan_roles.executor,
                            data={
                                "status": "incomplete_plan",
                                "continuation": continuations,
                                "remaining": remaining[:10],
                                "summary": (
                                    f"plano incompleto — continuando "
                                    f"({continuations}/"
                                    f"{self.config.limits.max_plan_continuations})"
                                ),
                            },
                        )
                    )
                    continuation_note = self._continuation_note(
                        remaining, changed_files, continuations
                    )
                    # Continuar não é nova iteração de validação: devolve o
                    # contador que o topo do loop vai incrementar de novo.
                    task.iteration = max(0, task.iteration - 1)
                    self.repo.save(task)
                    continue
                # Orçamento de continuações esgotado: segue para validação com o
                # que existe, mas registra que o plano não fechou sozinho.
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=plan_roles.executor,
                        data={
                            "status": "continuation_budget_exhausted",
                            "summary": (
                                f"plano seguiu incompleto após "
                                f"{continuations} continuações; validando o que há"
                            ),
                        },
                    )
                )
            continuation_note = ""

            agent_timed_out = bool(exec_result.timed_out)
            if agent_timed_out and not exec_result.changed_files:
                # Padrão Codex/Windows (quoting/heredoc PowerShell): timeout sem
                # escrever nada. "Continue do disco" é inútil sem arquivos —
                # rejeita como infra e rotaciona o executor via fallback.
                #
                # bug-087 — três mortes diferentes vinham com o MESMO rótulo
                # "AGENT-TIMEOUT-NO-OUTPUT". Na GuardLine e0457603df65 o
                # corrector tinha 20KB de stderr e o registro dizia "timeout sem
                # arquivos alterados": quem leu o log procurou o defeito no
                # lugar errado. Rotular pela evidência.
                issue_id, description, error_text = self._timeout_issue(
                    role, plan_roles.executor, exec_result, task
                )
                terminal, last_validation = await self._reject_iteration_infra(
                    task,
                    plan_roles,
                    issue_id=issue_id,
                    description=description,
                    summary="executor timeout without changed files",
                    error_text=error_text,
                    issue_counts=issue_counts,
                )
                if terminal is not None:
                    return terminal
                continue

            # TESTING
            task = self._ensure_runnable(self.get(task.id))
            self.repo.transition(task, TaskState.TESTING, reason="deterministic tests")
            self.bus.emit(RuntimeEvent(task_id=task.id, type=EventType.TEST_STARTED))
            # bug-048 — pasta-mãe de repos aninhados: descoberta na raiz não
            # acha stack nenhuma; roda também nos repos filhos tocados.
            nested_test_dirs = sorted(
                {
                    f.split("/", 1)[0]
                    for f in changed_files
                    if "/" in f
                    and (
                        self.config.project_path / f.split("/", 1)[0] / ".git"
                    ).exists()
                }
            )
            with self._test_lock():
                test_results = self.tests.run_all(
                    self.config.project_path,
                    extra_dirs=nested_test_dirs,
                    baseline=self._ctx(task).run_ctx.get("test_baseline"),
                )
            last_test_results = test_results
            self._ctx(task).run_ctx["test_results"] = test_results
            for tr in test_results:
                self.repo.add_test_run(task_id=task.id, **tr)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TEST_COMPLETED,
                    data={"results": [{"command": t["command"], "status": t["status"]} for t in test_results]},
                )
            )
            # bug-065 — falha "preexisting" (mesma assinatura da baseline
            # pré-executor) NÃO derruba o gate de testes: é quebra que já
            # existia, não mérito da iteração. Sem isto, o TEST-FAIL abaixo
            # condenava a task mesmo com o det aprovando (e2e 0.4.44).
            tests_passed = all(
                t["status"] in {"passed", "skipped"}
                or t.get("failure_kind") == "preexisting"
                for t in test_results
            )

            # VALIDATING
            task = self._ensure_runnable(self.get(task.id))
            self.repo.transition(
                task, TaskState.VALIDATING, reason="independent validation", agent=plan_roles.validator
            )
            self.bus.emit(
                RuntimeEvent(task_id=task.id, type=EventType.VALIDATION_STARTED)
            )
            det = self.det_validator.evaluate(
                task,
                changed_files=changed_files,
                test_results=test_results,
                project_path=self.config.project_path,
            )
            # Independent agent validation — policy hard gate
            val_agent = plan_roles.validator
            if (
                self.config.limits.require_independent_validation
                and val_agent == plan_roles.executor
            ):
                # bug-053 — validator==executor após rotação de infra (ex.:
                # executor girou para o agente do validator após EXEC-SPAWN,
                # ou o validator caiu no agente do executor por quota) tornava
                # a aprovação IMPOSSÍVEL: VAL-IND bloqueava toda iteração até o
                # repeat-limit, mesmo com entrega válida (task ff270e3ff814).
                # Antes de bloquear, girar o validator para um fallback
                # disponível ≠ executor; só bloqueia se não houver alternativa.
                rotated = self._next_validator_fallback(task, plan_roles, val_agent)
                if rotated:
                    self.bus.emit(
                        RuntimeEvent(
                            task_id=task.id,
                            type=EventType.AGENT_COMPLETED,
                            role="validator",
                            agent=rotated,
                            data={
                                "status": "validator_rotated",
                                "reason": (
                                    f"validator==executor ({val_agent}); "
                                    f"validator → {rotated} (independent validation)"
                                ),
                            },
                        )
                    )
                    plan_roles.validator = rotated
                    val_agent = rotated
                else:
                    det["status"] = "rejected"
                    det["blocking_issues"] = list(det.get("blocking_issues") or []) + [
                        {
                            "id": "VAL-IND",
                            "severity": "blocking",
                            "description": (
                                "validator==executor com require_independent_validation "
                                "e nenhum validator alternativo disponível"
                            ),
                        }
                    ]
                    det["score"] = min(float(det.get("score") or 0.0), 0.5)
                    det["summary"] = (
                        det.get("summary", "")
                        + " | blocking: validator==executor (independent validation required)"
                    )
            # 0.4.68 — enfraquecimento de teste entra no registro como
            # não-bloqueante: refator legítimo também remove asserção, e esta
            # frota já pagou caro por heurística de texto confiante demais
            # (bug-097). Quem transforma em blocking é o validador, se
            # confirmar. Mas some do relatório NUNCA.
            integridade = self._test_integrity_findings(changed_files)
            if integridade:
                base = len(det.get("non_blocking_issues") or [])
                det["non_blocking_issues"] = list(
                    det.get("non_blocking_issues") or []
                ) + [
                    f.as_issue(f"VAL-TI{base + i:02d}")
                    for i, f in enumerate(integridade, start=1)
                ]
            val_prompt = self._build_validator_prompt(task, det, test_results, changed_files)
            # bug-104 — sem orçamento para o veredito, NÃO estourar. `_run_agent`
            # levantava RuntimeError("Orçamento de tempo insuficiente para
            # validator (timeout_s=0)") e a task terminava FAILED: um trabalho
            # possivelmente pronto reprovado por relógio, com texto que parecia
            # mérito. O veredito determinístico já existe aqui — usar ele e
            # DIZER que o julgamento independente não coube.
            val_result = None
            if self._remaining_duration_s(task) < MIN_AGENT_TIMEOUT_S:
                last_validation = dict(det)
                last_validation["validator_infra_failure"] = True
                last_validation["validation_skipped"] = "budget"
                last_validation["summary"] = (
                    str(det.get("summary") or "")
                    + " | validator NÃO rodou: orçamento da task esgotado"
                    " (não é rejeição de mérito)"
                )
            else:
                val_result = await self._run_agent(
                    val_agent, "validator", val_prompt, task
                )
                last_validation = self.llm_validator.parse(val_result.stdout, det)
            if (
                val_result is not None
                and last_validation is det
                and self._validator_infra_failure(val_result)
            ):
                # Sem veredito LLM por falha de infra (ex.: sandbox Windows 740):
                # tentar validator alternativo; nunca virar rejeição de mérito.
                fb_agent = self._next_validator_fallback(task, plan_roles, val_agent)
                if fb_agent:
                    try:
                        val_result = await self._run_agent(
                            fb_agent, "validator", val_prompt, task
                        )
                        last_validation = self.llm_validator.parse(
                            val_result.stdout, det
                        )
                    except Exception:  # noqa: BLE001
                        last_validation = det
                if last_validation is det:
                    last_validation = dict(det)
                    last_validation["validator_infra_failure"] = True
                    last_validation["summary"] = (
                        str(det.get("summary") or "")
                        + " | validator infra failure — veredito LLM indisponível"
                        " (não é rejeição de mérito)"
                    )
            # Prefer stricter: if deterministic rejected, keep rejected
            if det["status"] != "approved":
                last_validation["status"] = "rejected"
                last_validation["blocking_issues"] = det["blocking_issues"]
                last_validation["score"] = min(
                    float(last_validation.get("score") or 1.0), float(det["score"])
                )
            # Testes falhos sempre forçam ciclo de correção (mesmo se o LLM aprovou)
            if not tests_passed:
                failed = [
                    t
                    for t in test_results
                    if t.get("status") not in {"passed", "skipped"}
                    and t.get("failure_kind") != "preexisting"
                ]
                last_validation["status"] = "rejected"
                issues = list(last_validation.get("blocking_issues") or [])
                issues.append(
                    {
                        "id": "TEST-FAIL",
                        "severity": "blocking",
                        "description": (
                            "Suite determinística falhou: "
                            + ", ".join(
                                f"{t.get('command')}:{t.get('status')}" for t in failed
                            )
                        ),
                    }
                )
                last_validation["blocking_issues"] = issues
                last_validation["score"] = min(
                    float(last_validation.get("score") or 0.0), 0.4
                )

            if agent_timed_out:
                last_validation["status"] = "rejected"
                timeout_issues = list(last_validation.get("blocking_issues") or [])
                timeout_issues.insert(
                    0,
                    {
                        "id": "AGENT-TIMEOUT",
                        "severity": "blocking",
                        "description": (
                            f"{role}/{plan_roles.executor} atingiu timeout "
                            f"({exec_result.duration_s:.0f}s). Retome a partir dos "
                            f"arquivos já no disco; não reinvente o inventário."
                        ),
                    },
                )
                last_validation["blocking_issues"] = timeout_issues
                last_validation["score"] = min(
                    float(last_validation.get("score") or 0.0), 0.2
                )

            # 0.4.52-C2 — hashes dos inputs da validação: re-auditoria
            # futura reproduz o estado exato medido nesta rodada.
            last_validation["input_hashes"] = _collect_input_hashes(
                self.config.project_path, changed_files
            )
            self.repo.add_validation_round(
                task_id=task.id,
                iteration=task.iteration,
                status=last_validation.get("status", "rejected"),
                score=last_validation.get("score"),
                payload_json=dumps(last_validation),
            )
            for issue in last_validation.get("blocking_issues") or []:
                iid = issue.get("id") if isinstance(issue, dict) else str(issue)
                desc = issue.get("description") if isinstance(issue, dict) else str(issue)
                self.repo.add_validation_issue(
                    task_id=task.id,
                    issue_id=iid,
                    severity="blocking",
                    description=desc or "",
                )
                # Timeout: não contar VAL-* de workspace/evidence vazios no
                # same_issue_repeat (evita INCOMPLETE falso por entrega "vazia").
                if agent_timed_out and self._is_empty_delivery_issue(issue):
                    continue
                # bug-052 — identidade da issue = id + descrição normalizada.
                # IDs são posicionais (VAL-001 = 1ª issue da rodada): problemas
                # DIFERENTES caem no mesmo id entre iterações (iter1 "Critério
                # não atendido: coleção Postman..." → iter3 "Teste falhou: go
                # test") e o repeat-limit encerrava a task por coincidência de
                # posição, não por repetição real (task ff270e3ff814).
                norm = " ".join(str(desc or "").lower().split())[:160]
                issue_counts[f"{iid}|{norm}"] = issue_counts.get(f"{iid}|{norm}", 0) + 1

            task.last_score = float(last_validation.get("score") or 0)
            self._ctx(task).run_ctx["last_validation"] = last_validation
            self.repo.save(task)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.VALIDATION_COMPLETED,
                    data={
                        "status": last_validation.get("status"),
                        "score": last_validation.get("score"),
                    },
                )
            )

            decision = await self.manager.evaluate_iteration(
                task, last_validation, task.iteration
            )
            # same issue repeat
            if any(
                c >= self.config.limits.same_issue_repeat_limit
                for c in issue_counts.values()
            ):
                decision.action = "stop_incomplete"
                decision.reason = "same_issue_repeat_limit"

            self.repo.add_iteration(
                task.id,
                task.iteration,
                task.last_score,
                decision.action,
                {"reason": decision.reason, "issues": decision.issues},
            )

            if decision.action == "approve" and tests_passed:
                break
            if decision.action == "approve" and not tests_passed:
                decision.action = "correct"
                decision.reason = "tests_failed"
            if decision.action in {"stop_incomplete", "fail"}:
                target = (
                    TaskState.FAILED
                    if decision.action == "fail"
                    else TaskState.INCOMPLETE
                )
                self.repo.transition(task, target, reason=decision.reason)
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=(
                            EventType.TASK_FAILED
                            if target == TaskState.FAILED
                            else EventType.TASK_INCOMPLETE
                        ),
                    )
                )
                self._persist_episode(task, success=False)
                return task

            # correct
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.CORRECTION_REQUESTED,
                    data={"issues": decision.issues},
                )
            )
            self.repo.transition(
                task, TaskState.CORRECTING, reason=decision.reason, agent=plan_roles.executor
            )

        # Documentation gate
        task = self.get(task.id)
        self.repo.transition(
            task, TaskState.UPDATING_DOCUMENTATION, reason="documentation gate"
        )
        self.bus.emit(
            RuntimeEvent(task_id=task.id, type=EventType.DOCUMENTATION_STARTED)
        )
        doc_review = self.docs.ensure_usage_docs(
            self.config.project_path, task.prompt, changed_files
        )
        task.documentation_review = doc_review
        self.repo.save(task)
        self.repo.save_documentation_update(task.id, doc_review)
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.DOCUMENTATION_COMPLETED,
                data=doc_review,
            )
        )

        ok, reason = self.gate.can_complete(
            validation=last_validation,
            tests_passed=tests_passed,
            documentation_review=doc_review,
        )
        self.repo.transition(task, TaskState.CONSOLIDATING, reason="completion gate")
        if not ok:
            self.repo.transition(task, TaskState.INCOMPLETE, reason=reason)
            self._persist_episode(task, success=False)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.TASK_INCOMPLETE,
                    data={"reason": reason},
                )
            )
            return task

        self.repo.transition(task, TaskState.COMPLETED, reason="all gates passed")
        self.bus.emit(RuntimeEvent(task_id=task.id, type=EventType.TASK_COMPLETED))
        self._persist_episode(task, success=True, strategy=plan_roles.strategy)
        # human-readable memory export
        self._export_memory_markdown(task)
        return task

    def _required_tooling_block(self) -> str:
        """Bloco de ferramentas obrigatórias injetado em todos os prompts (0.4.12)."""
        if not self.config.limits.caveman_enabled:
            return ""
        return (
            "Ferramentas obrigatórias (always-on, 0.4.12):\n"
            "- OpenWolf: leia .wolf/STATUS.md ANTES de qualquer ação; "
            "consulte .wolf/cerebrum.md (Do-Not-Repeat) antes de gerar código; "
            "use .wolf/anatomy.md como índice de arquivos.\n"
            "- Graphify: se .codegraph/ existir, use `codegraph explore` "
            "para localizar símbolos antes de ler arquivos.\n"
            "- Superpowers: invoque a skill `using-superpowers` antes de qualquer ação; "
            "aplique skills de processo relevantes (brainstorming, systematic-debugging, etc.).\n"
            "- Caveman (full): prosa concisa sem artigos/enchimento. "
            "NUNCA abreviar JSON, logs, erros, planos, docs ou código."
        )

    def _pick_selector_agent(self) -> str | None:
        """Return best available CLI agent for skill selection (fast-tier capable)."""
        for name in ("claude", "codex", "opencode", "gemini", "kimi"):
            adapter = self.registry.get(name)
            if adapter and adapter.detect().available:
                return name
        return None

    async def _select_skills(self, task: TaskRecord) -> None:
        """Discover installed skills and select relevant ones with a fast model (0.4.13).

        Result stored in task.analysis["selected_skills"]. Fails silently so
        the workflow continues even when skill discovery or the CLI call fails.
        """
        if not self.config.limits.skill_selection_enabled:
            return
        from orchestrator_runtime.skills.discovery import discover_skills
        from orchestrator_runtime.skills.selector import (
            build_selector_prompt,
            parse_and_validate,
            select_skills_heuristic,
        )
        try:
            catalog = discover_skills(
                self.config.project_path,
                include_user_global=self.config.limits.skill_selection_include_user_global,
            )
        except Exception:  # noqa: BLE001
            return
        if not catalog:
            return
        max_skills = self.config.limits.skill_selection_max_skills
        selected: list[str] = []
        selector_agent = self._pick_selector_agent()
        if selector_agent:
            sel_prompt = build_selector_prompt(task.prompt, catalog, max_skills)
            try:
                sel_result = await self._run_agent(
                    selector_agent,
                    "skill_selector",
                    sel_prompt,
                    task,
                    timeout_cap_s=self.config.limits.skill_selection_timeout_s,
                )
                selected = parse_and_validate(sel_result.stdout, catalog, max_skills)
            except Exception:  # noqa: BLE001
                pass
        if not selected:
            selected = select_skills_heuristic(
                catalog,
                task.prompt,
                task.task_type,
                max_skills=max_skills,
            )
        if selected:
            analysis_d = dict(task.analysis or {})
            analysis_d["selected_skills"] = selected
            task.analysis = analysis_d
            self.repo.save(task)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.ROUTING_DECIDED,
                    data={"selected_skills": selected, "skill_count": len(selected)},
                )
            )

    def _skills_block(self, task: TaskRecord) -> str:
        """Render selected skills for injection into prompts (0.4.13)."""
        analysis_d = task.analysis if isinstance(task.analysis, dict) else {}
        selected: list[str] = list(analysis_d.get("selected_skills") or [])
        if not selected:
            return ""
        from orchestrator_runtime.skills.discovery import discover_skills
        try:
            catalog = discover_skills(
                self.config.project_path,
                include_user_global=self.config.limits.skill_selection_include_user_global,
            )
        except Exception:  # noqa: BLE001
            catalog = []
        desc_map = {e.skill_id: e.description for e in catalog}
        lines = []
        for sid in selected:
            desc = desc_map.get(sid, "")
            lines.append(f"- {sid}: {desc}" if desc else f"- {sid}")
        return (
            "Skills selecionadas (instaladas; use APENAS estas, não invente outras):\n"
            + "\n".join(lines)
        )

    def _agents_block(self) -> str:
        """Personas de agente definidas no projeto (bug-081): o executor herda
        as INSTRUÇÕES como guia de escopo/convenções do time — nunca a
        delegação (delegação aninhada é proibida: faça você mesmo)."""
        roots = (
            (".claude/agents", "*.md"),
            (".codex/agents", "*.toml"),
            (".kimi-code/agents", "*.md"),
            (".opencode/agent", "*.md"),
        )
        found: list[str] = []
        for rel, pat in roots:
            d = self.config.project_path / rel
            if not d.is_dir():
                continue
            for f in sorted(d.glob(pat)):
                found.append(f"- {rel}/{f.name}")
        if not found:
            return ""
        return (
            "Agentes definidos no projeto (personas; use as INSTRUÇÕES como "
            "guia de escopo e convenções — NÃO delege: delegação aninhada é "
            "proibida, faça você mesmo sequencialmente):\n"
            + "\n".join(found[:12])
        )

    def _rules_block(self, task: TaskRecord) -> str:
        """Regras do projeto aplicáveis ao pedido (0.4.27).

        Sem isto o executor reimplementava padrões que o time já tinha escrito
        em `.cursor/rules/` — as regras existiam mas nunca chegavam ao agente.
        """
        from orchestrator_runtime.rules.discovery import select_rules

        analysis_d = task.analysis if isinstance(task.analysis, dict) else {}
        languages = list(analysis_d.get("languages") or [])
        try:
            rules = select_rules(
                self.config.project_path, task.prompt, languages=languages
            )
        except Exception:  # noqa: BLE001
            return ""
        if not rules:
            return ""

        lines = [
            "Regras do projeto aplicáveis (autoritativas; LEIA o arquivo antes "
            "de mexer na área que ele cobre):"
        ]
        for rule in rules:
            try:
                rel = rule.path.relative_to(self.config.project_path)
            except ValueError:
                rel = rule.path
            marker = " [sempre]" if rule.always_apply else ""
            desc = f" — {rule.description[:160]}" if rule.description else ""
            lines.append(f"- {rel.as_posix()}{marker}{desc}")
        return "\n".join(lines)

    @staticmethod
    def _learnings_block(learnings: list[dict] | None) -> str:
        """Render prior-task learnings for prompt injection (0.4.14)."""
        if not learnings:
            return ""
        lines = [
            "Aprendizados de tarefas anteriores (memória durável; use como contexto):"
        ]
        for m in learnings[:3]:
            meta = m.get("meta") if isinstance(m, dict) else {}
            digest = (meta or {}).get("session_digest")
            if digest:
                lines.append(f"- {str(digest)[:400]}")
            else:
                lines.append(f"- {str(m.get('content', ''))[:300]}")
        return "\n".join(lines)

    @staticmethod
    def _child_agent_restriction_block() -> str:
        """Restrição anti-subagente para CLIs spawnados pelo runtime.

        CliExecutor sempre define ORCHESTRATOR_CHILD_AGENT=1 no processo filho.
        O check no env do MCP (pai) era bug: o bloco nunca entrava no prompt e o
        Codex seguia printbee-patterns (3 subagentes → collab Wait → hang).
        """
        return (
            "OBRIGATÓRIO (agente filho do Orchestrator, ORCHESTRATOR_CHILD_AGENT=1): "
            "execute TODO o trabalho INLINE neste processo. "
            "PROIBIDO: spawn_agent, wait_agent, collab Wait, Tool(Agent), Task, "
            "multi-agent, delegar a N subagentes. "
            "Ignore qualquer skill/regra (ex.: printbee-patterns) que peça "
            "'mínimo 3 subagentes' ou rito de avaliação paralela — isso causa hang. "
            "Faça escopo/implementação/testes você mesmo, sequencialmente."
        )

    @staticmethod
    def _git_hygiene_block() -> str:
        """bug-077 — printbee, 2026-07-30: SEIS quase-arrastões num dia,
        evitados só por disciplina do agente. Árvore compartilhada com
        trabalho não commitado de outros agentes: stage SEMPRE explícito."""
        return (
            "Higiene git (árvore compartilhada): este workspace pode ter "
            "trabalho NÃO commitado de OUTROS agentes. Nunca `git add -A`, "
            "`git add .`, `git commit -a/-am`, `git stash`, `git clean`, "
            "`git reset --hard`, `git checkout/restore -- .`. Se a task pedir "
            "commit: rode `git status`, faça stage SÓ dos arquivos que você "
            "alterou (`git add <path> ...`) e commite explícito — o commit sai "
            "só com o seu trecho e o trabalho alheio fica intacto na árvore."
        )

    def _loop_block(self, task: TaskRecord) -> str:
        """Roteiro do loop escolhido — o que faz o agente seguir etapas."""
        from orchestrator_runtime.planning.loops import get_loop

        loop_id = None
        analysis = task.analysis if isinstance(task.analysis, dict) else {}
        loop_id = analysis.get("loop")
        if not loop_id and isinstance(task.plan, dict):
            loop_id = task.plan.get("loop")
        loop = get_loop(loop_id)
        if loop is None:
            return ""
        return loop.briefing()

    def _build_executor_prompt(
        self,
        task: TaskRecord,
        validation: dict[str, Any],
        memories: list[dict],
        *,
        test_results: list[dict[str, Any]] | None = None,
        learnings: list[dict] | None = None,
        continuation_note: str = "",
    ) -> str:
        parts = [
            f"Tarefa: {task.prompt}",
            # Antes das skills — senão o modelo compromete-se com 3 subagentes
            self._child_agent_restriction_block(),
        ]
        loop_block = self._loop_block(task)
        if loop_block:
            parts.append(loop_block)
        # bug-077 — higiene git sempre ligada no executor/corrector: árvore
        # compartilhada não pode depender de disciplina do agente.
        parts.append(self._git_hygiene_block())
        # 0.4.52-C1 - cap de 3 commits por iteracao (prompts.md Global Rule 17):
        # escopo grande convida a drift e fadiga de revisao.
        # bug-081 — o executor também herda os agentes do projeto (personas
        # como guia de escopo; delegação continua proibida).
        agents_block = self._agents_block()
        if agents_block:
            parts.append(agents_block)
        parts.append(
            "Cap de commits: máximo 3 commits nesta iteração. Se a correção "
            "natural pedir mais, pare nos 3 e descreva no relatório o plano de "
            "sub-slices restantes (sequenciais, na MESMA branch - nunca branch "
            "nova por sub-slice)."
        )

        if continuation_note:
            parts.append(continuation_note)
        parts.extend(
            [
                "Critérios:",
                *[f"- {c.id}: {c.description}" for c in task.acceptance_criteria],
            ]
        )
        if validation.get("blocking_issues"):
            parts.append("Corrija os issues:")
            for issue in validation["blocking_issues"]:
                if isinstance(issue, dict):
                    parts.append(f"- {issue.get('id')}: {issue.get('description')}")
                else:
                    parts.append(f"- {issue}")
            if any(
                isinstance(i, dict) and i.get("id") == "AGENT-TIMEOUT"
                for i in validation["blocking_issues"]
            ):
                parts.append(
                    "Atenção: a iteração anterior estourou timeout. "
                    "Inspecione o disco (git status) e continue o trabalho; "
                    "não recomece do zero."
                )
        if test_results:
            failed = [
                t
                for t in test_results
                if t.get("status") not in {"passed", "skipped"}
            ]
            introduced = [t for t in failed if t.get("failure_kind") != "preexisting"]
            preexisting = [t for t in failed if t.get("failure_kind") == "preexisting"]
            if introduced:
                parts.append("Testes que falharam (corrija até passarem):")
                for t in introduced:
                    parts.append(
                        f"- cmd={t.get('command')} status={t.get('status')} "
                        f"exit={t.get('exit_code')}"
                    )
            if preexisting:
                # bug-065 — já falhavam na baseline: informar para não
                # assustar, mas NÃO exigir correção (fora do escopo da task).
                parts.append(
                    "Falhas pré-existentes da suíte (já falhavam antes da "
                    "task; NÃO é exigido corrigir):"
                )
                for t in preexisting:
                    parts.append(
                        f"- cmd={t.get('command')} status={t.get('status')} "
                        f"exit={t.get('exit_code')}"
                    )
        if memories:
            parts.append("Memória relevante:")
            for m in memories[:3]:
                parts.append(f"- {m.get('content', '')[:200]}")
        learnings_block = self._learnings_block(learnings)
        if learnings_block:
            parts.append(learnings_block)
        analysis_d = task.analysis if isinstance(task.analysis, dict) else {}
        user_answer = analysis_d.get("user_message") or analysis_d.get(
            "resume_instruction"
        )
        if user_answer:
            parts.append(f"Decisão do usuário (já autorizada): {user_answer}")
        skills = self._skills_block(task)
        if skills:
            parts.append(skills)
        rules = self._rules_block(task)
        if rules:
            parts.append(rules)
        tooling = self._required_tooling_block()
        if tooling:
            parts.append(tooling)
        parts.append(
            "Escopo: o objetivo acima já define o que fazer. NÃO faça perguntas "
            "abertas nem pare para pedir decisão de negócio — implemente o "
            "escopo definido."
        )
        parts.append(
            "NÃO pare no meio do plano para perguntar se deve continuar: trabalhe "
            "até cumprir todos os critérios. Ao encerrar, emita como ÚLTIMA linha:\n"
            'PLAN_STATUS: {"complete": true}\n'
            'ou, se algo ficou pendente: PLAN_STATUS: {"complete": false, '
            '"remaining": ["o que falta", "..."]}\n'
            "O orquestrador usa essa linha para mandar continuar automaticamente."
        )
        parts.append(
            "Se a premissa da task for factualmente errada (já corrigido, já "
            "existe, já entregue no HEAD), NÃO invente trabalho: pare e responda "
            "com a linha `PREMISE_MISMATCH: <o que existe de verdade, com "
            "evidência>` — é um resultado de primeira classe, não uma falha."
        )
        parts.append(
            "Somente se estiver bloqueado por decisão externa obrigatória, "
            'escreva uma única linha REQUIRES_INPUT: {"question": "...", '
            '"options": ["..."]} e encerre imediatamente sem alterar arquivos.'
        )
        parts.append(self._stack_hint())
        if os.name == "nt":
            parts.append(
                "Ambiente Windows: NÃO use heredoc nem quoting complexo de "
                "PowerShell para criar arquivos; prefira a ferramenta de escrita "
                "de arquivos do agente, `python -c` ou arquivo temporário."
            )
        parts.append(
            "Caveman full na prosa; NUNCA abreviar JSON/logs/erros/planos/docs/código. "
            "Não declare sucesso sem evidências."
        )
        return "\n".join(parts)

    def _stack_hint(self) -> str:
        cmds = stack_test_commands(self.config.project_path)
        if not cmds:
            return (
                "Nenhuma suite de testes detectada no workspace; "
                "não invente comandos de teste."
            )
        return (
            "Testes detectados no workspace: "
            + "; ".join(cmds)
            + ". Use SOMENTE estes comandos de teste; não exija outros "
            "(ex.: pytest em projeto Node/Angular)."
        )

    _REQUIRES_INPUT_RE = re.compile(
        r"^\s*REQUIRES_INPUT\s*:\s*(.+)$", re.MULTILINE
    )

    # Aceita marcador puro ou envolvido por bullet/ênfase Markdown na própria linha.
    _PREMISE_MISMATCH_RE = re.compile(
        r"^[\t ]*(?:[-*>]\s*)*(?:[`*_~]+\s*)?"
        r"PREMISE_MISMATCH(?:\s*[`*_~]+)?\s*:\s*"
        r"(?:[`*_~]+\s*)?(.+?)\s*$",
        re.MULTILINE | re.IGNORECASE,
    )

    # Contrato explícito de conclusão emitido pelo executor.
    _PLAN_STATUS_RE = re.compile(
        r"^\s*PLAN_STATUS\s*:\s*(\{.*\})\s*$", re.MULTILINE
    )

    # Fallback: frases com que os CLIs param no meio do plano pedindo permissão.
    _EARLY_STOP_RE = re.compile(
        r"(?:"
        r"quer(?:e|ia)?\s+que\s+eu\s+(?:continue|siga|prossiga)"
        r"|posso\s+(?:continuar|seguir|prosseguir)"
        r"|deseja\s+que\s+eu\s+(?:continue|siga|prossiga)"
        r"|(?:me\s+)?avise\s+se\s+(?:quiser|deseja|posso)"
        r"|continuo\s*\?"
        r"|shall\s+i\s+(?:continue|proceed)"
        r"|(?:do\s+you\s+)?want\s+me\s+to\s+(?:continue|proceed)"
        r"|let\s+me\s+know\s+if\s+you(?:'d| would)?\s+like\s+me\s+to"
        r"|(?:next|remaining)\s+steps?\s*:"
        r"|(?:proximos|próximos)\s+passos\s*:"
        r"|(?:ainda\s+)?falta(?:m|ndo)?\s+(?:implementar|fazer|concluir|as\s+etapas)"
        r"|n[aã]o\s+implementei"
        r"|parte\s+\d+\s+de\s+\d+"
        r"|etapa\s+\d+\s+de\s+\d+"
        r")",
        re.IGNORECASE,
    )

    @classmethod
    def _parse_plan_status(cls, stdout: str | None) -> dict[str, Any] | None:
        """Lê a linha PLAN_STATUS que o executor deve emitir ao terminar."""
        match = cls._PLAN_STATUS_RE.search(stdout or "")
        if not match:
            return None
        try:
            data = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def _is_plan_incomplete(
        cls, plan_status: dict[str, Any] | None, stdout: str | None
    ) -> bool:
        """Plano ficou pela metade?

        Primeiro o contrato explícito (PLAN_STATUS). Sem ele, cai nas frases de
        parada que os CLIs usam para pedir permissão de seguir — o comportamento
        que o usuário relata como "o agente para no meio do plano".
        """
        if isinstance(plan_status, dict) and "complete" in plan_status:
            return not bool(plan_status.get("complete"))
        if plan_status is not None:
            return False
        return bool(cls._EARLY_STOP_RE.search(stdout or ""))

    @staticmethod
    def _continuation_note(
        remaining: list[str], changed_files: list[str], attempt: int
    ) -> str:
        parts = [
            f"CONTINUACAO {attempt}: a execucao anterior parou com o plano "
            "INCOMPLETO. Retome de onde parou; NAO recomece do zero e NAO "
            "refaca o que ja esta no disco.",
        ]
        if changed_files:
            parts.append(
                "Ja alterado: " + ", ".join(changed_files[:12])
                + (" ..." if len(changed_files) > 12 else "")
            )
        if remaining:
            parts.append("Falta concluir:")
            parts.extend(f"- {item}" for item in remaining[:10])
        parts.append(
            "Trabalhe ate cumprir TODOS os criterios de aceitacao. Nao pergunte "
            "se deve continuar — continue."
        )
        return "\n".join(parts)

    @classmethod
    def _parse_requires_input(cls, stdout: str | None) -> dict[str, Any] | None:
        match = cls._REQUIRES_INPUT_RE.search(stdout or "")
        if not match:
            return None
        payload = match.group(1).strip()
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict) and data.get("question"):
            return {
                "question": str(data["question"]),
                "options": [str(o) for o in data.get("options") or []],
            }
        return {"question": payload[:500], "options": []}

    @classmethod
    def _parse_premise_mismatch(cls, stdout: str | None) -> str | None:
        """Extrai a explicação do outcome terminal PREMISE_MISMATCH."""
        match = cls._PREMISE_MISMATCH_RE.search(stdout or "")
        if not match:
            return None
        explanation = re.sub(
            r"\s*[`*_~]+\s*$", "", match.group(1).strip()
        ).strip()
        return explanation[:500] or None

    def _test_integrity_findings(self, changed_files: list[str]) -> list:
        """Sinais de enfraquecimento de teste no diff da iteração (0.4.68).

        O executor escreve o código E os testes, e o gate só olha se a suíte
        fica verde — nada impedia baixar uma asserção para passar. Lê o diff de
        verdade (git), não a narrativa do agente.
        """
        alvos = [f for f in changed_files if is_test_path(f)]
        if not alvos:
            return []
        try:
            proc = run_git(
                self.config.project_path, "diff", "--unified=0", "--", *alvos
            )
            if proc.returncode != 0:
                return []
            return analyze_diff(proc.stdout)
        except Exception:  # noqa: BLE001
            return []  # heurística de apoio nunca derruba a validação

    def _build_validator_prompt(
        self,
        task: TaskRecord,
        det: dict[str, Any],
        tests: list[dict],
        changed_files: list[str],
    ) -> str:
        tooling = self._required_tooling_block()
        tooling_section = f"{tooling}\n" if tooling else ""
        skills = self._skills_block(task)
        skills_section = f"{skills}\n" if skills else ""
        child = self._child_agent_restriction_block()
        integridade = summarize(self._test_integrity_findings(changed_files))
        integridade_section = f"{integridade}\n" if integridade else ""
        return (
            "Valide a tarefa e responda APENAS JSON com status/score/blocking_issues.\n"
            f"{child}\n"
            # 0.4.68 — o veredito vem da OBSERVAÇÃO, não da narrativa. O maior
            # modo de falha documentado de agente de código é declarar sucesso
            # independente do resultado; nesta frota já apareceu como score 1.0
            # com os dois validators mortos (bug-089).
            "COMO JULGAR: trate as afirmações do executor como hipóteses "
            "falsificáveis, não como fatos. O diff e a saída dos testes abaixo "
            "são a verdade; o relato do agente, não. Reexecute o que puder com "
            "suas próprias ferramentas em vez de inferir do código. O que você "
            "NÃO conseguir verificar, marque como UNVERIFIABLE no "
            "non_blocking_issues — nunca aceite por omissão.\n"
            f"{integridade_section}"
            # bug-067 — o juiz roda `git status` com as próprias ferramentas e
            # via arquivos sujos da INFRA do orquestrador (update/propagação,
            # adapters) como "alteração fora de escopo" — iter 1 da task
            # c003522e25e2 (printbee) foi reprovada por isso. Não é trabalho
            # do agente nem violação: ignorar explicitamente.
            "Infra do orquestrador (NUNCA é escopo da task nem violação de "
            "escopo, mesmo suja no `git status`): .orchestrator/, .wolf/, "
            ".cursor/, .codex/, .claude/, .gemini/, .kimi/, AGENTS.md, "
            "CLAUDE.md, CURSOR.md, GEMINI.md, KIMI.md. Ignore esses arquivos "
            "ao julgar escopo e changed_files.\n"
            f"Prompt original: {task.prompt}\n"
            f"Critérios: {dumps([c.model_dump() for c in task.acceptance_criteria])}\n"
            f"Diff/arquivos: {changed_files}\n"
            # bug-065 — failure_kind no payload: o juiz precisa distinguir
            # falha introduzida de pré-existente (baseline) para não reprovar
            # mérito alheio.
            f"Testes: {dumps([{k: t.get(k) for k in ('command','status','exit_code','failure_kind')} for t in tests])}\n"
            "Regra: failure_kind=preexisting significa que o teste JÁ "
            "falhava antes da task (baseline pré-executor); não reprove a "
            "task por ele. Falhas introduced sim são mérito da iteração.\n"
            "Commits: se a iteração produziu mais de 3 commits novos do agente, "
            "sinalize como non-blocking (indício de escopo estourado/drift); "
            "não reprove só por isso.\n"
            f"Validação determinística: {dumps(det)}\n"
            f"{self._stack_hint()}\n"
            f"{skills_section}"
            f"{tooling_section}"
        )

    # bug-087 — quem morreu por quê. As três causas têm remédios opostos:
    # pendurado => trocar de agente; orçamento => aumentar o teto da task;
    # timeout com saída => o agente falou mas não entregou (mérito, não infra).
    _BUDGET_FLOOR_S = 30

    def _timeout_issue(
        self,
        role: str,
        agent_id: str,
        result: AgentResult,
        task: TaskRecord,
    ) -> tuple[str, str, str]:
        produced = bool((result.stdout or "").strip() or (result.stderr or "").strip())
        hung = NO_OUTPUT_MARKER in (result.stderr or "")
        budget_over = self._remaining_duration_s(task) <= self._BUDGET_FLOOR_S
        secs = f"{result.duration_s:.0f}s"
        if hung:
            # 0.4.79 — o eixo OCIOSO do papel é que matou, não o teto duro nem a
            # qualidade do trabalho: o texto tem que dizer FALTA DE SINAL, senão
            # quem lê o `task logs` procura o defeito na entrega.
            try:
                idle = self._resolve_idle_timeout(role, task)
            except Exception:  # noqa: BLE001
                idle = 0
            janela = f" (idle_timeout={idle}s)" if idle else ""
            return (
                "AGENT-NO-OUTPUT-HANG",
                f"{role}/{agent_id} sem sinal de vida{janela}: {secs} sem "
                "NENHUMA saída e sem tocar no workspace; morto pelo eixo ocioso "
                "antes de consumir o teto duro da tentativa. Falta de sinal — "
                "infra, não qualidade do trabalho",
                f"AGENT-NO-OUTPUT-HANG: {role}/{agent_id} sem sinal de vida"
                f"{janela}",
            )
        if budget_over:
            return (
                "TASK-BUDGET-EXHAUSTED",
                f"{role}/{agent_id} cortado em {secs} pelo "
                f"maximum_duration_seconds da task "
                f"({task.constraints.maximum_duration_seconds}s), não pelo "
                f"timeout do papel"
                + (" — havia saída em andamento" if produced else ""),
                f"TASK-BUDGET-EXHAUSTED: {role}/{agent_id} morto pelo teto da task",
            )
        if produced:
            return (
                "AGENT-TIMEOUT-NO-CHANGES",
                f"{role}/{agent_id} atingiu timeout ({secs}) com saída mas sem "
                "alterar arquivo nenhum",
                f"AGENT-TIMEOUT-NO-CHANGES: {role}/{agent_id} timeout com saída "
                "e sem mudanças",
            )
        return (
            "AGENT-TIMEOUT-NO-OUTPUT",
            f"{role}/{agent_id} atingiu timeout ({secs}) sem alterar arquivos",
            f"AGENT-TIMEOUT-NO-OUTPUT: {role}/{agent_id} timeout sem arquivos "
            "alterados",
        )

    def _remaining_duration_s(self, task: TaskRecord) -> int:
        started = self._ctx(task).started_monotonic
        if started is None:
            return int(task.constraints.maximum_duration_seconds)
        elapsed = time.monotonic() - started
        return max(0, int(task.constraints.maximum_duration_seconds - elapsed))

    def _resolve_agent_timeout_policy(
        self, role: str, task: TaskRecord
    ) -> AgentTimeoutPolicy:
        """Orçamento da invocação nos DOIS eixos (0.4.79).

        Ponto único de decisão: o eixo duro vai para ``AgentRequest.timeout_s``
        (o `proc.wait` do CLI) e o eixo ocioso vai para o watchdog de silêncio
        em ``_register_heartbeat``.
        """
        return resolve_agent_timeout_policy(
            role,
            remaining_s=self._remaining_duration_s(task),
            by_role=self.config.limits.agent_timeout_by_role,
            idle_by_role=self.config.limits.agent_idle_timeout_by_role,
            default_s=self.config.limits.agent_timeout_default_s,
        )

    def _resolve_agent_timeout(self, role: str, task: TaskRecord) -> int:
        return self._resolve_agent_timeout_policy(role, task).run_timeout_s

    def _resolve_idle_timeout(self, role: str, task: TaskRecord) -> int:
        """Eixo ocioso efetivo do papel, em segundos (0 = desligado).

        Papel sem eixo próprio cai no ``agent_no_output_timeout_s`` global —
        é isso que preserva o comportamento 0.4.78 para quem não migrou o
        `policies.json`.
        """
        idle = self._resolve_agent_timeout_policy(role, task).idle_timeout_s
        if idle is None:
            return int(self.config.limits.agent_no_output_timeout_s or 0)
        return int(idle)

    # Marcadores de falha de infra do validator (sandbox Windows sem elevação).
    _VALIDATOR_INFRA_MARKERS = (
        "createprocessasuserw failed: 740",
        "windows error 740",
        "requer elevação",
        "requer elevacao",
        "windows sandbox: runner failed",
    )

    @classmethod
    def _validator_infra_failure(cls, result: AgentResult) -> bool:
        """Validator falhou por infra (processo/sandbox), não por mérito."""
        if result.status != "completed":
            return True
        blob = ((result.stdout or "") + (result.stderr or "")).lower()
        return any(m in blob for m in cls._VALIDATOR_INFRA_MARKERS)

    # bug-070 — circuit breaker: o binário existe (detect() passa) mas o
    # SERVIÇO está morto (opencode: "Unexpected server error" em ~8s — 15
    # falhas instantâneas registradas no printbee entre validator/executor).
    # Toda rotação de fallback caía no mesmo agente morto e queimava a
    # iteração. N falhas rápidas consecutivas dentro da janela => quarentena:
    # os pontos de escolha de fallback pulam para o próximo candidato.
    _QUARANTINE_RUNS = 3
    _QUARANTINE_MAX_DURATION_S = 30.0
    _QUARANTINE_WINDOW_S = 6 * 3600  # cooldown: falha velha não condena para sempre

    @staticmethod
    def _duration_between(start: Any, end: Any) -> float | None:
        if not start or not end:
            return None
        try:
            a = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
            b = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
            if a.tzinfo is None:
                a = a.replace(tzinfo=timezone.utc)
            if b.tzinfo is None:
                b = b.replace(tzinfo=timezone.utc)
            return (b - a).total_seconds()
        except Exception:  # noqa: BLE001
            return None

    def _agent_quarantined(self, agent_id: str) -> bool:
        try:
            runs = self.repo.list_recent_agent_runs(agent_id, self._QUARANTINE_RUNS)
        except Exception:  # noqa: BLE001
            return False
        if len(runs) < self._QUARANTINE_RUNS:
            return False
        now = datetime.now(timezone.utc)
        for r in runs:
            if str(r.get("status")) != "failed":
                return False
            dur = self._duration_between(r.get("started_at"), r.get("finished_at"))
            if dur is None or dur > self._QUARANTINE_MAX_DURATION_S:
                return False
            started = self._duration_between(
                r.get("started_at"), now.isoformat()
            )
            if started is None or started > self._QUARANTINE_WINDOW_S:
                return False  # fora da janela: cooldown encerrado
        return True

    def _next_validator_fallback(
        self, task: TaskRecord, plan_roles: Any, current: str
    ) -> str | None:
        fallbacks = (task.plan or {}).get("fallbacks", {}).get("validator") or []
        for fb in fallbacks:
            if fb in {current, plan_roles.executor}:
                continue
            if self._agent_quarantined(fb):
                continue  # bug-070 — serviço morto; próximo candidato
            adapter = self.registry.get(fb)
            if adapter and adapter.detect().available:
                return fb
        return None

    async def _reject_iteration_infra(
        self,
        task: TaskRecord,
        plan_roles: Any,
        *,
        issue_id: str,
        description: str,
        summary: str,
        error_text: str | None,
        issue_counts: dict[str, int],
    ) -> tuple[TaskRecord | None, dict[str, Any]]:
        """Iteração rejeitada por falha de infra do executor (spawn/saída vazia).

        Retorna (task_terminal | None, last_validation). None → caller continua
        o loop em CORRECTING com fallback de executor aplicado.
        """
        last_validation: dict[str, Any] = {
            "status": "rejected",
            "score": 0.0,
            "blocking_issues": [
                {
                    "id": issue_id,
                    "severity": "blocking",
                    "description": description,
                }
            ],
            "summary": summary,
        }
        self._ctx(task).run_ctx["last_validation"] = last_validation
        decision = await self.manager.evaluate_iteration(
            task, last_validation, task.iteration
        )
        issue_counts[issue_id] = issue_counts.get(issue_id, 0) + 1
        if issue_counts[issue_id] >= self.config.limits.same_issue_repeat_limit:
            decision.action = "stop_incomplete"
            decision.reason = "same_issue_repeat_limit"
        self.repo.add_iteration(
            task.id,
            task.iteration,
            0.0,
            decision.action,
            {"reason": decision.reason, "infra_issue": issue_id},
        )
        if decision.action in {"stop_incomplete", "fail"}:
            target = (
                TaskState.FAILED
                if decision.action == "fail"
                else TaskState.INCOMPLETE
            )
            self.repo.transition(
                task, target, reason=decision.reason, error=error_text
            )
            self._persist_episode(task, success=False)
            return task, last_validation
        # Tentar fallback de executor na próxima iteração
        fallbacks = (task.plan or {}).get("fallbacks", {}).get("executor") or []
        for fb in fallbacks:
            if (
                fb != plan_roles.executor
                and self.registry.get(fb)
                and not self._agent_quarantined(fb)  # bug-070 — serviço morto
            ):
                plan_roles.executor = fb
                break
        self.repo.transition(
            task,
            TaskState.CORRECTING,
            reason=f"{issue_id} → correct/fallback",
            agent=plan_roles.executor,
        )
        return None, last_validation

    @staticmethod
    def _is_empty_delivery_issue(issue: Any) -> bool:
        """VAL de workspace/evidence vazio — não deve acelerar same_issue após timeout."""
        if not isinstance(issue, dict):
            return False
        if issue.get("id") == "AGENT-TIMEOUT":
            return False
        kind = str(issue.get("kind") or "").lower()
        if kind in {"workspace_changes", "evidence"}:
            return True
        desc = str(issue.get("description") or "").lower()
        markers = (
            "workspace_changes",
            "entregável",
            "entregavel",
            "arquivos vazio",
            "diff/arquivos vazio",
            "nenhum entregável",
            "changed_files",
        )
        return any(m in desc for m in markers)

    # bug-111 — espera entre as reexecuções após falha de lançamento.
    #
    # Backoff crescente com teto pequeno (26s no total): a janela que o
    # trustsafe mediu era de segundos — ~132 processos `node` vivos, e a
    # próxima task já nascia. Esperar mais que isso seria queimar o orçamento
    # da task por uma condição que ou passa rápido ou não passa.
    _LAUNCH_RETRY_BACKOFF_S: tuple[float, ...] = (3.0, 8.0, 15.0)

    # 0.4.79 — JITTER. O modo de falha que este retry atende (0xC0000142
    # STATUS_DLL_INIT_FAILED) é exaustão de recurso DA MÁQUINA, não do CLI:
    # vários agentes falham no MESMO instante. No trustsafe, 10/08,
    # corrector/codex e corrector/opencode saíram com o mesmo exit code e quatro
    # lançamentos falharam em ~1s. Com intervalo FIXO todos esperam 3s, depois
    # 8s, depois 15s — e colidem de novo, contra o mesmo recurso escasso. O
    # backoff sozinho baixa a frequência; ele não quebra a SINCRONIA, que é a
    # causa. (O `RetryPolicy` do LangGraph usa `jitter=True` por padrão pela
    # mesma razão.)
    #
    # Multiplicativo e só para CIMA: a espera fica em [base, base*1.5). Nunca
    # encurta — retentativa imediata é o oposto do remédio — e o teto continua
    # conhecido: 3+8+15=26s viram no máximo 4,5+12+22,5=39s no pior caso.
    _LAUNCH_RETRY_JITTER_RATIO: float = 0.5

    # Fonte de aleatoriedade INJETÁVEL: teste determinístico troca por uma
    # sequência conhecida no objeto (atributo de instância — atribuir na CLASSE
    # uma função comum a transformaria em método ligado).
    _launch_retry_rand: Callable[[], float] = staticmethod(random.random)

    def _launch_backoff_s(self, base: float) -> float:
        """Espera final da tentativa: base + jitter limitado, nunca menor."""
        try:
            sorteio = float(self._launch_retry_rand())
        except Exception:  # noqa: BLE001
            sorteio = 0.0  # sem sorteio, o backoff antigo — nunca uma exceção
        sorteio = min(1.0, max(0.0, sorteio))
        return float(base) * (1.0 + self._LAUNCH_RETRY_JITTER_RATIO * sorteio)

    async def _retry_launch_failure(
        self,
        adapter: Any,
        request: AgentRequest,
        result: AgentResult,
        *,
        task: TaskRecord,
        agent_id: str,
        report: Any,
    ) -> AgentResult:
        """Reexecuta o MESMO agente após falha de lançamento (bug-111).

        0.4.76 — no trustsafe, 5 tasks morreram INCOMPLETE em 10/08 com
        ``AGENT-FAILED-NO-OUTPUT: corrector/codex exit=3221225794 sem mudancas``
        (0xC0000142 STATUS_DLL_INIT_FAILED). O ramo `launch` só emitia o evento
        e devolvia a mesma falha: ela caía no guard `failed_no_output`, QUEIMAVA
        uma iteração e disparava fallback para outro agente — que também não
        nascia, porque a falta de recurso era da MÁQUINA. `same_issue_repeat_limit`
        estourava e a task morria sem NENHUM julgamento de mérito.

        Nada é reinstalado aqui de propósito: a reinstalação já foi medida
        falhando com o mesmo exit code. Esgotadas as tentativas, o resultado
        devolvido continua sendo o falho — infra, nunca mérito.
        """
        ultimo = result
        for tentativa, base in enumerate(self._LAUNCH_RETRY_BACKOFF_S, start=1):
            # O jitter entra ANTES da guarda de orçamento: comparar o orçamento
            # contra a base e dormir o valor sorteado furaria o teto da task.
            espera = self._launch_backoff_s(base)
            restante = self._remaining_duration_s(task)
            if restante <= espera + MIN_AGENT_TIMEOUT_S:
                # Orçamento da task manda. Esperar aqui deixaria o agente sem
                # tempo de trabalhar mesmo que ele nascesse.
                report(
                    failure_kind="launch",
                    exit_code=ultimo.exit_code,
                    retry_attempt=tentativa,
                    retry_skipped="budget",
                    remaining_s=restante,
                    summary=(
                        f"{agent_id}: sem orçamento para esperar o recurso "
                        f"({restante}s restantes)"
                    ),
                )
                break
            report(
                failure_kind="launch",
                exit_code=ultimo.exit_code,
                retry_attempt=tentativa,
                backoff_s=espera,
                backoff_base_s=base,
                summary=(
                    f"{agent_id}: tentativa {tentativa} de "
                    f"{len(self._LAUNCH_RETRY_BACKOFF_S)} em {espera:.1f}s "
                    f"(base {base:.0f}s + jitter) — mesmo agente, sem reinstalar"
                ),
            )
            if espera > 0:
                await asyncio.sleep(espera)
            try:
                ultimo = await adapter.run(request)
            except Exception as exc:  # noqa: BLE001
                # Reexecutar é conveniência; explodir aqui trocaria uma falha
                # de agente por uma falha de runtime.
                report(
                    failure_kind="launch",
                    retry_attempt=tentativa,
                    retry_error=str(exc),
                )
                return ultimo
            if classify_agent_failure(ultimo) != "launch":
                report(
                    failure_kind="launch",
                    retry_attempt=tentativa,
                    retry_ok=True,
                    exit_code=ultimo.exit_code,
                    summary=f"{agent_id}: processo nasceu na tentativa {tentativa}",
                )
                return ultimo
        report(
            failure_kind="launch",
            exit_code=ultimo.exit_code,
            retry_exhausted=True,
            summary=(
                f"{agent_id}: o processo não nasceu em nenhuma tentativa "
                f"(exit={ultimo.exit_code}). Falta de recurso da máquina — "
                f"infra, não mérito do trabalho"
            ),
        )
        return ultimo

    async def _maybe_repair_and_retry(
        self,
        adapter: Any,
        request: AgentRequest,
        result: AgentResult,
        *,
        task: TaskRecord,
        role: str,
        agent_id: str,
    ) -> AgentResult:
        """CLI quebrado: reinstala uma vez e reexecuta. Nunca derruba a task.

        0.4.63 — o `codex` saía exit=1 com zero byte como executor E como
        validator (task 143e8b2ca47b), e o `opencode` faz o mesmo nesta máquina.
        O bug-070 só colocava em quarentena: esconde, não resolve, e a rodada
        seguinte redescobre do zero. Falta de CREDENCIAL não é reinstalada —
        reinstalar apaga a sessão e o remédio é o `auth_hint`.
        """
        kind = classify_agent_failure(result)
        if kind is None:
            return result

        def _report(**data: Any) -> None:
            # Emitir E persistir: quem investiga depois lê `task logs`, não o
            # console do processo que morreu.
            event = RuntimeEvent(
                task_id=task.id,
                type=EventType.AGENT_REPAIR,
                role=role,
                agent=agent_id,
                data=data,
            )
            self.bus.emit(event)
            self.repo.add_event(event)

        if kind == "launch":
            # bug-109/bug-111 — o processo não nasceu (NTSTATUS de falta de
            # recurso). Reinstalar não tem como funcionar: no trustsafe a
            # própria reinstalação saiu com o MESMO exit code. O remédio é
            # ESPERAR o recurso voltar e tentar de novo o MESMO agente.
            _report(
                failure_kind="launch",
                exit_code=result.exit_code,
                summary=(
                    f"{agent_id}: o processo não chegou a iniciar "
                    f"(exit={result.exit_code}). Falta de recurso da máquina — "
                    f"reinstalar não resolve; esperando para tentar de novo"
                ),
            )
            return await self._retry_launch_failure(
                adapter,
                request,
                result,
                task=task,
                agent_id=agent_id,
                report=_report,
            )
        if kind == "service":
            # bug-106 — o servidor do provedor respondeu erro. Reinstalar é o
            # remédio errado e caro: nos `opencode` de 09/08 o reparo rodou
            # inteiro, terminou `repair_ok: true`, e o agente falhou igual na
            # chamada seguinte. Registrar e deixar o fallback fazer o trabalho.
            _report(
                failure_kind="service",
                summary=(
                    f"{agent_id}: serviço do provedor respondeu erro "
                    f"({result.duration_s:.0f}s). Reinstalar e login NÃO "
                    f"resolvem — outro agente assume"
                ),
            )
            return result
        if kind == "auth":
            _report(
                failure_kind="auth",
                auth_command=auth_hint(agent_id),
                summary=(
                    f"{agent_id}: CLI vivo, sem credencial. Reinstalar não "
                    f"resolve — rode: {auth_hint(agent_id)}"
                ),
            )
            return result
        if not self.config.limits.agent_auto_repair:
            return result
        if agent_id in self._repaired_agents:
            return result
        self._repaired_agents.add(agent_id)

        _report(
            failure_kind="install",
            summary=f"{agent_id}: CLI parece quebrado; tentando reinstalar",
        )
        try:
            repair = repair_agent(
                agent_id,
                project_path=self.config.project_path,
                timeout_s=self.config.limits.agent_repair_timeout_s,
            )
        except Exception as exc:  # noqa: BLE001
            # Reparo é conveniência; explodir aqui trocaria uma falha de agente
            # por uma falha de runtime.
            _report(failure_kind="install", repair_error=str(exc))
            return result

        _report(
            failure_kind="install",
            repair_ok=repair.ok,
            repair_available=repair.available,
            summary=repair.summary,
        )
        if not repair.ok:
            return result
        try:
            return await adapter.run(request)
        except Exception:  # noqa: BLE001
            return result

    def _enrich_changed_files(
        self, result: AgentResult, task: TaskRecord
    ) -> AgentResult:
        if result.changed_files:
            return result
        from_git = changed_files_since(
            self.config.project_path, self._ctx(task).git_baseline
        )
        # 0.4.74 — o fallback via git vê a árvore INTEIRA, então com duas tasks
        # concorrentes ele traria os arquivos da outra. Quando há escopo
        # declarado, o que veio do git é filtrado por ele: atribuir arquivo alheio
        # à task contamina o registro, o learning e o prompt do validator.
        #
        # Só o FALLBACK é filtrado. O que o agente relatou explicitamente passa
        # inteiro — é dele que sai a detecção de desvio (`scope_violation`), e
        # filtrar aqui esconderia justamente o que precisa ser visto.
        escopo = self.task_scope(task)
        if from_git and escopo:
            from_git = [f for f in from_git if path_in_scope(f, escopo)]
        if from_git:
            result.changed_files = list(from_git)
        return result

    # ------------------------------------------------------------------
    # 0.4.61 — fan-out: subtarefas paralelas, cada uma em seu worktree
    # ------------------------------------------------------------------

    def _fanout_enabled(self) -> bool:
        limits = self.config.limits
        return (
            bool(limits.allow_parallel_workspace_writes)
            and int(limits.max_parallel_subtasks) >= 2
            and worktrees_available(self.config.project_path)
        )

    async def _decompose(
        self, task: TaskRecord, plan_roles: OrchestrationPlan
    ) -> list[SubtaskSpec]:
        """Pede a divisão ao planner. Indivisível devolve [] — e isso é normal."""
        max_subtasks = int(self.config.limits.max_parallel_subtasks)
        try:
            result = await self._run_agent(
                plan_roles.planner,
                "planner",
                decomposition_prompt(task.prompt, max_subtasks=max_subtasks),
                task,
            )
        except Exception as exc:  # noqa: BLE001
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_COMPLETED,
                    role="planner",
                    agent=plan_roles.planner,
                    data={
                        "status": "decompose_failed",
                        "summary": f"decomposição falhou; seguindo sequencial: {exc}",
                    },
                )
            )
            return []
        return parse_subtasks(result.stdout or "", max_subtasks=max_subtasks)

    def _subtask_executor(self, worktree: Path) -> CliExecutor:
        """Executor próprio por subtarefa.

        Compartilhar o executor principal quebraria duas coisas ao mesmo tempo:
        o heartbeat (um callback só para N agentes) e — pior — o watchdog de
        silêncio, cuja sonda olha a árvore PRINCIPAL. Como a subtarefa escreve
        no worktree, a sonda global veria "nada mudou" e mataria agentes vivos.
        """
        executor = CliExecutor(
            self.config.project_path,
            echo=False,
            infra_fail_fast_count=self.config.limits.agent_infra_fail_fast_count,
            heartbeat_s=self.caller_profile.heartbeat_s,
        )
        executor.no_output_timeout_s = self.config.limits.agent_no_output_timeout_s
        executor.progress_probe = lambda: bool(
            (run_git(worktree, "status", "--porcelain").stdout or "").strip()
        )
        return executor

    def _subtask_prompt(self, base_prompt: str, spec: SubtaskSpec) -> str:
        scope = ", ".join(spec.scope) if spec.scope else "(não declarado)"
        return (
            f"{base_prompt}\n\n"
            "=== SUBTAREFA PARALELA ===\n"
            f"Você é UM de vários agentes rodando ao mesmo tempo. Sua parte:\n"
            f"{spec.title}\n{spec.instruction}\n\n"
            f"ESCOPO (só estes caminhos): {scope}\n"
            "Você está numa ÁRVORE GIT ISOLADA (worktree próprio): o que você "
            "escrever aqui será fundido na árvore real como patch. Por isso:\n"
            "- Escreva SOMENTE dentro do seu escopo. Arquivo fora dele colide "
            "com o patch de outro agente e o SEU trabalho é o que será "
            "descartado na fusão.\n"
            "- Não faça commit, não use `git stash`, não mexa em branch: a "
            "fusão é do runtime.\n"
            "- Não espere pelas outras subtarefas nem se refira a elas — elas "
            "estão sendo feitas agora, em paralelo."
        )

    def _run_subtask_blocking(
        self,
        *,
        agent_id: str,
        prompt: str,
        worktree: Path,
        timeout_s: int,
        model: str | None,
        model_flag: str | None,
    ) -> AgentResult:
        """Roda a subtarefa numa thread própria.

        `adapter.run` é async mas o CliExecutor por baixo é BLOQUEANTE: um
        gather direto serializaria tudo e ainda travaria o event loop. Cada
        subtarefa ganha thread + loop próprios.
        """
        adapter = self.registry.get(agent_id)
        if adapter is None or not adapter.detect().available:
            raise RuntimeError(f"Agente indisponível para subtarefa: {agent_id}")
        # Cópia rasa do adapter com executor próprio: registry novo por
        # subtarefa descartaria adapter customizado (fake/teste, quarentena) e
        # recarregaria os profiles do disco N vezes. O que precisa ser isolado
        # é o executor — perfil e capacidades são só leitura.
        adapter = copy.copy(adapter)
        if hasattr(adapter, "executor"):
            adapter.executor = self._subtask_executor(worktree)
        request = AgentRequest(
            role="executor",
            prompt=prompt,
            model=model,
            model_flag=model_flag,
            cwd=str(worktree),
            timeout_s=timeout_s,
        )
        return asyncio.run(adapter.run(request))

    async def _run_fanout(
        self,
        task: TaskRecord,
        plan_roles: OrchestrationPlan,
        base_prompt: str,
        specs: list[SubtaskSpec],
    ) -> AgentResult:
        """Executa as subtarefas em paralelo e funde os patches na árvore real."""
        project = self.config.project_path
        timeout_s = self._resolve_agent_timeout("executor", task)
        candidates = self.router.resolve_model_candidates(
            plan_roles.executor, task.task_type, role="executor"
        )
        model, model_flag = candidates[0] if candidates else (None, None)

        handles: dict[str, WorktreeHandle] = {}
        started = datetime.now(timezone.utc).isoformat()
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.AGENT_STARTED,
                role="executor",
                agent=plan_roles.executor,
                data={
                    "mode": "parallel_subtasks",
                    "subtasks": [s.as_dict() for s in specs],
                    "timeout_s": timeout_s,
                    "summary": f"fan-out: {len(specs)} subtarefas em worktrees",
                },
            )
        )
        try:
            for spec in specs:
                handles[spec.id] = create_worktree(project, task.id, spec.id)

            results = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        self._run_subtask_blocking,
                        agent_id=plan_roles.executor,
                        prompt=self._subtask_prompt(base_prompt, spec),
                        worktree=handles[spec.id].path,
                        timeout_s=timeout_s,
                        model=model,
                        model_flag=model_flag,
                    )
                    for spec in specs
                ],
                return_exceptions=True,
            )

            merged_files: list[str] = []
            stdout_parts: list[str] = []
            stderr_parts: list[str] = []
            applied = 0
            patch_dir = (
                self.config.orchestrator_root / "runtime" / "patches" / task.id
            )
            for spec, result in zip(specs, results):
                if isinstance(result, BaseException):
                    self._record_subtask(
                        task, spec, "failed", {"error": str(result)}
                    )
                    stderr_parts.append(f"[{spec.id}] falhou: {result}")
                    continue
                patch = collect_patch(handles[spec.id])
                files = patch_files(patch)
                if not patch.strip():
                    self._record_subtask(
                        task,
                        spec,
                        "empty",
                        {"agent_status": result.status, "files": []},
                    )
                    stdout_parts.append(f"[{spec.id}] {spec.title}: sem alterações")
                    stderr_parts.append((result.stderr or "")[-2000:])
                    continue
                ok, err = apply_patch(
                    project, patch, patch_path=patch_dir / f"{spec.id}.patch"
                )
                self._record_subtask(
                    task,
                    spec,
                    "merged" if ok else "conflict",
                    {
                        "agent_status": result.status,
                        "files": files,
                        "error": err,
                        "patch": str(patch_dir / f"{spec.id}.patch"),
                    },
                )
                if ok:
                    applied += 1
                    merged_files.extend(files)
                    stdout_parts.append(
                        f"[{spec.id}] {spec.title}: {len(files)} arquivo(s) fundido(s)"
                    )
                else:
                    # Patch preservado no disco: o conflito é retrabalho da
                    # próxima iteração, não trabalho perdido.
                    stderr_parts.append(
                        f"[{spec.id}] CONFLITO na fusão ({', '.join(files) or '?'}): {err}"
                    )
                stdout_parts.append((result.stdout or "")[-4000:])

            status = "completed" if applied else "failed"
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_COMPLETED,
                    role="executor",
                    agent=plan_roles.executor,
                    data={
                        "mode": "parallel_subtasks",
                        "merged": applied,
                        "total": len(specs),
                        "changed_files": sorted(dict.fromkeys(merged_files))[:50],
                        "summary": (
                            f"fan-out: {applied}/{len(specs)} subtarefas fundidas"
                        ),
                    },
                )
            )
            return AgentResult(
                session_id=f"fanout-{task.id}",
                agent_id=plan_roles.executor,
                role="executor",
                status=status,
                exit_code=0 if applied else 1,
                stdout="\n".join(p for p in stdout_parts if p),
                stderr="\n".join(p for p in stderr_parts if p),
                model=model,
                cwd=str(project),
                started_at=started,
                finished_at=datetime.now(timezone.utc).isoformat(),
                changed_files=sorted(dict.fromkeys(merged_files)),
            )
        finally:
            # Worktree órfão trava `git worktree add` na próxima task e ocupa
            # disco: limpeza sempre, mesmo com tudo dando errado.
            try:
                cleanup_task_worktrees(project, task.id)
            except Exception:  # noqa: BLE001
                pass

    def _record_subtask(
        self, task: TaskRecord, spec: SubtaskSpec, status: str, payload: dict[str, Any]
    ) -> None:
        try:
            self.repo.add_subtask(
                task.id,
                role="executor",
                description=spec.title,
                status=status,
                payload={**spec.as_dict(), **payload},
            )
        except Exception:  # noqa: BLE001
            pass  # registro nunca derruba a execução

    def _task_executor(self, task: TaskRecord) -> CliExecutor:
        """Executor de CLI desta task, criado uma vez e guardado no contexto.

        0.4.74 — o executor carrega `on_heartbeat` e `progress_probe`, que são
        POR TASK. Com o executor compartilhado, a segunda task a despachar um
        agente reescrevia o callback de heartbeat da primeira (batidas atribuídas
        à task errada) e trocava a sonda de silêncio dela — e a sonda é o que
        decide se um agente calado é morto ou vivo (bug-086).

        É CÓPIA RASA do executor principal, não um `CliExecutor` novo: construir
        um do zero descartaria qualquer executor injetado — dublê de teste,
        agente em quarentena, `echo` do perfil do chamador. Só os campos por task
        são reiniciados; o resto (opções, tipo, comportamento) vem de quem
        configurou o principal.
        """
        ctx = self._ctx(task)
        if ctx.executor is not None:
            return ctx.executor
        base = getattr(self, "executor", None)
        if base is None:
            return None  # type: ignore[return-value]
        if not self._concurrency_on():
            # Sem concorrência não há o que isolar, e o executor compartilhado é
            # o que o chamador configurou (echo, dublê, quarentena).
            ctx.executor = base
            return base
        executor = copy.copy(base)
        # `copy.copy` compartilharia o conjunto de PIDs com o principal, e é dele
        # que sai o `agent_active` do heartbeat: compartilhado, a task A relataria
        # "agente no ar" por causa do agente da task B.
        executor._active_pids = set()
        executor.on_heartbeat = None
        executor.progress_probe = None
        ctx.executor = executor
        return executor

    def _concurrency_on(self) -> bool:
        """Este projeto admite mais de uma task ativa?"""
        return int(self.config.limits.max_parallel_tasks or 1) > 1

    def _adapter_for(self, task: TaskRecord, adapter: Any) -> Any:
        """Adapter a usar nesta task: o do registry, ou uma cópia isolada.

        0.4.74 — com concorrência, `on_heartbeat` e `progress_probe` (atributos do
        EXECUTOR, que o adapter carrega) precisam ser por task; senão a segunda a
        despachar rouba o heartbeat da primeira e substitui a sonda de silêncio
        dela. A cópia é rasa pelo mesmo motivo do fan-out: registry novo
        descartaria adapter customizado e recarregaria os profiles do disco.

        Com teto 1 devolve o adapter ORIGINAL, intocado. Não é economia: copiar um
        adapter que guarda estado observável (contador, cache de sessão) faz o
        estado ir para a cópia e desaparecer para quem tem a referência. Sem
        concorrência não há nada a isolar, então não se paga esse risco.
        """
        if not self._concurrency_on():
            return adapter
        copia = copy.copy(adapter)
        if hasattr(copia, "executor"):
            executor = self._task_executor(task)
            if executor is not None:
                copia.executor = executor
        return copia

    def _register_heartbeat(self, task: TaskRecord, *, role: str, agent_id: str) -> None:
        """Sinal de vida do CLI durante EXECUTING.

        0.4.28 fez o heartbeat virar evento; 0.4.29 fez o evento ser PERSISTIDO
        (o bus so imprime no console de quem chamou) e a cadencia vir do perfil
        do chamador — sessao bloqueante fica muda entre um sinal e outro.
        """
        # 0.4.73 — quem o heartbeat do loop vai nomear como etapa corrente.
        self._ctx(task).current_agent = (role, agent_id)
        if getattr(self, "executor", None) is None:
            return
        # 0.4.74 — daqui para baixo tudo vai no executor DESTA task.
        executor = self._task_executor(task)
        # bug-119 — o registro durável dos PIDs lançados nasce aqui pelo mesmo
        # motivo do heartbeat: este é o ponto por onde TODO despacho passa, e
        # papel/agente/task só são conhecidos aqui.
        self._register_process_tracking(executor, task.id, role=role, agent=agent_id)

        def _emit_heartbeat(elapsed: int, pid: int, _t=task, _r=role, _a=agent_id):
            evt = RuntimeEvent(
                task_id=_t.id,
                type=EventType.AGENT_PROGRESS,
                role=_r,
                agent=_a,
                data={
                    "elapsed_s": elapsed,
                    "pid": pid,
                    "summary": f"{_r}/{_a} rodando ha {elapsed}s",
                },
            )
            try:
                self.bus.emit(evt)
                self.repo.add_event(evt)
            except Exception:  # noqa: BLE001
                pass  # sinal de vida nunca derruba a execucao

        try:
            executor.on_heartbeat = _emit_heartbeat
        except Exception:  # noqa: BLE001
            pass

        # bug-086 — watchdog de silencio. A sonda existe porque `claude -p` so
        # imprime no fim: silencio sozinho nao prova nada, silencio COM zero
        # arquivo tocado prova. Sem isso, 40 min de agente pendurado saiam do
        # orcamento do agente seguinte, que morria trabalhando.
        #
        # 0.4.74 — a sonda olha o ESCOPO da task, não a árvore inteira. Com duas
        # tasks escrevendo no mesmo projeto, a árvore inteira sempre "mudou": a
        # task A veria a escrita da B e concluiria que o próprio agente pendurado
        # está trabalhando — exatamente a prova que o bug-086 precisava, virada
        # do avesso. Sem escopo declarado o comportamento é o de antes.
        def _workspace_progress() -> bool:
            try:
                mudados = changed_files_since(
                    self.config.project_path, self._ctx(task).git_baseline
                )
                escopo = self.task_scope(task)
                if escopo:
                    mudados = [f for f in mudados if path_in_scope(f, escopo)]
                return bool(mudados)
            except Exception:  # noqa: BLE001
                # Git indisponivel/lento: sem prova de morte, nao mata.
                return True

        # 0.4.79 — o eixo OCIOSO agora é por PAPEL. Até a 0.4.78 havia um número
        # global para todo mundo: o mesmo silêncio que condena um `tester` de
        # 600s condenava um `executor` de 2400s que só imprime no fim. Papel sem
        # eixo próprio continua no global — nada muda para quem não migrou.
        try:
            executor.no_output_timeout_s = self._resolve_idle_timeout(role, task)
            executor.progress_probe = _workspace_progress
        except Exception:  # noqa: BLE001
            pass

    async def _run_agent(
        self,
        agent_id: str,
        role: str,
        prompt: str,
        task: TaskRecord,
        *,
        timeout_cap_s: int | None = None,
    ):
        self._register_heartbeat(task, role=role, agent_id=agent_id)

        adapter = self.registry.get(agent_id)
        if adapter is None or not adapter.detect().available:
            # try fallbacks from plan
            fallbacks = (task.plan or {}).get("fallbacks", {}).get(
                "executor" if role in {"executor", "corrector"} else role, []
            )
            for fb in fallbacks:
                adapter = self.registry.get(fb)
                if adapter and adapter.detect().available:
                    agent_id = fb
                    break
        if adapter is None or not adapter.detect().available:
            raise RuntimeError(f"Agente indisponivel para papel {role}: {agent_id}")

        adapter = self._adapter_for(task, adapter)

        timeout_s = self._resolve_agent_timeout(role, task)
        if timeout_cap_s is not None:
            timeout_s = min(timeout_s, int(timeout_cap_s))
        if timeout_s < MIN_AGENT_TIMEOUT_S:
            raise RuntimeError(
                f"Orçamento de tempo insuficiente para {role} "
                f"(timeout_s={timeout_s})"
            )

        from orchestrator_runtime.routing.quota import should_retry_next_model

        candidates = self.router.resolve_model_candidates(
            agent_id, task.task_type, role=role
        )
        if not candidates:
            candidates = [(None, None)]

        # Filtra modelos já esgotados neste run; se todos esgotados, tenta o 1º.
        usable = [
            c
            for c in candidates
            if (agent_id, str(c[0] or "")) not in self._ctx(task).exhausted_models
        ]
        if not usable:
            usable = list(candidates)

        last_result = None
        art_dir = self.config.orchestrator_root / "runtime" / "results" / task.id
        art_dir.mkdir(parents=True, exist_ok=True)

        for idx, (model, model_flag) in enumerate(usable):
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_STARTED,
                    role=role,
                    agent=agent_id,
                    data={
                        "model": model,
                        "timeout_s": timeout_s,
                        "model_attempt": idx + 1,
                        "model_candidates": [c[0] for c in usable],
                    },
                )
            )
            request = AgentRequest(
                role=role,
                prompt=prompt,
                model=model,
                model_flag=model_flag,
                cwd=str(self.config.project_path),
                timeout_s=timeout_s,
            )
            result = await adapter.run(request)
            result = await self._maybe_repair_and_retry(
                adapter, request, result, task=task, role=role, agent_id=agent_id
            )
            result = self._enrich_changed_files(result, task)
            last_result = result
            self.repo.add_agent_run(
                task_id=task.id,
                role=role,
                agent=agent_id,
                model=model,
                command_json=dumps(result.command),
                cwd=result.cwd,
                started_at=result.started_at,
                finished_at=result.finished_at,
                exit_code=result.exit_code,
                timed_out=1 if result.timed_out else 0,
                stdout=result.stdout[-20000:],
                stderr=result.stderr[-20000:],
                status=result.status,
                changed_files_json=dumps(result.changed_files),
            )
            out_path = art_dir / f"{role}-{agent_id}.txt"
            out_path.write_text(
                result.stdout + "\n" + result.stderr, encoding="utf-8"
            )
            self.repo.add_artifact(task.id, "agent_output", str(out_path))
            self.repo.update_agent_performance(
                agent_id,
                result.status == "completed",
                result.duration_s,
                task.last_score,
            )

            if result.status == "completed":
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=agent_id,
                        data={
                            "status": result.status,
                            "exit_code": result.exit_code,
                            "timed_out": result.timed_out,
                            "timeout_s": timeout_s,
                            "model": model,
                        },
                    )
                )
                return result

            # 0.4.25 — cota/rate-limit: tenta próximo modelo da preferência do papel
            has_next = idx + 1 < len(usable)
            if has_next and should_retry_next_model(result):
                exhausted_key = (agent_id, str(model or ""))
                self._ctx(task).exhausted_models.add(exhausted_key)
                next_model = usable[idx + 1][0]
                self.bus.emit(
                    RuntimeEvent(
                        task_id=task.id,
                        type=EventType.AGENT_COMPLETED,
                        role=role,
                        agent=agent_id,
                        data={
                            "status": "quota_exhausted",
                            "exit_code": result.exit_code,
                            "model": model,
                            "fallback_model": next_model,
                            "summary": (
                                f"cota/rate-limit em {model}; "
                                f"fallback → {next_model}"
                            ),
                        },
                    )
                )
                continue

            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.AGENT_COMPLETED,
                    role=role,
                    agent=agent_id,
                    data={
                        "status": result.status,
                        "exit_code": result.exit_code,
                        "timed_out": result.timed_out,
                        "timeout_s": timeout_s,
                        "model": model,
                    },
                )
            )
            return result

        assert last_result is not None
        self.bus.emit(
            RuntimeEvent(
                task_id=task.id,
                type=EventType.AGENT_COMPLETED,
                role=role,
                agent=agent_id,
                data={
                    "status": last_result.status,
                    "exit_code": last_result.exit_code,
                    "timed_out": last_result.timed_out,
                    "timeout_s": timeout_s,
                    "model": getattr(last_result, "model", None),
                },
            )
        )
        return last_result

    def _persist_episode(
        self, task: TaskRecord, *, success: bool, strategy: str | None = None
    ) -> None:
        content = (
            f"task={task.id} status={task.status.value} success={success} "
            f"type={task.task_type} prompt={task.prompt[:300]}"
        )
        self.repo.save_memory(
            "episode",
            content,
            task_id=task.id,
            meta={
                "status": task.status.value,
                "score": task.last_score,
                "documentation": task.documentation_review,
            },
        )
        if strategy:
            self.repo.update_strategy_performance(
                strategy, success, task.last_score
            )
        self.bus.emit(
            RuntimeEvent(task_id=task.id, type=EventType.MEMORY_UPDATED, data={"kind": "episode"})
        )
        # 0.4.14 — learn-then-compact: grava aprendizado durável ANTES de qualquer
        # compactação. Nunca compacta sem o learning já em disco.
        self._learn_then_compact(task, success=success, strategy=strategy)

    def _learn_then_compact(
        self, task: TaskRecord, *, success: bool, strategy: str | None = None
    ) -> None:
        """Save enriched learning THEN compact result artifacts (0.4.14).

        Ordem obrigatória: (1) extrair + persistir learning (SQLite kind=learning
        com meta rico + digest), export markdown + index.json, atualizar .wolf/;
        (2) só depois truncar artefatos grandes. Falha aqui nunca aborta a task.
        """
        limits = self.config.limits
        if not limits.context_compaction_enabled:
            return
        from orchestrator_runtime.memory import learnings as L

        try:
            learning = L.extract_learning(
                task,
                success=success,
                strategy=strategy,
                run_ctx=self._ctx(task).run_ctx,
            )
            digest = L.build_digest(learning, max_chars=limits.digest_max_chars)
            # Disponibiliza o digest para o result/status do MCP.
            analysis_d = dict(task.analysis or {})
            analysis_d["session_digest"] = digest
            task.analysis = analysis_d
            self.repo.save(task)

            if limits.save_learning_before_compact:
                # 1a. SQLite memory kind=learning (retrieval na próxima conversa)
                self.repo.save_memory(
                    "learning",
                    L.memory_content(learning),
                    task_id=task.id,
                    meta={**learning, "session_digest": digest},
                )
                # 1b. Markdown + index
                mem_root = self.config.orchestrator_root / "memory"
                L.write_markdown(mem_root / "learnings", learning, digest)
                L.update_index(mem_root, learning, digest)
                # 1c. .wolf/ (STATUS + cerebrum Do-Not-Repeat em pitfall)
                if limits.update_wolf_status:
                    wolf_dir = self.config.project_path / ".wolf"
                    L.update_wolf_status(wolf_dir, learning)
                    L.append_cerebrum_pitfall(wolf_dir, learning)
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.MEMORY_UPDATED,
                    data={"kind": "learning", "digest_chars": len(digest)},
                )
            )
            # 2. Compactação dos artefatos grandes — SÓ depois do learning salvo.
            # Invariante: nunca compacta sem o learning já em disco.
            if limits.save_learning_before_compact:
                results_dir = (
                    self.config.orchestrator_root / "runtime" / "results" / task.id
                )
                L.compact_result_artifacts(
                    results_dir, max_chars=limits.truncate_result_artifacts_chars
                )
        except Exception as exc:  # noqa: BLE001
            self.bus.emit(
                RuntimeEvent(
                    task_id=task.id,
                    type=EventType.MEMORY_UPDATED,
                    data={"kind": "learning", "error": str(exc)},
                )
            )

    def _export_memory_markdown(self, task: TaskRecord) -> None:
        mem_dir = self.config.orchestrator_root / "memory" / "episodes"
        mem_dir.mkdir(parents=True, exist_ok=True)
        path = mem_dir / f"{task.id}.md"
        path.write_text(
            f"# Episode {task.id}\n\n"
            f"- status: {task.status.value}\n"
            f"- score: {task.last_score}\n"
            f"- prompt: {task.prompt}\n"
            f"- documentation: {dumps(task.documentation_review)}\n",
            encoding="utf-8",
        )


def build_service(
    project_path: str | Path | None = None,
    *,
    fake_agents: bool = False,
    manager_provider: str | None = None,
    verbose: bool = True,
) -> TaskService:
    config = load_config(
        project_path, fake_agents=fake_agents, manager_provider=manager_provider
    )
    return TaskService(config, verbose=verbose)
