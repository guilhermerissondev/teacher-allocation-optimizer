from __future__ import annotations

import json
import shutil
import sys
import unittest
import uuid
from datetime import time
from pathlib import Path

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from motor_alocacao.domain import (  # noqa: E402
    AllocationResult,
    Assignment,
    Problem,
    Teacher,
    Transmission,
)
from motor_alocacao.reporting import write_results  # noqa: E402


PROFILE = frozenset({"gestão - administração"})


def teacher(identifier: int, *, stricto: bool = False) -> Teacher:
    return Teacher(
        id=identifier,
        name=f"Docente {identifier}",
        badge=f"{identifier + 1:012d}",
        job_function=(
            "PROFESSOR DE ENSINO SUPERIOR PRESENCIAL"
            if stricto
            else "PROFESSOR REGENTE"
        ),
        contracted_capacity=0 if stricto else 40,
        teaching_capacity=0 if stricto else 4,
        manager="Gestor",
        status="ATIVO",
        profiles=PROFILE,
        profile_text="Gestão - Administração",
    )


def transmission(
    identifier: int,
    *,
    stricto: bool = False,
    order: str = "1ª",
) -> Transmission:
    return Transmission(
        id=identifier,
        excel_row=identifier + 2,
        course=f"C{identifier}",
        course_name="Curso",
        curriculum=f"CURR{identifier}",
        discipline_code=f"D{identifier}",
        discipline_name=f"Disciplina {identifier}",
        profiles=PROFILE,
        profile_text="Gestão - Administração",
        synergy="Curso Único",
        day="SEGUNDA",
        start_time=time(19 + identifier, 0),
        order=order,
        cluster="GESTÃO",
        coordinator="Coordenador",
    )


def reporting_fixture() -> tuple[Problem, AllocationResult]:
    problem = Problem(
        source=Path("base_m53.xlsx"),
        teachers=(teacher(0, stricto=True), teacher(1)),
        transmissions=(transmission(0), transmission(1)),
    )
    result = AllocationResult(
        status="PARCIAL",
        solver_status="OPTIMAL",
        assignments=[
            Assignment(
                transmission_id=0,
                teacher_id=0,
                status="ALOCADA",
                reason="",
                eligible_teacher_count=1,
                allocation_reason="Regra Stricto",
            ),
            Assignment(
                transmission_id=1,
                teacher_id=None,
                status="NAO_ALOCADA",
                reason="SEM_DOCENTE_COM_PERFIL_E_CARGA",
                eligible_teacher_count=0,
                allocation_reason="",
            ),
        ],
        teacher_loads={0: 2, 1: 0},
        objective_unassigned=1,
        used_teacher_count=1,
        zero_active_teacher_count=1,
        high_capacity_score=0,
        rescue_scarcity_score=0,
        wall_time_seconds=0.25,
        diagnostics={"all_lexicographic_phases_optimal": True},
    )
    return problem, result


class ReportingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.output_dir = ROOT / "tests" / f".reporting-{uuid.uuid4().hex}"
        self.addCleanup(shutil.rmtree, self.output_dir, True)

    def test_generates_xlsx_and_json_with_line_level_decisions(self) -> None:
        problem, result = reporting_fixture()

        xlsx_path, json_path = write_results(problem, result, self.output_dir)

        self.assertEqual(self.output_dir / "resultado_alocacao.xlsx", xlsx_path)
        self.assertEqual(self.output_dir / "resumo_alocacao.json", json_path)
        self.assertTrue(xlsx_path.is_file())
        self.assertTrue(json_path.is_file())

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(2, payload["transmissions"])
        self.assertEqual(1, payload["allocated"])
        self.assertEqual(1, payload["unassigned"])
        self.assertEqual(
            {"first_stage": 2, "second_stage": 0},
            payload["allocated_stage_hours"],
        )
        # Stricto fica fora da apuracao de teto e o outro docente nao tem carga.
        self.assertEqual(0, payload["teachers_over_capacity"])
        self.assertEqual(
            {"SEM_DOCENTE_COM_PERFIL_E_CARGA": 1},
            payload["unassigned_reasons"],
        )
        self.assertNotIn("contract_model_comparison", payload)
        self.assertIsInstance(payload["decisions"], list)
        self.assertEqual(2, len(payload["decisions"]))

        allocated, unassigned = payload["decisions"]
        self.assertEqual(
            {
                "transmission_id": 0,
                "source_row": 2,
                "curriculum": "CURR0",
                "discipline_code": "D0",
                "discipline_name": "Disciplina 0",
                "status": "ALOCADA",
                "unassigned_reason": "",
                "allocation_reason": "Regra Stricto",
                "eligible_teacher_count": 1,
                "eligibility_basis": "PERFIL_EXATO",
                "contract_model": "CLT STRICTO",
                "teacher_id": 0,
                "teacher_badge": "000000000001",
                "teacher_name": "Docente 0",
            },
            allocated,
        )
        self.assertEqual("NAO_ALOCADA", unassigned["status"])
        self.assertEqual("SEM_DOCENTE_COM_PERFIL_E_CARGA", unassigned["unassigned_reason"])
        self.assertEqual("A DEFINIR", unassigned["contract_model"])
        self.assertNotIn("original_contract_model", unassigned)
        self.assertNotIn("suggested_contract_model", unassigned)
        self.assertIsNone(unassigned["teacher_id"])
        self.assertIsNone(unassigned["teacher_badge"])
        self.assertIsNone(unassigned["teacher_name"])

        workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            self.assertEqual(
                ["RESUMO", "ALOCACOES", "DOCENTES", "DOCENTES POR CARGO"],
                workbook.sheetnames,
            )
            allocations = workbook["ALOCACOES"]
            headers = [cell.value for cell in allocations[1]]
            self.assertEqual(
                [
                    "STATUS", "MOTIVO", "MOTIVO_ALOCACAO", "LINHA_ORIGEM",
                    "CURSO", "NOME_CURSO", "CURRÍCULO", "COD_DISCIPLINA",
                    "NOME_DISCIPLINA", "PERFIL_DISCIPLINA", "SINERGIA",
                    "DIA_AULA", "HORÁRIO", "ORDEM", "CLUSTER", "COORDENADOR",
                    "MODELO_CONTRATO", "DOCENTE", "CHAPA", "CANDIDATOS_ELEGÍVEIS",
                    "BASE_ELEGIBILIDADE",
                ],
                headers,
            )
            first_row = dict(zip(headers, next(allocations.iter_rows(min_row=2, values_only=True))))
            self.assertEqual("ALOCADA", first_row["STATUS"])
            self.assertEqual("Regra Stricto", first_row["MOTIVO_ALOCACAO"])
            self.assertNotIn("MODELO_CONTRATO_ORIGEM", headers)
            self.assertEqual("CLT STRICTO", first_row["MODELO_CONTRATO"])
        finally:
            workbook.close()

    def test_preserves_stricto_base_loads_and_removes_temporary_files(self) -> None:
        problem, result = reporting_fixture()

        xlsx_path, _ = write_results(problem, result, self.output_dir)

        workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            worksheet = workbook["DOCENTES"]
            headers = [cell.value for cell in worksheet[1]]
            rows = [dict(zip(headers, values)) for values in worksheet.iter_rows(min_row=2, values_only=True)]
            stricto = next(row for row in rows if row["CHAPA"] == "000000000001")
            self.assertEqual(0, stricto["CH_CONTRATADA"])
            self.assertEqual(0, stricto["CH_LETIVA"])
            self.assertEqual(1, stricto["QTD_1ª_ORDEM"])
            self.assertEqual(0, stricto["QTD_2ª_ORDEM"])
            self.assertEqual(0, stricto["QTD_ESTENDIDA"])
            self.assertEqual(1, stricto["QTD_TRANSMISSÕES"])
            self.assertEqual(1, stricto["QTD_DISCIPLINAS_1ª_ETAPA"])
            self.assertEqual(2, stricto["CH_ALOCADA_1ª_ETAPA"])
            self.assertEqual(0, stricto["QTD_DISCIPLINAS_2ª_ETAPA"])
            self.assertEqual(0, stricto["CH_ALOCADA_2ª_ETAPA"])
            self.assertEqual(2, stricto["CH_ALOCADA_PICO"])
            # Stricto preserva CH_LETIVA zero: folga zerada, percentuais em 0%
            # e o teto semanal nao se aplica.
            self.assertEqual(0, stricto["CH_DISPONÍVEL_1ª_ETAPA"])
            self.assertEqual(0, stricto["CH_DISPONÍVEL_2ª_ETAPA"])
            self.assertEqual(0, stricto["CH_DISPONÍVEL"])
            self.assertEqual(0, stricto["UTILIZAÇÃO_1ª_ETAPA"])
            self.assertEqual(0, stricto["UTILIZAÇÃO_2ª_ETAPA"])
            self.assertEqual(0, stricto["UTILIZAÇÃO_PICO"])
            self.assertEqual("NSA", stricto["EXCEDE_CH_LETIVA"])
            self.assertNotIn("MODELO_CONTRATO", headers)
        finally:
            workbook.close()

        self.assertEqual([], list(self.output_dir.rglob("*.tmp")))

    def test_breaks_down_teacher_usage_by_job_function_and_regime(self) -> None:
        """A abertura por cargo do relatorio semanal, gerada pelo motor.

        Cada cargo abre nos regimes de contratacao e fecha em Total Geral. Sem
        CH letiva alocavel nao ha percentual: o contrato Stricto entra com NSA
        em vez de um denominador zerado.
        """
        problem, result = reporting_fixture()

        xlsx_path, _ = write_results(problem, result, self.output_dir)

        workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            worksheet = workbook["DOCENTES POR CARGO"]
            headers = [cell.value for cell in worksheet[1]]
            self.assertEqual(
                [
                    "CARGO", "REGIME", "HEADCOUNT", "CH_CONTRATADA",
                    "CH_LETIVA_ALOCÁVEL",
                    "CH_ALOCADA_1ª_ETAPA", "UTILIZAÇÃO_1ª_ETAPA",
                    "CH_ALOCADA_2ª_ETAPA", "UTILIZAÇÃO_2ª_ETAPA",
                    "CH_ALOCADA_PICO", "UTILIZAÇÃO_PICO",
                ],
                headers,
            )
            rows = list(worksheet.iter_rows(min_row=2, values_only=True))
            self.assertEqual(
                [
                    (
                        "PROFESSOR DE ENSINO SUPERIOR PRESENCIAL",
                        "TOTAL DO CARGO", 1, 0, 0, 2, "NSA", 0, "NSA", 2, "NSA",
                    ),
                    (
                        "PROFESSOR DE ENSINO SUPERIOR PRESENCIAL",
                        "T0 · 0h contratadas · Mensalista",
                        1, 0, 0, 2, "NSA", 0, "NSA", 2, "NSA",
                    ),
                    (
                        "PROFESSOR REGENTE",
                        "TOTAL DO CARGO", 1, 40, 4, 0, 0.0, 0, 0.0, 0, 0.0,
                    ),
                    (
                        "PROFESSOR REGENTE",
                        "T40 · 40h contratadas", 1, 40, 4, 0, 0.0, 0, 0.0, 0, 0.0,
                    ),
                    (
                        "TOTAL GERAL",
                        "TOTAL GERAL", 2, 40, 4, 2, 0.5, 0, 0.0, 2, 0.5,
                    ),
                ],
                rows,
            )
        finally:
            workbook.close()

    def test_flags_teacher_over_the_weekly_cap_in_one_stage(self) -> None:
        """A bandeira de governanca do teto semanal.

        A CH_LETIVA vale por semana, entao o estouro acontece dentro de uma
        etapa: tres disciplinas na primeira metade somam 6h contra 4h de teto,
        mesmo que a segunda metade caiba folgada. Sem esta bandeira o excesso
        so apareceria comparando duas colunas na mao.
        """
        problem = Problem(
            source=Path("base_m53.xlsx"),
            teachers=(teacher(0),),
            transmissions=(
                transmission(0, order="1ª"),
                transmission(1, order="1ª"),
                transmission(2, order="1ª"),
            ),
        )
        assignments = [
            Assignment(
                transmission_id=identifier,
                teacher_id=0,
                status="ALOCADA",
                reason="",
                eligible_teacher_count=1,
                allocation_reason="Regra por etapa",
            )
            for identifier in range(3)
        ]
        result = AllocationResult(
            status="COMPLETA",
            solver_status="OPTIMAL",
            assignments=assignments,
            teacher_loads={0: 6},
            objective_unassigned=0,
            used_teacher_count=1,
            zero_active_teacher_count=0,
            high_capacity_score=12,
            rescue_scarcity_score=0,
            wall_time_seconds=0.1,
            teacher_stage_loads={0: {"PRIMEIRA_ETAPA": 6, "SEGUNDA_ETAPA": 0}},
        )

        xlsx_path, json_path = write_results(problem, result, self.output_dir)

        workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            worksheet = workbook["DOCENTES"]
            headers = [cell.value for cell in worksheet[1]]
            row = dict(zip(headers, next(worksheet.iter_rows(min_row=2, values_only=True))))
            self.assertEqual(3, row["QTD_DISCIPLINAS_1ª_ETAPA"])
            self.assertEqual(6, row["CH_ALOCADA_1ª_ETAPA"])
            self.assertEqual(0, row["CH_ALOCADA_2ª_ETAPA"])
            self.assertEqual(6, row["CH_ALOCADA_PICO"])
            # A folga negativa e o sintoma; a bandeira e o diagnostico.
            self.assertEqual(-2, row["CH_DISPONÍVEL_1ª_ETAPA"])
            self.assertEqual(-2, row["CH_DISPONÍVEL"])
            self.assertEqual(1.5, row["UTILIZAÇÃO_PICO"])
            self.assertEqual("SIM", row["EXCEDE_CH_LETIVA"])
        finally:
            workbook.close()

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertEqual(1, payload["teachers_over_capacity"])

    def test_reports_stage_counts_hours_and_peak_utilization(self) -> None:
        problem = Problem(
            source=Path("base_m53.xlsx"),
            teachers=(teacher(0),),
            transmissions=(
                transmission(0, order="1ª"),
                transmission(1, order="ESTENDIDA"),
            ),
        )
        assignments = [
            Assignment(
                transmission_id=identifier,
                teacher_id=0,
                status="ALOCADA",
                reason="",
                eligible_teacher_count=1,
                allocation_reason="Regra por etapa",
            )
            for identifier in range(2)
        ]
        result = AllocationResult(
            status="COMPLETA",
            solver_status="OPTIMAL",
            assignments=assignments,
            teacher_loads={0: 4},
            objective_unassigned=0,
            used_teacher_count=1,
            zero_active_teacher_count=0,
            high_capacity_score=8,
            rescue_scarcity_score=0,
            wall_time_seconds=0.1,
            teacher_stage_loads={
                0: {"PRIMEIRA_ETAPA": 4, "SEGUNDA_ETAPA": 2},
            },
        )

        xlsx_path, _ = write_results(problem, result, self.output_dir)

        workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            worksheet = workbook["DOCENTES"]
            headers = [cell.value for cell in worksheet[1]]
            values = next(worksheet.iter_rows(min_row=2, values_only=True))
            row = dict(zip(headers, values))
            self.assertEqual(
                [
                    "NOME", "CHAPA", "NM_FUNCAO", "CH_CONTRATADA", "CH_LETIVA",
                    "CH_LETIVA_ALOCÁVEL", "GESTOR", "STATUS", "PERFIL_DISCIPLINA",
                    "QTD_1ª_ORDEM", "QTD_2ª_ORDEM", "QTD_ESTENDIDA",
                    "QTD_TRANSMISSÕES",
                    "QTD_DISCIPLINAS_1ª_ETAPA", "CH_ALOCADA_1ª_ETAPA",
                    "CH_DISPONÍVEL_1ª_ETAPA", "UTILIZAÇÃO_1ª_ETAPA",
                    "QTD_DISCIPLINAS_2ª_ETAPA", "CH_ALOCADA_2ª_ETAPA",
                    "CH_DISPONÍVEL_2ª_ETAPA", "UTILIZAÇÃO_2ª_ETAPA",
                    "CH_ALOCADA_PICO", "CH_DISPONÍVEL", "UTILIZAÇÃO_PICO",
                    "EXCEDE_CH_LETIVA", "SITUACAO_ALOCACAO",
                ],
                headers,
            )
            self.assertNotIn("MODELO_CONTRATO", headers)
            # 4h de CH_LETIVA fecham dois blocos de 2h: a alocável coincide.
            self.assertEqual(4, row["CH_LETIVA_ALOCÁVEL"])
            # Uma disciplina de 1ª ordem e uma ESTENDIDA, com CH_LETIVA de 4h.
            self.assertEqual(1, row["QTD_1ª_ORDEM"])
            self.assertEqual(0, row["QTD_2ª_ORDEM"])
            self.assertEqual(1, row["QTD_ESTENDIDA"])
            self.assertEqual(2, row["QTD_TRANSMISSÕES"])
            # 1ª etapa: 1ª ordem + ESTENDIDA = 2 disciplinas = 4h = teto.
            self.assertEqual(2, row["QTD_DISCIPLINAS_1ª_ETAPA"])
            self.assertEqual(4, row["CH_ALOCADA_1ª_ETAPA"])
            self.assertEqual(0, row["CH_DISPONÍVEL_1ª_ETAPA"])
            self.assertEqual(1, row["UTILIZAÇÃO_1ª_ETAPA"])
            # 2ª etapa: apenas a ESTENDIDA = 1 disciplina = 2h.
            self.assertEqual(1, row["QTD_DISCIPLINAS_2ª_ETAPA"])
            self.assertEqual(2, row["CH_ALOCADA_2ª_ETAPA"])
            self.assertEqual(2, row["CH_DISPONÍVEL_2ª_ETAPA"])
            self.assertEqual(0.5, row["UTILIZAÇÃO_2ª_ETAPA"])
            # O pico e a 1ª etapa; encosta no teto sem ultrapassar.
            self.assertEqual(4, row["CH_ALOCADA_PICO"])
            self.assertEqual(0, row["CH_DISPONÍVEL"])
            self.assertEqual(1, row["UTILIZAÇÃO_PICO"])
            self.assertEqual("NAO", row["EXCEDE_CH_LETIVA"])
            for header in (
                "UTILIZAÇÃO_PICO",
                "UTILIZAÇÃO_1ª_ETAPA",
                "UTILIZAÇÃO_2ª_ETAPA",
            ):
                column = headers.index(header) + 1
                self.assertEqual("0.0%", worksheet.cell(2, column).number_format)
        finally:
            workbook.close()

    def test_uses_allocatable_capacity_as_the_utilization_denominator(self) -> None:
        """A hora que não fecha uma transmissão não conta como capacidade.

        Um regente de 12h contratadas com 9h letivas só consegue receber quatro
        disciplinas de 2h: as 8h são o teto real e a nona hora fica ociosa por
        construção. Dividir a carga pelas 9h fazia todo o corpo docente parecer
        menos ocupado do que o modelo permite.
        """
        capacity = 9
        problem = Problem(
            source=Path("base_m53.xlsx"),
            teachers=(
                Teacher(
                    id=0,
                    name="Regente T12",
                    badge="000000000001",
                    job_function="PROFESSOR REGENTE",
                    contracted_capacity=12,
                    teaching_capacity=capacity,
                    manager="Gestor",
                    status="ATIVO",
                    profiles=PROFILE,
                    profile_text="Gestão - Administração",
                ),
            ),
            transmissions=tuple(transmission(item, order="1ª") for item in range(4)),
        )
        assignments = [
            Assignment(
                transmission_id=identifier,
                teacher_id=0,
                status="ALOCADA",
                reason="",
                eligible_teacher_count=1,
                allocation_reason="Regra por etapa",
            )
            for identifier in range(4)
        ]
        result = AllocationResult(
            status="COMPLETA",
            solver_status="OPTIMAL",
            assignments=assignments,
            teacher_loads={0: 8},
            objective_unassigned=0,
            used_teacher_count=1,
            zero_active_teacher_count=0,
            high_capacity_score=0,
            rescue_scarcity_score=0,
            wall_time_seconds=0.1,
        )

        xlsx_path, _ = write_results(problem, result, self.output_dir)

        workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
        try:
            worksheet = workbook["DOCENTES"]
            headers = [cell.value for cell in worksheet[1]]
            row = dict(zip(headers, next(worksheet.iter_rows(min_row=2, values_only=True))))
            # A CH_LETIVA da base fica intacta; a alocável desce para o múltiplo.
            self.assertEqual(9, row["CH_LETIVA"])
            self.assertEqual(8, row["CH_LETIVA_ALOCÁVEL"])
            self.assertEqual(8, row["CH_ALOCADA_1ª_ETAPA"])
            # Cheio contra o teto real: folga zero e 100%, não 8/9 = 88,9%.
            self.assertEqual(0, row["CH_DISPONÍVEL_1ª_ETAPA"])
            self.assertEqual(1, row["UTILIZAÇÃO_1ª_ETAPA"])
            self.assertEqual(1, row["UTILIZAÇÃO_PICO"])
            self.assertEqual(0, row["CH_DISPONÍVEL"])
            self.assertEqual("NAO", row["EXCEDE_CH_LETIVA"])

            por_cargo = workbook["DOCENTES POR CARGO"]
            cabecalho = [cell.value for cell in por_cargo[1]]
            linhas = [
                dict(zip(cabecalho, values))
                for values in por_cargo.iter_rows(min_row=2, values_only=True)
            ]
            regime = next(linha for linha in linhas if linha["REGIME"].startswith("T12"))
            # A abertura por cargo soma a alocável, não a CH letiva da base.
            self.assertEqual(8, regime["CH_LETIVA_ALOCÁVEL"])
            self.assertEqual(1, regime["UTILIZAÇÃO_PICO"])
        finally:
            workbook.close()


if __name__ == "__main__":
    unittest.main()
