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
 * Comportamento: na PRIMEIRA edicao de codigo-fonte da sessao, bloqueia uma vez
 * (exit 2) e devolve ao agente a instrucao de orquestrar. Depois disso, libera —
 * o objetivo e forcar a decisao consciente no momento certo, nao travar a sessao.
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

function main() {
  if (process.env.ORCHESTRATOR_CHILD_AGENT) return 0;
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

  let payload = {};
  try {
    payload = JSON.parse(readStdin() || '{}');
  } catch {
    return 0;
  }
  const input = payload.tool_input || {};
  const target = String(input.file_path || input.path || '');
  if (!target) return 0;

  const lowered = normalize(target);
  if (EXEMPT_PARTS.some((p) => lowered.includes(p))) return 0;
  if (!SOURCE_EXT.has(path.extname(lowered))) return 0;

  // Uma interrupcao por SESSAO: o marcador leva o session_id do payload, senao
  // o guard dispararia uma unica vez na vida do workspace.
  const sessionId = String(payload.session_id || 'sem-sessao').replace(
    /[^A-Za-z0-9_-]/g,
    ''
  );
  const stampDir = path.join(root, '.orchestrator', 'runtime', 'guard');
  const stamp = path.join(stampDir, `${sessionId}.notified`);
  try {
    if (fs.existsSync(stamp)) return 0;
    fs.mkdirSync(stampDir, { recursive: true });
    fs.writeFileSync(stamp, new Date().toISOString(), 'utf8');
  } catch {
    return 0; // nao conseguiu marcar: nao insiste
  }

  process.stderr.write(
    [
      'ORQUESTRADOR NAO ACIONADO.',
      '',
      `Voce esta prestes a editar codigo-fonte direto: ${path.basename(target)}`,
      'Neste projeto, alterar codigo-fonte e um gatilho de orquestracao — ver',
      'CLAUDE.md / AGENTS.md, secao "Como usar o Orquestrador".',
      '',
      'Faca em vez disso:',
      '  orchestrator run --prompt "<atividade com criterios de aceitacao>"',
      '  (loops: --loop bug|mvp|landing|conteudo|saas, ou prefixo /loop-bug)',
      'Via MCP: orchestrator_run -> orchestrator_status -> orchestrator_result.',
      '',
      'Se a edicao for mesmo trivial (typo, comentario, formatacao sem mudanca',
      'de logica), repita a operacao: este aviso so aparece uma vez por sessao.',
    ].join('\n')
  );
  return 2;
}

process.exit(main());
