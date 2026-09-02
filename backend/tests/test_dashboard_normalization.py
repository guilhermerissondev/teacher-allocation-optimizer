"""A planilha é digitada por pessoas; o backend precisa ler como o motor lê.

O motor aceita variações de caixa e de espaçamento — ``normalize_order`` e
``contract_family`` colapsam os dois antes de comparar. Quando o backend
recalcula indicadores a partir da mesma planilha sem aplicar a mesma regra, a
oferta continua alocada e some do gráfico: as duas telas passam a discordar a
partir do mesmo arquivo auditado, que é o pior modo de falhar.

Aqui também ficam os recuos para rodadas antigas. Uma coluna que ainda não
existia não pode virar um indicador falso: sem ``CANDIDATOS_ELEGÍVEIS`` a
resposta é "não sei", não "todas as alocações são frágeis".
"""

from __future__ import annotations

import unittest

from app.services.insights import _has_weekly_cap, _single_candidate
from app.services.jobs import _allocatable_hours, _canonical, _regime_label


class CanonicalTests(unittest.TestCase):
    def test_colapsa_caixa_e_espacos_como_o_motor(self) -> None:
        self.assertEqual("ESTENDIDA", _canonical("Estendida"))
        self.assertEqual("ESTENDIDA", _canonical("  estendida  "))
        self.assertEqual("1ª", _canonical("1ª"))
        self.assertEqual(
            "PROFESSOR DE ENSINO SUPERIOR PRESENCIAL",
            _canonical("PROFESSOR DE  ENSINO   SUPERIOR PRESENCIAL"),
        )

    def test_valor_ausente_vira_string_vazia(self) -> None:
        self.assertEqual("", _canonical(None))


class RegimeLabelTests(unittest.TestCase):
    def test_stricto_reconhecido_apesar_do_espaco_duplo(self) -> None:
        """O sufixo Mensalista não pode depender de digitação limpa."""
        row = {
            "NM_FUNCAO": "PROFESSOR DE  ENSINO SUPERIOR PRESENCIAL",
            "CH_CONTRATADA": 40,
        }
        self.assertEqual("T40 · 40h contratadas · Mensalista", _regime_label(row))

    def test_regime_comum_nao_recebe_sufixo(self) -> None:
        row = {"NM_FUNCAO": "PROFESSOR REGENTE", "CH_CONTRATADA": 12}
        self.assertEqual("T12 · 12h contratadas", _regime_label(row))


class AllocatableHoursTests(unittest.TestCase):
    def test_prefere_a_coluna_do_motor(self) -> None:
        row = {"CH_LETIVA": 9, "CH_LETIVA_ALOCÁVEL": 8}
        self.assertEqual(8, _allocatable_hours(row, 2))

    def test_rodada_antiga_arredonda_a_partir_da_ch_letiva(self) -> None:
        """Sem a coluna, o piso é refeito aqui — 9h dão quatro blocos de 2h."""
        self.assertEqual(8, _allocatable_hours({"CH_LETIVA": 9}, 2))

    def test_zero_declarado_pelo_motor_vence_a_ch_letiva_da_base(self) -> None:
        """O contrato Stricto sai com zero mesmo com CH_LETIVA preenchida."""
        row = {"CH_LETIVA": 40, "CH_LETIVA_ALOCÁVEL": 0}
        self.assertEqual(0, _allocatable_hours(row, 2))


class SingleCandidateTests(unittest.TestCase):
    def test_conta_apenas_quando_a_coluna_existe(self) -> None:
        self.assertTrue(_single_candidate({"CANDIDATOS_ELEGÍVEIS": 1}))
        self.assertFalse(_single_candidate({"CANDIDATOS_ELEGÍVEIS": 3}))

    def test_coluna_ausente_nao_marca_escassez(self) -> None:
        """Rodada antiga não pode render um cartão crítico dizendo 100%."""
        self.assertFalse(_single_candidate({}))


class WeeklyCapTests(unittest.TestCase):
    def test_sem_ch_alocavel_fica_fora_da_mediana(self) -> None:
        self.assertFalse(_has_weekly_cap({"CH_LETIVA_ALOCÁVEL": 0, "CH_LETIVA": 0}))
        self.assertTrue(_has_weekly_cap({"CH_LETIVA_ALOCÁVEL": 8}))

    def test_rodada_antiga_usa_a_ch_letiva(self) -> None:
        self.assertTrue(_has_weekly_cap({"CH_LETIVA": 9}))
        self.assertFalse(_has_weekly_cap({"CH_LETIVA": 0}))


if __name__ == "__main__":
    unittest.main()
