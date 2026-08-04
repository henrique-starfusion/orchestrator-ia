#!/usr/bin/env node
/**
 * orchestrator-guard — PreToolUse (Write|Edit|MultiEdit)
 *
 * O problema que este hook resolve: a regra "toda alteracao de codigo passa
 * pelo orquestrador" existia apenas como TEXTO em CLAUDE.md/AGENTS.md/rules.
 * Texto e advisory: o agente le, concorda e edita direto mesmo assim — foi
 * exatamente o que aconteceu na sessao de 2026-07-26, em que o proprio repo do
 * orquestrador foi evoluido inline. Sem um ponto de interceptacao, "modo
 * padrao" nunca vira comportamento padrao.
 *
 * Comportamento: bloqueia uma vez (exit 2) e devolve ao agente a instrucao de
 * orquestrar; a repeticao da operacao passa. O objetivo e forcar a decisao
 * consciente no momento certo, nao travar a sessao.
 *
 * 0.4.34 — o aviso REARMA. Ate aqui era "uma vez por sessao", e numa sessao de
 * 12h no proprio repo do orquestrador ele apareceu as 01:03 e nunca mais: 1
 * interrupcao para dezenas de arquivos de codigo editados direto. Um lembrete
 * que fala uma vez e cala nao e um ponto de interceptacao, e uma formalidade.
 * Agora ele volta a cada ORCHESTRATOR_GUARD_REARM_MIN minutos (padrao 20) e diz
 * quantos arquivos ja foram editados direto na sessao.
 *
 * Isencoes (nao bloqueia):
 *   - ORCHESTRATOR_CHILD_AGENT definido  -> voce E o executor da task
 *   - ORCHESTRATOR_GUARD=off             -> desligado explicitamente
 *   - lock de workspace ativo            -> ja existe task rodando aqui
 *   - alvo nao e codigo-fonte            -> docs, memoria, config do agente
 */

const fs = require('fs');
const path = require('path');

const SOURCE_EXT = new Set([
  '.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.cs', '.go', '.rs',
  '.java', '.kt', '.rb', '.php', '.swift', '.c', '.h', '.cpp', '.hpp',
  '.ps1', '.psm1', '.sh', '.sql', '.vue', '.svelte',
]);

// Caminhos que nunca contam como "codigo-fonte do produto".
// Comparados SEMPRE com '/': o Claude Code envia file_path com barra normal no
// Windows, entao usar path.sep aqui fazia as isencoes falharem em silencio e o
// guard bloqueava edicao em .wolf/, .claude/ e .cursor/.
const EXEMPT_PARTS = [
  '/.orchestrator/',
  '/.wolf/',
  '/.claude/',
  '/.cursor/',
  '/node_modules/',
  '/.git/',
];

function normalize(p) {
  return String(p).replace(/\\/g, '/').toLowerCase();
}

function readStdin() {
  try {
    return fs.readFileSync(0, 'utf8');
  } catch {
    return '';
  }
}

// bug-077 — higiene git em árvore compartilhada (printbee, 2026-07-30):
// SEIS quase-arrastões num dia, evitados só por disciplina do agente. Com
// trabalho não commitado de outros agentes na árvore, `git add -A` arrasta e
// `git clean/reset/checkout .` DESTRÓI trabalho alheio. Vale MESMO para o
// executor (ORCHESTRATOR_CHILD_AGENT) — higiene não é nudge de orquestração.
//
// bug-080 (2026-08-04, printbee): o guard não pode IMPEDIR edição/correção —
// o ideal é o orquestrador executar, sem travar o agente. Destrutivo em lote
// (mata trabalho alheio sem volta) segue bloqueando UMA vez; tudo o mais vira
// aviso consultivo (systemMessage, exit 0). `reset --hard <ref>` com alvo
// explícito NÃO é violação: é o sync documentado do fluxo de merge (Type 6
// do prompts.md) — o bloqueio cego a ele travava o fluxo canônico do printbee.
const GIT_DESTRUCTIVE = [
  { re: /\bgit\s+clean\b/, label: 'git clean (DESTRÓI não-rastreados alheios)' },
  { re: /\bgit\s+reset\s+--hard\s*$/, label: 'git reset --hard sem alvo (DESTRÓI não-commitados da árvore)' },
  { re: /\bgit\s+(checkout|restore)\b[^;|&]*(--\s*\.$|\s\.$|\s\*)/, label: 'git checkout/restore em lote (DESTRÓI não-commitados alheios)' },
];
const GIT_ADVISORY = [
  { re: /\bgit\s+add\s+([^;|&]*\s)?(-A\b|--all\b|-u\b|\.$|\.\s)/, label: 'git add em lote (-A/--all/-u/.)' },
  { re: /\bgit\s+commit\b[^;|&]*\s(-a\b|-am\b|--all\b)/, label: 'git commit -a/-am (stage em lote embutido)' },
  { re: /\bgit\s+stash\b/, label: 'git stash (pode enterrar trabalho alheio)' },
];

