"""0.4.83 - regra de desenvolvimento baseada em evidencia (Issue #12)."""

from __future__ import annotations

import unicodedata
from pathlib import Path

from orchestrator_runtime.rules.discovery import discover_rules, select_rules


REPO_ROOT = Path(__file__).resolve().parents[3]
RULE_ID = "nunca-supor"
# Fonte rastreada pelo git. O `.orchestrator/` da raiz e ignorado (.gitignore:2)
# e nao existe em clone limpo — apontar para la deixava a suite verde so na
# maquina de quem instalou o pacote.
TEMPLATE_RULE = (
    REPO_ROOT / "package" / "template" / ".orchestrator" / "rules" / f"{RULE_ID}.md"
)


def _plain(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(character)
    )


def test_nunca_supor_e_descoberta_e_selecionada_por_evidencia(tmp_path: Path) -> None:
    assert TEMPLATE_RULE.is_file(), f"regra ausente do pacote: {TEMPLATE_RULE}"

    isolated_rule_dir = tmp_path / ".orchestrator" / "rules"
    isolated_rule_dir.mkdir(parents=True)
    (isolated_rule_dir / TEMPLATE_RULE.name).write_text(
        TEMPLATE_RULE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    rules = {rule.rule_id: rule for rule in discover_rules(tmp_path)}

    assert RULE_ID in rules, "discover_rules nao encontrou .orchestrator/rules/nunca-supor.md"
    description = _plain(rules[RULE_ID].description)
    assert {"verificar", "suposicao", "evidencia", "medir", "consultar"} <= set(
        description.split()
    ), "description perdeu termos distintivos usados pela selecao"

    selected = select_rules(
        tmp_path,
        "Verificar a evidencia e medir o comportamento antes de afirmar.",
    )

    assert RULE_ID in {rule.rule_id for rule in selected}
