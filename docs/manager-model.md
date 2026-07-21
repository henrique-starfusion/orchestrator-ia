# Manager model

Default: **RulesManager** (determinístico).

Opcional: provider `openai-compatible` em `.orchestrator/config/manager_model.json`:

```json
{
  "provider": "openai-compatible",
  "base_url": "http://localhost:8000/v1",
  "model": "",
  "enabled": false
}
```

Interface: `analyze_task`, `select_strategy`, `evaluate_iteration`.

Qwen/local LLM **não** é obrigatório no MVP.