function advise(message) {
  // Consultivo: o modelo VE o aviso (systemMessage) e a operação passa.
  process.stdout.write(JSON.stringify({ systemMessage: message }));
  return 0;
}

function gitHygieneCheck(payload, root) {
  if ((process.env.ORCHESTRATOR_GUARD || '').toLowerCase() === 'off') return 0;
  const command = String((payload.tool_input || {}).command || '');
  if (!/\bgit\b/.test(command)) return 0;

  const advisoryHit = GIT_ADVISORY.find((v) => v.re.test(command));
  if (advisoryHit) {
    return advise(
      `Higiene git (árvore compartilhada): ${advisoryHit.label} pode arrastar ` +
      'trabalho não commitado de outros agentes. Prefira `git status` + ' +
      '`git add <path>...` explícito; se o lote for mesmo o pretendido, siga em frente.'
    );
  }

  const hit = GIT_DESTRUCTIVE.find((v) => v.re.test(command));
  if (!hit) return 0;

  // Destrutivo: bloqueia UMA vez por classe/sessão; repetir consciente passa.
  const sessionId = String(payload.session_id || 'sem-sessao').replace(/[^A-Za-z0-9_-]/g, '');
  const stampDir = path.join(root, '.orchestrator', 'runtime', 'guard');
  const cls = hit.label.replace(/[^A-Za-z0-9]+/g, '-').slice(0, 32);
  const stamp = path.join(stampDir, `${sessionId}.git-${cls}.notified`);
  try {
    if (fs.existsSync(stamp)) return 0;
    fs.mkdirSync(stampDir, { recursive: true });
    fs.writeFileSync(stamp, new Date().toISOString(), 'utf8');
  } catch {
    return 0;
  }

  process.stderr.write(
    [
      'HIGIENE GIT — COMANDO DESTRUTIVO EM ÁRVORE COMPARTILHADA.',
      '',
      `Comando: ${hit.label}`,
      'Este workspace pode ter trabalho NÃO COMMITADO de outros agentes —',
      'este comando apaga sem volta o que não é seu.',
      '',
      'Faça em vez disso:',
      '  git status                      # veja o que é SEU nesta task',
      '  git add <path1> <path2>         # stage explícito, só o seu',
      '  git commit -m "..."             # commit sai só com o seu trecho',
      '',
      'Se a destruição for mesmo pretendida, repita a operação — ela passa.',
    ].join('\n')
  );
  return 2;
}

