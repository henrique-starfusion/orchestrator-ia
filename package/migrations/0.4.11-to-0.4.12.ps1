#Requires -Version 5.1
# Migration 0.4.11 -> 0.4.12
# Always-on tooling: OpenWolf, Graphify, Superpowers, Caveman obrigatórios em todos os prompts.
# - policies.json: caveman_enabled=true, caveman_default="full", required_agent_tooling block
# - models.json: required_agent_tooling + always_on_skills block
# - config.py default caveman_enabled alterado para True
# - service.py: _required_tooling_block() injetado em executor/planner/validator prompts
# - docs/global-tools.md e docs/model-routing.md: caveman de opt-in para obrigatório
param()
Write-Host '[OK] Migration 0.4.11-to-0.4.12 applied.'
