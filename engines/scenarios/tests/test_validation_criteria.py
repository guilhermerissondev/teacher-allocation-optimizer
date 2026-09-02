from __future__ import annotations

import sys
import unittest
from datetime import time
from pathlib import Path
from tempfile import TemporaryDirectory

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from alocacao_docente.validation import validate_workbook  # noqa: E402
from motor_alocacao import (  # noqa: E402
    CRITERION_CLUSTER_PREFERRED,
    CRITERION_CLUSTER_PURE,
    CRITERION_PROFILE,
)


MAPA_HEADERS = (
    "CURSO", "NOME_CURSO", "CURRÍCULO", "COD_DISCIPLINA", "NOME_DISCIPLINA",
    "PERFIL_DISCIPLINA", "MATRIZ", "MÓD", "ANO", "ORDEM", "VALIDADO",
    "METODOLOGIA", "FORMATO", "PROVA", "ENTURMAÇÃO", "PERFIL", "CLUSTER",
    "COORDENADOR", "MODELO_CONTRATO", "SINERGIA", "DIA_AULA", "HORÁRIO",
    "FORMATO_AULA",
)

DOCENTES_HEADERS = (
    "NOME", "CHAPA", "NM_FUNCAO", "CH_CONTRATADA", "CH_LETIVA", "GESTOR",
    "STATUS", "PERFIL_DISCIPLINA",
)


def offer_row(code: str, profile: str, cluster: str, hour: int) -> tuple:
    return (
        "C1", "Curso", f"CURR{code}", code, f"Disciplina {code}", profile,
        2025, 52, "1º", "1ª", "VALIDADO", "5 SEMANAS", "ONLINE", 5,
        "N", "CLUSTER", cluster, "Coordenador", "CLT EAD", "CURSO ÚNICO",
        "SEGUNDA", time(hour, 0), "AO VIVO",
    )


def build_workbook(path: Path, offers: list[tuple], teachers: list[tuple]) -> None:
    workbook = Workbook()
    mapa = workbook.active
    mapa.title = "MAPA PEDAGÓGICO"
    mapa.append(MAPA_HEADERS)
    for row in offers:
        mapa.append(row)
    docentes = workbook.create_sheet("DOCENTES")
    docentes.append(DOCENTES_HEADERS)
    for row in teachers:
        docentes.append(row)
    workbook.save(path)
    workbook.close()


class ProfileCoverageByCriterionTests(unittest.TestCase):
    """A cobertura de perfil deve seguir o método escolhido na importação."""

    def setUp(self):
        self._directory = TemporaryDirectory()
        self.path = Path(self._directory.name) / "base.xlsx"
        # A oferta D2 usa o perfil "b", que existe no cluster GESTAO por causa
        # de D1, mas nenhum docente ativo possui "b" exatamente.
        build_workbook(
            self.path,
            [
                offer_row("D1", "a", "GESTAO", 19),
                offer_row("D2", "b", "GESTAO", 21),
            ],
            [
                (
                    "Docente A", "000000000001", "PROFESSOR REGENTE", 40, 10,
                    "Gestor", "ATIVO", "a",
                ),
            ],
        )

    def tearDown(self):
        self._directory.cleanup()

    def _codes(self, criterion) -> set[str]:
        report = validate_workbook(self.path, expected_module=52, criterion=criterion)
        return {issue.code for issue in report.issues}

    def test_profile_criterion_still_reports_the_gap(self):
        self.assertIn("PERFIL_SEM_DOCENTE_ATIVO", self._codes(CRITERION_PROFILE))

    def test_preferential_downgrades_the_gap_to_an_informational_notice(self):
        codes = self._codes(CRITERION_CLUSTER_PREFERRED)

        self.assertNotIn("PERFIL_SEM_DOCENTE_ATIVO", codes)
        self.assertIn("OFERTA_COBERTA_APENAS_POR_CLUSTER", codes)

    def test_pure_cluster_ignores_the_exact_profile_entirely(self):
        codes = self._codes(CRITERION_CLUSTER_PURE)

        self.assertNotIn("PERFIL_SEM_DOCENTE_ATIVO", codes)
        self.assertNotIn("OFERTA_COBERTA_APENAS_POR_CLUSTER", codes)

    def test_cluster_still_reports_an_offer_no_teacher_can_cover(self):
        # Nenhum docente possui "z", nem pelo cluster isolado da oferta.
        build_workbook(
            self.path,
            [offer_row("D3", "z", "SAUDE", 19)],
            [
                (
                    "Docente A", "000000000001", "PROFESSOR REGENTE", 40, 10,
                    "Gestor", "ATIVO", "a",
                ),
            ],
        )
        self.assertIn("PERFIL_SEM_DOCENTE_ATIVO", self._codes(CRITERION_CLUSTER_PURE))

    def test_criterion_is_recorded_in_the_report_metadata(self):
        report = validate_workbook(
            self.path, expected_module=52, criterion=CRITERION_CLUSTER_PURE
        )

        self.assertEqual(
            CRITERION_CLUSTER_PURE, report.metadata["eligibility_criterion"]
        )
        self.assertEqual("2.4", report.metadata["contract_version"])

    def test_unknown_criterion_is_refused(self):
        with self.assertRaises(ValueError):
            validate_workbook(self.path, expected_module=52, criterion="CLUSTER_TOTAL")


if __name__ == "__main__":
    unittest.main()
