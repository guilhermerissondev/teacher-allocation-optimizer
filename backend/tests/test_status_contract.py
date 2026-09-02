"""O vocabulário de estados é um contrato entre o backend e a interface.

O backend decide quando uma execução terminou e em que estado. A interface
traduz esse estado em duas coisas que o operador lê antes de qualquer outra:
a cor do selo e a etapa marcada como falha no stepper.

Quando um estado novo entra em ``TERMINAL_STATES`` e ninguém atualiza a
interface, ele não quebra nada — ele mente em silêncio. Uma auditoria
reprovada aparecia com o mesmo cinza de um estado desconhecido e com a falha
desenhada em "Preparando", mandando conferir o arquivo de entrada em vez do
relatório de auditoria. Estes testes fecham essa porta lendo as tabelas da
interface e exigindo que elas cubram o vocabulário publicado pelo backend.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from app.services.jobs import TERMINAL_STATES


REPO_ROOT = Path(__file__).resolve().parents[2]
STATUS_BADGE = REPO_ROOT / "frontend" / "src" / "components" / "StatusBadge.tsx"
# As tabelas de etapa e as opções da importação são compartilhadas pelas duas
# telas de processamento. Vigiar a fonte única evita que uma cópia divirja.
JOB_STAGES = REPO_ROOT / "frontend" / "src" / "jobStages.ts"
RUN_OPTIONS = REPO_ROOT / "frontend" / "src" / "components" / "RunOptions.tsx"

# Estados que a própria tela trata sem tabela: um é o sucesso, o outro é a
# interrupção do encerramento seguro, que não pertence a nenhuma etapa.
SELF_EVIDENT_STATES = {"CONCLUIDA", "INTERROMPIDA"}


def _string_list(source: str, name: str) -> set[str]:
    """Extrai os literais de um ``const NOME = [...]`` do TypeScript."""
    match = re.search(rf"(?:export )?const {name} = \[(.*?)\];", source, re.DOTALL)
    if not match:
        raise AssertionError(f"Tabela {name} não encontrada na interface.")
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def _record_keys(source: str, name: str) -> set[str]:
    """Extrai as chaves de um ``const NOME: Record<string, number> = {...}``."""
    match = re.search(
        rf"(?:export )?const {name}: Record<string, number> = \{{(.*?)\n\}};",
        source,
        re.DOTALL,
    )
    if not match:
        raise AssertionError(f"Tabela {name} não encontrada na interface.")
    return set(re.findall(r"^\s*([A-Z_0-9]+):", match.group(1), re.MULTILINE))


class TerminalStateContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.badge_source = STATUS_BADGE.read_text(encoding="utf-8")
        self.stages_source = JOB_STAGES.read_text(encoding="utf-8")
        self.options_source = RUN_OPTIONS.read_text(encoding="utf-8")

    def test_every_terminal_failure_is_coloured_as_a_failure(self) -> None:
        # `startsWith("FALHA")` cobre metade do vocabulário. A outra metade —
        # VALIDACAO_REPROVADA, AUDITORIA_REPROVADA, OTIMO_NAO_COMPROVADO,
        # SNAPSHOT_ALTERADO, ERRO_INTERNO — precisa estar listada, ou é
        # desenhada em cinza neutro.
        declared = _string_list(self.badge_source, "TERMINAL_FAILURE_STATES")
        uncovered = {
            state
            for state in TERMINAL_STATES
            if state not in SELF_EVIDENT_STATES
            and not state.startswith("FALHA")
            and state not in declared
        }
        self.assertEqual(set(), uncovered)

    def test_every_terminal_failure_points_at_the_stage_that_failed(self) -> None:
        mapped = _record_keys(self.stages_source, "STEP_BY_STATUS")
        uncovered = {
            state
            for state in TERMINAL_STATES
            if state not in SELF_EVIDENT_STATES
            and state != "ERRO_INTERNO"  # falha sem etapa conhecida
            and state not in mapped
        }
        self.assertEqual(set(), uncovered)

    def test_the_stepper_knows_every_stage_the_engine_announces(self) -> None:
        # Os estados de progresso do motor vêm de `_StatusRecorder.update` no
        # pipeline. Um estado de progresso sem etapa deixa o stepper parado
        # enquanto a rodada avança.
        pipeline = (
            REPO_ROOT / "engines" / "primary" / "pipeline.py"
        ).read_text(encoding="utf-8")
        announced = set(re.findall(r'status\.update\(\s*"([A-Z_]+)"', pipeline))
        mapped = _record_keys(self.stages_source, "STEP_BY_STATUS")
        uncovered = {
            state
            for state in announced
            if state not in mapped
            and state not in {"INICIADA", "CONCLUIDA", "ERRO_INTERNO"}
        }
        self.assertEqual(set(), uncovered)

    def test_usable_solver_guarantees_are_not_painted_as_failures(self) -> None:
        # COBERTURA_PROVADA e OTIMO_COM_MARGEM são resultados legítimos, mais
        # fortes que FEASIBLE. Pintá-los de vermelho — ou deixá-los cinza —
        # sugeriria uma falha que não houve.
        partial = _string_list(self.badge_source, "PARTIAL_GUARANTEE_STATES")
        for status in ("COBERTURA_PROVADA", "OTIMO_COM_MARGEM", "FEASIBLE"):
            with self.subTest(status=status):
                self.assertIn(status, partial)

    def test_the_interface_offers_exactly_the_profiles_the_api_accepts(self) -> None:
        # O `pattern` do formulário de upload é a fronteira real: um perfil
        # oferecido na tela e recusado pelo `pattern` viraria 422 na cara do
        # operador, e um perfil aceito e nunca oferecido é caminho morto.
        api = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        accepted = set(
            re.search(
                r'Form\(pattern="\^\((PROVA_COMPLETA[^)]*)\)\$"\)', api
            ).group(1).split("|")
        )
        block = re.search(
            r"^export const PROFILES: .*?^\];",
            self.options_source,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(block, "Lista de perfis não encontrada na interface.")
        offered = set(re.findall(r'value: "([A-Z_]+)"', block.group(0)))
        self.assertEqual(accepted, offered)

    def test_the_interface_offers_exactly_the_criteria_the_api_accepts(self) -> None:
        # Mesma fronteira do teste acima, para o critério de elegibilidade.
        # As duas telas de processamento leem esta lista, então uma divergência
        # aqui atingiria a rodada única e o lote de uma vez.
        api = (REPO_ROOT / "backend" / "app" / "main.py").read_text(encoding="utf-8")
        accepted = set(
            re.search(
                r'Form\(pattern="\^\((PERFIL_EXATO[^)]*)\)\$"\)', api
            ).group(1).split("|")
        )
        block = re.search(
            r"^export const CRITERIA: .*?^\];",
            self.options_source,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(block, "Lista de critérios não encontrada na interface.")
        offered = set(re.findall(r'value: "([A-Z_]+)"', block.group(0)))
        self.assertEqual(accepted, offered)


if __name__ == "__main__":
    unittest.main()
