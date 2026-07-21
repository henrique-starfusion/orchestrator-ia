#!/usr/bin/env node
'use strict';

/**
 * CLI @starfusion/orchestrator
 *   Instalador  → PowerShell (Install-Orchestrator.ps1)
 *   Runtime     → Python (orchestrator_runtime)
 */

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

const packageRoot = path.resolve(__dirname, '..');
const installScript = path.join(packageRoot, 'scripts', 'Install-Orchestrator.ps1');
const runtimeSrc = path.join(packageRoot, 'runtime', 'src');

function printHelp() {
  const help = `
@starfusion/orchestrator — Orquestrador Multiagente (StarFusion)

Installer:
  orchestrator init|update|verify|repair|uninstall|status|analyze
  orchestrator global-tools          # opt-in: MCPs/plugins/skills no perfil
  orchestrator route|dispatch        # roteamento / despacho unico

Runtime (persistente):
  orchestrator run --prompt "..."
  orchestrator task create|run|status|list|cancel|resume|logs|artifacts

Exemplos:
  orchestrator install --skip-global-tools
  orchestrator run --prompt "Crie modulo soma com testes e docs"
  orchestrator task status <id>
`.trim();
  console.log(help);
}

function mapCommand(raw) {
  if (!raw || raw === 'init' || raw === 'i') return 'install';
  if (raw === 'upgrade') return 'update';
  return raw;
}

function isRuntimeCommand(command, argv) {
  if (command === 'run') return true;
  if (command === 'task') return true;
  // `orchestrator task ...` when parse puts task as command
  return false;
}

function parseArgs(argv) {
  const out = {
    command: 'install',
    projectPath: process.cwd(),
    passthrough: [],
    runtimeArgs: [],
    help: false,
    raw: [...argv],
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
    'run', 'task', 'tools',
  ]);

  if (known.has(first) || !first.startsWith('-')) {
    out.command = mapCommand(first);
    args.shift();
  }

  // Runtime: preserve remaining args almost as-is
  if (out.command === 'run' || out.command === 'task' || out.command === 'tools') {
    out.runtimeArgs = args;
    // still extract --project for logging
    for (let i = 0; i < args.length; i += 1) {
      if (args[i] === '--project' || args[i] === '-ProjectPath') {
        out.projectPath = path.resolve(args[i + 1] || process.cwd());
        break;
      }
      if (args[i].startsWith('--project=')) {
        out.projectPath = path.resolve(args[i].slice('--project='.length));
        break;
      }
    }
    return out;
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
      '--global-tools': '-InstallGlobalTools',
      '--install-global-tools': '-InstallGlobalTools',
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

function findPython() {
  const candidates = process.platform === 'win32'
    ? ['py', 'python', 'python3']
    : ['python3', 'python'];
  for (const name of candidates) {
    const args = name === 'py' ? ['-3', '--version'] : ['--version'];
    const probe = spawnSync(name, args, { encoding: 'utf8', windowsHide: true });
    if (probe.status === 0) return { cmd: name, prefix: name === 'py' ? ['-3'] : [] };
  }
  return null;
}

function runRuntime(parsed) {
  const py = findPython();
  if (!py) {
    console.error('[ERRO] Python 3.11+ nao encontrado (necessario para o runtime).');
    process.exit(4);
  }

  const env = {
    ...process.env,
    PYTHONPATH: runtimeSrc + (process.env.PYTHONPATH ? path.delimiter + process.env.PYTHONPATH : ''),
  };

  const args = [...py.prefix, '-m', 'orchestrator_runtime'];
  if (parsed.command === 'run') {
    args.push('run', ...parsed.runtimeArgs);
  } else if (parsed.command === 'task') {
    args.push('task', ...parsed.runtimeArgs);
  } else if (parsed.command === 'tools') {
    // tools install <id> → still PowerShell global-tools for now unless id given
    console.error('[INFO] Use: orchestrator global-tools   ou   orchestrator install --init-tools');
    console.error('[INFO] Tools opt-in: openwolf/graphify via --init-tools; MCPs via --global-tools');
    process.exit(0);
  }

  console.log(`[orchestrator] runtime: ${runtimeSrc}`);
  console.log(`[orchestrator] projeto: ${parsed.projectPath}`);
  console.log(`[orchestrator] comando: ${parsed.command}`);

  const result = spawnSync(py.cmd, args, {
    stdio: 'inherit',
    windowsHide: true,
    env,
    cwd: parsed.projectPath,
  });
  if (result.error) {
    console.error(`[ERRO] Falha ao iniciar Python: ${result.error.message}`);
    process.exit(1);
  }
  process.exit(result.status === null ? 1 : result.status);
}

function runInstaller(parsed) {
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

function main() {
  const parsed = parseArgs(process.argv.slice(2));
  if (parsed.help) {
    printHelp();
    process.exit(0);
  }

  if (isRuntimeCommand(parsed.command) || parsed.command === 'run' || parsed.command === 'task') {
    runRuntime(parsed);
    return;
  }

  runInstaller(parsed);
}

main();
