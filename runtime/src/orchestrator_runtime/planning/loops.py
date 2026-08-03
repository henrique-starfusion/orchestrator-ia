"""Loops de execução — roteiros nomeados, escolhidos pelo que o usuário pede.

Um prompt termina numa resposta; um loop termina num resultado verificado. Cada
loop declara as ETAPAS que o executor precisa cumprir e os CRITÉRIOS que fecham
o trabalho, de modo que o agente não pare porque "acha" que concluiu.

Seleção: automática por palavra-chave do prompt (`detect_loop`), com override
explícito via `orchestrator run --loop <id>`. Sem match, o orquestrador segue o
comportamento padrão — nenhum loop é imposto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from orchestrator_runtime.tasks.models import (
    AcceptanceCriterion,
    CriterionCheck,
    CriterionKind,
)


@dataclass(frozen=True)
class LoopSpec:
    id: str
    title: str
    goal: str
    task_type: str
    stages: tuple[str, ...]
    criteria: tuple[tuple[str, CriterionKind], ...]
    done_when: str
    keywords: tuple[str, ...] = field(default=())

    def to_criteria(self) -> list[AcceptanceCriterion]:
        out: list[AcceptanceCriterion] = []
        for idx, (description, kind) in enumerate(self.criteria, start=1):
            out.append(
                AcceptanceCriterion(
                    id=f"AC-{idx:03d}",
                    description=description,
                    kind=kind,
                    check=CriterionCheck(kind=kind, params={}),
                    required=True,
                )
            )
        return out

    def briefing(self) -> str:
        """Bloco injetado no prompt do executor."""
        etapas = "\n".join(
            f"  {i}. {s}" for i, s in enumerate(self.stages, start=1)
        )
        return (
            f"Loop de execução: /{self.id} — {self.title}\n"
            f"Objetivo do loop: {self.goal}\n"
            f"Cumpra as etapas NA ORDEM, sem pular:\n{etapas}\n"
            f"Concluído quando: {self.done_when}\n"
            "Não declare conclusão por impressão: cada etapa precisa de "
            "evidência (arquivo, saída de comando ou teste)."
        )


_EVID = CriterionKind.EVIDENCE
_WORK = CriterionKind.WORKSPACE_CHANGES
_TEST = CriterionKind.TESTS_PASS

LOOPS: dict[str, LoopSpec] = {
    "bug": LoopSpec(
        id="bug",
        title="correção de defeito com prova",
        goal=(
            "Não apenas 'corrigir o erro': reproduzir o problema, achar a causa "
            "raiz, criar o teste que falha e validar a correção."
        ),
        task_type="implementation",
        stages=(
            # bug-069 — task 8193684389b1 (printbee): bug de renderização no
            # navegador; nem executor nem validador CLI abrem browser, e o
            # validador reprovou 2x por falta de "evidência" impossível.
            # Escopo explícito do que conta como evidência para bug de UI.
            "Reproduzir o defeito e registrar a evidência (comando + saída). "
            "Bug de UI/renderização: evidência = teste que falha, DOM/snapshot "
            "do HTML gerado ou análise estática do código de render — agentes "
            "CLI não abrem navegador.",
            "Diagnosticar a causa raiz; conferir todos os chamadores afetados.",
            "Escrever o teste que FALHA por causa do defeito.",
            "Corrigir no ponto comum a todos os chamadores, não no sintoma.",
            "Rodar o teste e a suíte; anexar a saída.",
        ),
        criteria=(
            (
                "Defeito reproduzido com evidência registrada (comando+saída, "
                "teste que falha ou log; bug de UI/renderização: DOM, snapshot "
                "do HTML gerado ou análise estática — não exigir screenshot de "
                "navegador de agentes CLI)",
                _EVID,
            ),
            ("Causa raiz identificada e corrigida no código", _WORK),
            ("Teste de regressão cobre o defeito e passa", _TEST),
        ),
        done_when="o teste que falhava passa e a suíte segue verde",
        keywords=(
            "bug", "erro", "erros", "falha*", "quebrad*", "corrig*",
            "conserta*", "fix", "stacktrace", "traceback", "exception",
            "nao funciona", "não funciona", "regressao", "regressão",
            "defeito*",
        ),
    ),
    "ui-probe": LoopSpec(
        id="ui-probe",
        title="sonda empírica e segura de UI",
        goal=(
            "Produzir prova empírica de UI: navegar e clicar nas superfícies "
            "priorizadas para capturar o que quebra, em vez de auditar código."
        ),
        task_type="complex_analysis",
        stages=(
            "Preparar a sonda: usar o Playwright MCP se disponível; caso "
            "contrário, executar npx playwright com cache "
            "~/.cache/ms-playwright e manter qualquer script descartável fora "
            "do repositório.",
            "Definir e respeitar o boundary de segurança: exercer livremente "
            "controles NÃO-mutantes (tabs, filtros, ordenação, paginação e "
            "modais somente para abrir/cancelar); NUNCA clicar em Salvar, "
            "Bloquear, Excluir, Aprovar ou submits em dado real. Em dúvida, "
            "não clicar e listar o controle como 'não exercido'.",
            "Localizar controles por ROLE com getByRole/getByLabel, nunca com "
            "getByText exato.",
            "Armar listeners ANTES do clique: response HTTP >=400, console "
            "error, requestfailed e WebSocket.",
            "Consolidar o roadmap em tabela superfície/controle | ação | "
            "resultado | veredito | tag, com tags do vocabulário fixo, e "
            "encerrar com o Top 3 must-fix.",
        ),
        criteria=(
            (
                "Relatório da sonda com tabela por superfície/controle e tags "
                "do vocabulário fixo",
                _EVID,
            ),
            (
                "Capturas de listeners (HTTP 4xx/5xx, console, WebSocket) "
                "anexadas ou descritas",
                _EVID,
            ),
            (
                "Screenshots ou trace salvos fora do repo, com caminho "
                "registrado",
                _EVID,
            ),
        ),
        done_when=(
            "todas as superfícies priorizadas foram sondadas e o roadmap tem "
            "veredito por item"
        ),
        keywords=(
            "sonda", "probe", "ui", "visual", "tela", "playwright", "demo",
            "renderiza", "navegador", "browser",
        ),
    ),
    "review": LoopSpec(
        id="review",
        title="revisão adversarial do código no HEAD",
        goal=(
            "Caçar o que está ERRADO no que acabou de ser entregue — não "
            "verificar entregas; fazer leitura adversarial do código no HEAD."
        ),
        task_type="complex_analysis",
        stages=(
            "Fazer identity priming OBRIGATÓRIO com quatro papéis: SRE acordado "
            "às 3h por um cenário de falha real; engenheiro de "
            "segurança/privacidade; arquiteto perguntando 'se escalar 10x, o "
            "que quebra primeiro'; engenheiro júnior perguntando 'o que isto "
            "faz e por que está certo'.",
            "Responder cinco temas fixos nesta ordem: correção/races/ordenação; "
            "Edge cases que produzem dado errado ou perdido; Pontos cegos de "
            "operação; Fragilidades e partes que parecem prontas mas não estão; "
            "Melhorias mesmo onde está correto.",
            "Aplicar 'do NOT pad findings': pergunta sem achado real recebe "
            "'sem achados porque <razão>', nunca enchimento cosmético.",
            "Registrar findings com file:line e reprodutor mínimo em prosa "
            "para cada finding crítico.",
            "Sintetizar o Top 5 ranqueado, 'parece pronto mas não está' e 'o "
            "que eu mudaria se fosse meu'; fechar com tabela ordenada por "
            "severidade — a tabela vai NO FIM, não no início.",
        ),
        criteria=(
            ("Findings das 5 perguntas com evidência file:line", _EVID),
            (
                "Síntese com Top 5 ranqueado por severidade e tabela final "
                "ordenada",
                _WORK,
            ),
            (
                "Reprodutores mínimos em prosa para os findings críticos",
                _EVID,
            ),
            (
                "Hashes sha256 dos artefatos-chave inspecionados registrados",
                _EVID,
            ),
        ),
        done_when=(
            "as 5 perguntas foram respondidas com evidência e a tabela de "
            "severidade está completa"
        ),
        keywords=(
            "review", "revisão", "revisao", "adversarial", "deep dive",
            "sanity", "auditoria profunda", "caçar bugs", "cacar bugs",
        ),
    ),
    "mvp": LoopSpec(
        id="mvp",
        title="ideia até MVP que roda",
        goal="Transformar uma ideia em MVP funcional que abre e executa.",
        task_type="implementation",
        stages=(
            "Planejar o escopo mínimo que entrega valor (nada além disso).",
            "Construir a aplicação.",
            "Executar de verdade e capturar o resultado.",
            "Corrigir os erros encontrados na execução.",
            "Repetir execução+correção até abrir sem erro.",
        ),
        criteria=(
            ("Aplicação criada no workspace com escopo mínimo definido", _WORK),
            ("Projeto executa sem erro; saída de execução anexada", _EVID),
            ("Teste ou verificação determinística cobre o caminho principal", _TEST),
        ),
        done_when="o projeto abre/executa sem erro",
        keywords=(
            "mvp", "prototip*", "protótip*", "do zero", "criar um app",
            "criar app", "nova aplicacao", "nova aplicação", "novo projeto",
            "ideia em", "poc",
        ),
    ),
    "landing": LoopSpec(
        id="landing",
        title="auditoria de landing page",
        goal=(
            "Avaliar a página em oferta, copy, clareza, mobile e conversão, com "
            "recomendação priorizada por impacto."
        ),
        task_type="complex_analysis",
        stages=(
            "Levantar a página e o público-alvo declarado.",
            "Avaliar OFERTA: proposta de valor e prova.",
            "Avaliar COPY: título, subtítulo e CTA.",
            "Avaliar CLAREZA: o que é, para quem, próximo passo.",
            "Avaliar MOBILE: hierarquia e legibilidade em tela pequena.",
            "Avaliar CONVERSÃO: atrito do formulário e do CTA.",
            "Priorizar as correções por impacto estimado.",
        ),
        criteria=(
            ("Relatório da auditoria gravado no workspace", _EVID),
            ("Os 5 eixos avaliados: oferta, copy, clareza, mobile, conversão", _EVID),
            ("Recomendações priorizadas por impacto", _EVID),
        ),
        done_when="os 5 eixos têm veredito e as ações estão priorizadas",
        keywords=(
            "landing", "lp ", "pagina de venda*", "página de venda*",
            "conversao", "conversão", "cta", "copy da pagina",
            "copy da página", "checkout",
        ),
    ),
    "conteudo": LoopSpec(
        id="conteudo",
        title="conteúdo com crítica antes de publicar",
        goal=(
            "Pesquisar ângulos, escrever variações, criticar sem dó e escolher a "
            "mais forte — em vez de aceitar o primeiro rascunho."
        ),
        task_type="docs",
        stages=(
            "Pesquisar o tema e listar ângulos possíveis.",
            "Escrever ao menos 3 variações distintas.",
            "Criticar cada variação (o que enfraquece o texto).",
            "Melhorar a mais forte com base na crítica.",
            "Registrar a escolhida e o porquê.",
        ),
        criteria=(
            ("Ângulos pesquisados e listados", _EVID),
            ("Pelo menos 3 variações escritas e criticadas", _EVID),
            ("Versão final escolhida com justificativa registrada", _EVID),
        ),
        done_when="a variação escolhida está justificada por escrito",
        keywords=(
            "conteudo", "conteúdo", "post", "artigo", "copy", "newsletter",
            "roteiro", "legenda", "thread", "carrossel",
        ),
    ),
    "saas": LoopSpec(
        id="saas",
        title="entrega multidisciplinar com revisão final",
        goal=(
            "Tratar a entrega como uma pequena equipe: produto, desenvolvimento, "
            "marketing e validação, com um revisor final independente."
        ),
        task_type="implementation",
        stages=(
            "PRODUTO: definir escopo, usuário e critério de sucesso.",
            "DESENVOLVIMENTO: implementar o escopo definido.",
            "MARKETING: escrever a comunicação da entrega (o que mudou e por quê).",
            "VALIDAÇÃO: verificar contra o critério de sucesso do produto.",
            "REVISÃO FINAL: revisar a entrega inteira antes de fechar.",
        ),
        criteria=(
            ("Escopo de produto e critério de sucesso registrados", _EVID),
            ("Implementação presente no workspace", _WORK),
            ("Validação executada contra o critério de sucesso", _TEST),
            ("Revisão final da entrega registrada", _EVID),
        ),
        done_when="a revisão final aprova a entrega contra o critério de produto",
        keywords=(
            "saas", "produto completo", "end to end", "end-to-end",
            "ponta a ponta", "feature completa", "lancar", "lançar",
            "go-live", "release completa",
        ),
    ),
    "research": LoopSpec(
        id="research",
        title="pesquisa na internet com relatório verificado",
        goal=(
            "Pesquisa web com entrega auditável — padrão Lead→Researchers→"
            "Analyst→Writer do demo research-agent da Anthropic (SDK), adaptado "
            "para UM executor sequencial de QUALQUER CLI (claude, codex, kimi, "
            "gemini, opencode): decompor, pesquisar com a busca web do próprio "
            "agente, extrair dados, redigir relatório com citações."
        ),
        task_type="docs",
        stages=(
            "DECOMPOR o tópico em 2-4 subtemas e gravar o plano em "
            ".orchestrator/runtime/results/research/00-plano.md (subtemas, "
            "perguntas-chave, o que conta como fonte boa).",
            "PESQUISAR cada subtema com a ferramenta de busca web do SEU CLI "
            "(WebSearch/web.run/google_search — a que existir). Se o CLI NÃO "
            "tiver busca web disponível, declare a limitação no plano e siga "
            "só com o acesso que tiver — nunca simule pesquisa. Gravar uma nota "
            "por subtema em .orchestrator/runtime/results/research/notes/ com "
            "URLs citadas por afirmação.",
            "EXTRAIR dados quantitativos das notas (percentuais, rankings, "
            "datas, valores) em .orchestrator/runtime/results/research/data/ e "
            "gerar gráficos (python gerenciado + matplotlib) em .../charts/. "
            "Sem dados quantitativos relevantes? Grave 'sem dados "
            "quantitativos' — não invente números.",
            "REDIGIR o relatório final em .orchestrator/runtime/results/"
            "research/reports/ (PDF se reportlab disponível, senão Markdown): "
            "seção por subtema, citações por afirmação, gráficos embutidos ou "
            "referenciados.",
            "REVISÃO DE HONESTIDADE: todo número do relatório rastreia para "
            "uma nota com URL; lacunas marcadas explicitamente ('não "
            "encontrado') em vez de preenchidas com conhecimento interno.",
        ),
        criteria=(
            (
                "Plano com 2-4 subtemas gravado em results/research/00-plano.md",
                _EVID,
            ),
            (
                "Uma nota por subtema em results/research/notes/ com URLs "
                "citadas por afirmação",
                _EVID,
            ),
            (
                "Relatório final em results/research/reports/ com citações e "
                "lacunas marcadas explicitamente",
                _EVID,
            ),
            (
                "Gráficos em results/research/charts/ OU registro explícito de "
                "'sem dados quantitativos'",
                _EVID,
            ),
        ),
        done_when=(
            "o relatório final tem toda afirmação rastreada para nota com URL "
            "e nenhuma lacuna preenchida sem marcação"
        ),
        keywords=(
            "pesquisa", "pesquisar", "pesquise", "research", "investigue",
            "investigar", "levantamento", "tendencias", "tendências",
            "analise de mercado", "análise de mercado", "fact check",
            "fact-check", "verificar claim", "busque na internet",
            "buscar na internet",
        ),
    ),
}

# Verbo de implementação vence "conteudo"/"landing" quando o pedido é de código.
_IMPL_INTENT_RE = re.compile(
    r"\b(implement\w*|refator\w*|codific\w*|programa\w*|cri(?:e|ar) (?:o )?(?:m[oó]dulo|script|endpoint|servi[çc]o))\b",
    re.IGNORECASE,
)

# Correção explícita continua sendo bug mesmo quando o pedido também exige uma
# revisão adversarial; a relação verbo+defeito evita promover menções soltas.
_BUG_FIX_INTENT_RE = re.compile(
    r"\b(?:corrig\w*|consert\w*|fix(?:e[ds]?|ing)?|repar\w*)\b"
    r"[^.!?;\n]{0,100}"
    r"\b(?:bugs?|erros?|falhas?|defeitos?)\b",
    re.IGNORECASE,
)


# Override explícito no início do prompt: "/loop-bug ..." ou "/bug ...".
_EXPLICIT_RE = re.compile(r"^\s*/(?:loop[-_])?([a-z0-9_-]{2,20})\b", re.IGNORECASE)

# bug-045 — cláusula condicional não é o pedido principal: "se gap for bug,
# corrigir com testes" descrevia um ramo hipotético e ligava o loop de bug numa
# task de publicação de docs. O lookbehind poupa reflexivos ("trata-se").
_CONDITIONAL_CLAUSE_RE = re.compile(
    r"(?<![\w-])(?:se|caso|if)\b[^.!?;\n]{0,160}",
    re.IGNORECASE,
)

# bug-045 — 1 hit incidental num prompt longo (specs de 1500+ chars citando
# "erros"/"mvp" de passagem) não define o roteiro da task inteira. Em prompt
# curto, a palavra-chave É o assunto.
_SHORT_PROMPT_LEN = 240


def _kw_regex(kw: str) -> re.Pattern[str]:
    """Palavra inteira; sufixo ``*`` marca radical ("corrig*" → corrigir/ido).

    Sem fronteira, "erro" casava dentro de "errors" (inglês) e "lp " dentro de
    qualquer palavra — bug-045.
    """
    stem = kw.endswith("*")
    body = re.escape(kw[:-1] if stem else kw)
    return re.compile(r"\b" + body + (r"\w*" if stem else r"\b"))


_KEYWORD_RES: dict[str, tuple[re.Pattern[str], ...]] = {
    loop_id: tuple(_kw_regex(kw) for kw in spec.keywords)
    for loop_id, spec in LOOPS.items()
}


def detect_loop(prompt: str) -> str | None:
    """Loop mais provável para o pedido; None quando nada casa com folga."""
    text = (prompt or "").lower()
    if not text.strip():
        return None

    # Prefixo explícito vence qualquer heurística.
    explicit = _EXPLICIT_RE.match(text)
    if explicit and explicit.group(1) in LOOPS:
        return explicit.group(1)

    scan = _CONDITIONAL_CLAUSE_RE.sub(" ", text)
    scores: dict[str, int] = {}
    for loop_id, patterns in _KEYWORD_RES.items():
        hits = sum(1 for pat in patterns if pat.search(scan))
        if hits:
            scores[loop_id] = hits
    if not scores:
        return None
    if max(scores.values()) < 2 and len(text) > _SHORT_PROMPT_LEN:
        return None

    # Pedido de código não vira auditoria de landing nem produção de conteúdo.
    if _IMPL_INTENT_RE.search(text):
        for soft in ("landing", "conteudo"):
            scores.pop(soft, None)
        if not scores:
            return None

    # Um review pode repetir várias keywords do próprio roteiro. Quando há
    # intenção inequívoca de corrigir um defeito, o loop-bug ainda prevalece.
    if (
        "bug" in scores
        and "review" in scores
        and _BUG_FIX_INTENT_RE.search(scan)
    ):
        return "bug"

    # bug vence mvp: "corrigir o app" é defeito, não projeto novo.
    best = max(scores.values())
    finalists = sorted(k for k, v in scores.items() if v == best)
    if "bug" in finalists:
        return "bug"
    return finalists[0]


def get_loop(loop_id: str | None) -> LoopSpec | None:
    if not loop_id:
        return None
    return LOOPS.get(str(loop_id).strip().lower().lstrip("/"))
