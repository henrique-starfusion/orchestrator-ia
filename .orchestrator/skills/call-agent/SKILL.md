# Call Agent

Invoke another agent CLI with the correct model for the task, using declarative profiles. Works for ANY agent that has a profile in `agents/profiles/` — adding a new CLI requires only a new JSON file there.

## When to use

- Delegating a plan step to another agent (executor, tester, validator)
- Running read-only analysis in parallel when policy allows (`config/policies.json`)

## Anti-recursion (check FIRST)

If the environment variable `ORCHESTRATOR_CHILD_AGENT` is set, you ARE a delegated child: do NOT delegate further. Do the work yourself.
When spawning a child, set `ORCHESTRATOR_CHILD_AGENT=1` in its environment.

## Flow

1. **Classify** the task into a `task_class` (see `config/models.json` → `task_classes`; e.g. `docs`, `implementation`, `architecture`, `complex_analysis`).
2. **Route** to a model:
   `orchestrator route --task-class <class> --client <claude|codex|gemini|opencode|kimi|cursor|auto> --json`
   Returns `client`, `model`, `alias`, `model_flag`, `tier`.
3. **Read the profile** `agents/profiles/<client>.json`:
   - `kind: "ide-hint"` → no CLI; follow `hint` (Cursor: `Task model="<slug>"`, mandatory).
   - `invoke.subcommand` → fixed non-interactive args.
   - `invoke.prompt_flag` → prompt flag; `null` means positional prompt.
   - `invoke.sandbox_flags` → NEVER apply unless the user explicitly asked.
   - `verified: false` → flags came from docs, not tested on this host; expect quirks.
4. **Assemble**: `<cli> <subcommand...> <model_flag> <alias|model> [prompt_flag] "<scoped prompt>"`
5. **Execute** with the profile's `timeout_default_s`. Pass only scoped files and a tight brief — no full-repo paste. Caveman intensity `full` unless the user disabled it.
6. **Persist**: result goes to `runtime/results/`, model choice next to it. Exit code != `exit_codes.success` → treat as failure, consider `correction-loop`.

Shortcut for steps 2-6: `orchestrator dispatch --task-class <class> --client <c> --prompt "..."`.

## Examples

| Client | Assembled command |
|---|---|
| claude | `claude --model sonnet -p "Atualize o README do modulo X"` |
| codex | `codex exec -m gpt-5.6-sol-medium "Corrija o teste Y"` |
| gemini | `gemini -m gemini-3.1-pro -p "Analise o arquivo Z"` |
| opencode | `opencode run --model default "Refatore W"` |
| cursor | (no CLI) `Task model="claude-sonnet-5-thinking-high"` — slug from `orchestrator route --client cursor` |

## Ownership split

- `agents/profiles/<cli>.json` — HOW to invoke (mechanics). New CLI = new file here.
- `config/models.json` — WHICH model per task_class (routing policy).
- `config/policies.json` — iteration/validation limits. Respect them.

## Outputs

- Agent result: `runtime/results/<stamp>-<task_class>-result.txt`
- Model choice: `runtime/results/<stamp>-<task_class>-model-choice.json`
