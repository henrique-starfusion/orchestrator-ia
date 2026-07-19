# Correction Loop

Retry or replan when validation fails, respecting iteration and repeat-issue limits.

## When to use

- Validation score below threshold
- Same issue detected repeatedly

## Outputs

- Updated plan or task state
- Lessons in `memory/lessons/` when limits are hit
