#Requires -Version 5.1
# Migration 0.4.12 -> 0.4.13
# Skill selection: fast-model picks installed skills before planner/executor/validator.
# - policies.json: skill_selection block + agent_timeout_by_role.skill_selector
# - models.json: role_model_preferences.skill_selector -> haiku/fast per CLI
# - config.py: skill_selection_enabled/max_skills/timeout_s/include_user_global in RuntimeLimits
# - skills/discovery.py + skills/selector.py: new modules
# - tasks/service.py: _select_skills + _skills_block + _pick_selector_agent; prompts injected
param()
Write-Host '[OK] Migration 0.4.12-to-0.4.13 applied.'
