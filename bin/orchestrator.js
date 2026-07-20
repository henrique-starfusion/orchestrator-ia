#!/usr/bin/env node
'use strict';

/**
 * CLI no estilo OpenWolf/Graphify:
 *   npx @starfusion/orchestrator init
 *   orchestrator init
 *   orchestrator route|dispatch|update|verify|...
 */

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const packageRoot = path.resolve(__dirname, '..');
const installScript = path.join(packageRoot, 'scripts', 'Install-Orchestrator.ps1');

function printHelp() {
  const help = `
@starfusion/orchestrator — Orquestrador Multiagente (StarFusion)

Uso (na pasta do projeto):
  orchestrator init|update|verify|status|analyze|global-tools
  orchestrator route --task-class <class> [--client cursor|claude|codex|auto]
  orchestrator dispatch --task-class <class> --prompt "..." [--client claude]

Roteamento de modelos (obrigatorio para subagentes Cursor):
  Task SEM model= herda o modelo do pai (ex.: Grok em tudo) — isso e bug de uso.
  Use: orchestrator route --task-class complex_analysis --client cursor
  Depois: Task com model="<slug retornado>"

Exemplos:
  orchestrator route --task-class docs --client cursor --json
  orchestrator route --task-class complex_analysis --client claude
  orchestrator dispatch --task-class docs --client claude --prompt "Atualize o README"
`.trim();
  console.log(help);
}

function mapCommand(raw) {
  if (!raw || raw === 'init' || raw === 'i') return 'install';
  if (raw === 'upgrade') return 'update';
  return raw;
}

function parseArgs(argv) {
  const out = {
    command: 'install',
    projectPath: process.cwd(),
    passthrough: [],
    help: false,
  };

  const args = [...argv];
  if (args.length === 0) {
    out.command = 'install';
    return out;
  }

  const first = args[0];
  if (first === '-h' || first === '--help' || first === 'help') {
    out.help = true;
    return out;
  }

  const known = new Set([
    'init', 'i', 'install', 'verify', 'update', 'upgrade', 'repair', 'uninstall',
    'status', 'analyze', 'skills', 'global-tools', 'route', 'dispatch',
  ]);

  if (known.has(first) || !first.startsWith('-')) {
    out.command = mapCommand(first);
    args.shift();
  }

  for (let i = 0; i < args.length; i += 1) {
    const a = args[i];
    if (a === '-h' || a === '--help') {
      out.help = true;
      continue;
    }
    if (a === '--project' || a === '-ProjectPath' || a === '-Project') {
      out.projectPath = path.resolve(args[i + 1] || process.cwd());
      i += 1;
      continue;
    }
    if (a.startsWith('--project=')) {
      out.projectPath = path.resolve(a.slice('--project='.length));
      continue;
    }

    const valueFlags = {
      '--task-class': '-TaskClass',
      '-TaskClass': '-TaskClass',
      '--prompt': '-Prompt',
      '-Prompt': '-Prompt',
      '--client': '-Client',
      '-Client': '-Client',
    };

    if (valueFlags[a]) {
      const val = args[i + 1];
      if (val !== undefined) {
        out.passthrough.push(valueFlags[a], val);
        i += 1;
      }
      continue;
    }

    if (a.startsWith('--task-class=')) {
      out.passthrough.push('-TaskClass', a.slice('--task-class='.length));
      continue;
    }
    if (a.startsWith('--prompt=')) {
      out.passthrough.push('-Prompt', a.slice('--prompt='.length));
      continue;
    }
    if (a.startsWith('--client=')) {
      out.passthrough.push('-Client', a.slice('--client='.length));
      continue;
    }

    const flagMap = {
      '--dry-run': '-DryRun',
      '--force': '-Force',
      '--non-interactive': '-NonInteractive',
      '--update-agents': '-UpdateAgents',
      '--install-missing-agents': '-InstallMissingAgents',
      '--skip-agent-probes': '-SkipAgentProbes',
      '--skip-tools': '-SkipTools',
      '--refresh-tools': '-RefreshTools',
      '--init-tools': '-InitTools',
      '--skip-tool-init': '-SkipToolInit',
      '--skip-global-tools': '-SkipGlobalTools',
      '--configure-mcps': '-ConfigureMcps',
      '--run-smoke-test': '-RunSmokeTest',
      '--run-project-tests': '-RunProjectTests',
      '--legacy-cleanup': '-LegacyCleanup',
      '--verbose': '-Verbose',
      '--json': '-Json',
      '--print-only': '-PrintOnly',
    };

    if (flagMap[a]) {
      out.passthrough.push(flagMap[a]);
      continue;
    }

    if (a.startsWith('-')) {
      out.passthrough.push(a);
      continue;
    }

    out.passthrough.push(a);
  }

  return out;
}

function findPowerShell() {
  const candidates = process.platform === 'win32'
    ? ['powershell.exe', 'pwsh.exe']
    : ['pwsh', 'powershell'];

  for (const name of candidates) {
    const probe = spawnSync(name, ['-NoProfile', '-Command', '$PSVersionTable.PSVersion.ToString()'], {
      encoding: 'utf8',
      windowsHide: true,
    });
    if (probe.status === 0) return name;
  }
  return null;
}

function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.help) {
    printHelp();
    process.exit(0);
  }

  if (!fs.existsSync(installScript)) {
    console.error('[ERRO] Pacote incompleto: scripts/Install-Orchestrator.ps1 ausente.');
    process.exit(1);
  }

  if (!fs.existsSync(parsed.projectPath)) {
    console.error(`[ERRO] Projeto nao encontrado: ${parsed.projectPath}`);
    process.exit(2);
  }

  const shell = findPowerShell();
  if (!shell) {
    console.error('[ERRO] PowerShell nao encontrado.');
    process.exit(4);
  }

  const psArgs = [
    '-NoProfile',
    '-NonInteractive',
    '-ExecutionPolicy', 'Bypass',
    '-File', installScript,
    parsed.command,
    '-ProjectPath', parsed.projectPath,
    '-PackageRoot', packageRoot,
    '-NonInteractive',
    ...parsed.passthrough,
  ];

  console.log(`[orchestrator] pacote:  ${packageRoot}`);
  console.log(`[orchestrator] projeto: ${parsed.projectPath}`);
  console.log(`[orchestrator] comando: ${parsed.command}`);
  console.log(`[orchestrator] host:    ${os.platform()} / ${shell}`);

  const result = spawnSync(shell, psArgs, {
    stdio: 'inherit',
    windowsHide: true,
  });

  if (result.error) {
    console.error(`[ERRO] Falha ao iniciar PowerShell: ${result.error.message}`);
    process.exit(1);
  }

  process.exit(result.status === null ? 1 : result.status);
}

main();
