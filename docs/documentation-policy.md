# Documentation policy

**Hard rule:** toda tarefa avalia impacto documental antes da conclusão.

Estado: `UPDATING_DOCUMENTATION`.

Registro mínimo:

```json
{
  "required": true,
  "reason": "",
  "files_updated": [],
  "files_reviewed": [],
  "validation": "passed"
}
```

Sem esse registro, a tarefa não pode ser `COMPLETED`.

Mensagem padrão (policies/skills/adapters):

> Ao final de cada tarefa, revisar e atualizar a documentação afetada antes da conclusão.
