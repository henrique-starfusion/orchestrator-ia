#Requires -Version 5.1
# Migration 0.4.13 -> 0.4.14
# Learn-then-compact context: salva aprendizado durável ANTES de compactar o
# contexto do chat; devolve um digest compacto no result/status para o cliente
# IDE descartar ruído de polls.
# - policies.json: bloco context_compaction (enabled, save_learning_before_compact,
#   digest_max_chars, truncate_result_artifacts_chars, update_wolf_status)
# - config.py: context_compaction_enabled/save_learning_before_compact/digest_max_chars/
#   truncate_result_artifacts_chars/update_wolf_status em RuntimeLimits; _context_compaction_limits()
# - memory/learnings.py: novo módulo (extract_learning, build_digest, markdown, index,
#   .wolf/STATUS + cerebrum, compact_result_artifacts)
# - tasks/service.py: _learn_then_compact (save learning -> depois compact) no choke
#   point _persist_episode; cancel() após execução; retrieval kind=learning injetado
#   nos prompts de planner/executor
# - tasks/repository.py: search_memories(kind=...) filtra por tipo de memória
# - mcp/tools.py: result()/status() expõem session_digest + learning_path
# - diagnostics.py: feature learn_then_compact_context + fingerprint memory/learnings.py
param()
Write-Host '[OK] Migration 0.4.13-to-0.4.14 applied.'
