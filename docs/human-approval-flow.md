# Human approval flow

Status: **implementado** (contrato) · uso pleno depende do manager colocar a tarefa em `WAITING_FOR_USER`

```mermaid
sequenceDiagram
  participant U as Usuario
  participant C as Cursor model
  participant M as MCP
  participant R as Runtime
  R-->>M: WAITING_FOR_USER
  M-->>C: requires_input + question
  C->>U: pergunta
  U-->>C: resposta
  C->>M: orchestrator_message
  M->>R: PLANNING + resume
```

`orchestrator_status` inclui `requires_input`, `question`, `options`, `risk` quando aplicável.