function main() {
  const payload = (() => {
    try {
      return JSON.parse(readStdin() || '{}');
    } catch {
      return {};
    }
  })();

  // bug-077 — Bash/git vem ANTES das isenções: higiene vale até para executor.
  if (String(payload.tool_name || '') === 'Bash') {
    const root0 = process.env.CLAUDE_PROJECT_DIR || process.cwd();
    return gitHygieneCheck(payload, root0);
  }

  // bug-057: flag de filho e VALOR, nao presenca — vazia/'0' herdadas de
  // shells nao silenciam o guard nem fazem o agente principal virar "filho".
  const childFlag = String(process.env.ORCHESTRATOR_CHILD_AGENT || '').trim();
  if (childFlag && childFlag !== '0') return 0;
  if ((process.env.ORCHESTRATOR_GUARD || '').toLowerCase() === 'off') return 0;

  const root = process.env.CLAUDE_PROJECT_DIR || process.cwd();

  // Task do orquestrador ja segurando o workspace: a edicao e dela.
  const lockDir = path.join(root, '.orchestrator', 'runtime', 'locks');
  try {
    const locks = fs.readdirSync(lockDir).filter((f) => f.endsWith('.lock'));
    if (locks.length > 0) return 0;
  } catch {
    /* sem diretorio de lock: segue */
  }

  const input = payload.tool_input || {};
  const target = String(input.file_path || input.path || '');
  if (!target) return 0;

  const lowered = normalize(target);
  if (EXEMPT_PARTS.some((p) => lowered.includes(p))) return 0;
  if (!SOURCE_EXT.has(path.extname(lowered))) return 0;

  // Marcador por SESSAO (session_id do payload, senao o guard dispararia uma
  // unica vez na vida do workspace) — mas com REARME por tempo, para o lembrete
  // nao morrer no primeiro aviso de uma sessao longa.
  const sessionId = String(payload.session_id || 'sem-sessao').replace(
    /[^A-Za-z0-9_-]/g,
    ''
  );
  const stampDir = path.join(root, '.orchestrator', 'runtime', 'guard');
  const stamp = path.join(stampDir, `${sessionId}.notified`);

  const rearmMin = Number(process.env.ORCHESTRATOR_GUARD_REARM_MIN || 20);
  const now = Date.now();
  let edits = 0;
  let lastAt = 0;
  try {
    // replace(/^﻿/) : ferramenta que reescreva o marcador no Windows pode
    // deixar BOM (Set-Content -Encoding UTF8 do PS 5.1 deixa), e o JSON.parse
    // quebraria em silencio — o contador zerava e o guard reiniciava a contagem.
    const raw = fs.readFileSync(stamp, 'utf8').replace(/^﻿/, '');
    const prev = JSON.parse(raw);
    edits = Number(prev.edits) || 0;
    lastAt = Number(prev.last_at) || 0;
  } catch {
    /* primeiro aviso da sessao, ou marcador do formato antigo (texto puro) */
  }
  edits += 1;

  // rearmMin <= 0 desliga o rearme e volta ao "uma vez por sessao".
  const silent = lastAt > 0 && (rearmMin <= 0 || now - lastAt < rearmMin * 60000);
  try {
    fs.mkdirSync(stampDir, { recursive: true });
    fs.writeFileSync(
      stamp,
      JSON.stringify({
        edits,
        last_at: silent ? lastAt : now,
        last_iso: new Date(silent ? lastAt : now).toISOString(),
      }),
      'utf8'
    );
  } catch {
    return 0; // nao conseguiu marcar: nao insiste
  }
  if (silent) return 0;

  const placar =
    edits > 1
      ? `${edits} arquivos de codigo-fonte editados direto nesta sessao (este e o ${edits}o).`
      : 'Primeira edicao de codigo-fonte desta sessao.';

  // bug-080 (2026-08-04, printbee): consultivo, NUNCA bloqueante — o ideal é
  // o orquestrador executar a tarefa, mas o agente não pode ser impedido de
  // editar/corrigir. O aviso aparece ao modelo (systemMessage) na cadência
  // do rearm; a edição sempre passa.
  return advise(
    [
      'ORQUESTRADOR NAO ACIONADO (aviso consultivo — a edição passa normalmente).',
      `Alvo: ${path.basename(target)}. ${placar}`,
      'Neste projeto, alterar código-fonte é gatilho de orquestração — ver',
      'CLAUDE.md / AGENTS.md, seção "Como usar o Orquestrador".',
      'Prefira: orchestrator run --prompt "<atividade com critérios de aceitação>"',
      '(loops: /loop-bug|mvp|landing|conteudo|saas|ui-probe|review|research),',
      'ou via MCP: orchestrator_run -> orchestrator_status -> orchestrator_result.',
      'Se a edição for mesmo o caminho certo (typo, ajuste pontual, correção',
      'direta), siga em frente — nada está bloqueado. O lembrete volta daqui a',
      `${rearmMin} min de edição direta. Desligar: ORCHESTRATOR_GUARD=off.`,
    ].join(' ')
  );
}

process.exit(main());
