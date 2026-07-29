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

function main() {
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

  process.stderr.write(
    [
      'ORQUESTRADOR NAO ACIONADO.',
      '',
      `Alvo: ${path.basename(target)}`,
      placar,
      'Neste projeto, alterar codigo-fonte e um gatilho de orquestracao — ver',
      'CLAUDE.md / AGENTS.md, secao "Como usar o Orquestrador".',
      '',
      'Faca em vez disso:',
      '  orchestrator run --prompt "<atividade com criterios de aceitacao>"',
      '  (loops: --loop bug|mvp|landing|conteudo|saas, ou prefixo /loop-bug)',
      'Via MCP: orchestrator_run -> orchestrator_status -> orchestrator_result.',
      '',
      'Se a edicao for mesmo trivial (typo, comentario, formatacao sem mudanca',
      'de logica), repita a operacao — ela passa. O aviso volta daqui a',
      `${rearmMin} min de edicao direta, para a excecao nao virar o padrao.`,
      'Desligar de vez nesta sessao: ORCHESTRATOR_GUARD=off.',
    ].join('\n')
  );
  return 2;
}

process.exit(main());
