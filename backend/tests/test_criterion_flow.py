from __future__ import annotations

import shutil
import unittest
import uuid
from datetime import time
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.config import Settings
from app.database import Database
from app.main import create_app
from app.services.scenarios import ScenarioError, add_scenario_policy


REPO_ROOT = Path(__file__).resolve().parents[2]

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


def workbook_bytes() -> bytes:
    workbook = Workbook()
    mapa = workbook.active
    mapa.title = "MAPA PEDAGÓGICO"
    mapa.append(MAPA_HEADERS)
    for code, profile, hour in (("D1", "a", 19), ("D2", "b", 21)):
        mapa.append((
            "C1", "Curso", f"CURR{code}", code, f"Disciplina {code}", profile,
            2025, 52, "1º", "1ª", "VALIDADO", "5 SEMANAS", "ONLINE", 5,
            "N", "CLUSTER", "GESTAO", "Coordenador", "CLT EAD",
            "CURSO ÚNICO", "SEGUNDA", time(hour, 0), "AO VIVO",
        ))
    docentes = workbook.create_sheet("DOCENTES")
    docentes.append(DOCENTES_HEADERS)
    docentes.append((
        "Docente A", "000000000001", "PROFESSOR REGENTE", 40, 10, "Gestor",
        "ATIVO", "a",
    ))
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


class CriterionApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir = REPO_ROOT / "data" / "test_runs" / uuid.uuid4().hex
        self.data_dir.mkdir(parents=True, exist_ok=False)
        self.settings = Settings(
            repo_root=REPO_ROOT,
            tela_dir=REPO_ROOT,
            vbeta_dir=REPO_ROOT / "engines" / "primary",
            data_dir=self.data_dir,
        )
        self.app = create_app(self.settings)
        self.client_context = TestClient(self.app, base_url="http://localhost")
        self.client = self.client_context.__enter__()

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def _upload(self, criterion: str | None):
        data = {"module": "52"}
        if criterion is not None:
            data["criterion"] = criterion
        return self.client.post(
            "/api/uploads",
            data=data,
            files={
                "file": (
                    "base.xlsx",
                    workbook_bytes(),
                    "application/vnd.openxmlformats-officedocument"
                    ".spreadsheetml.sheet",
                )
            },
        )

    def test_upload_defaults_to_the_historical_profile_criterion(self) -> None:
        response = self._upload(None)

        self.assertEqual(200, response.status_code)
        self.assertEqual("PERFIL_EXATO", response.json()["criterion"])

    def test_upload_accepts_each_supported_criterion(self) -> None:
        for criterion in ("PERFIL_EXATO", "CLUSTER_PREFERENCIAL", "CLUSTER_PURO"):
            with self.subTest(criterion=criterion):
                response = self._upload(criterion)
                self.assertEqual(200, response.status_code)
                self.assertEqual(criterion, response.json()["criterion"])

    def test_upload_refuses_an_unknown_criterion(self) -> None:
        response = self._upload("CLUSTER_TOTAL")

        self.assertEqual(422, response.status_code)

    def test_criterion_changes_the_validation_outcome(self) -> None:
        # A oferta D2 usa o perfil "b", coberto apenas pelo cluster.
        strict = self._upload("PERFIL_EXATO").json()["validation"]
        pure = self._upload("CLUSTER_PURO").json()["validation"]

        strict_codes = {issue["code"] for issue in strict["issues"]}
        pure_codes = {issue["code"] for issue in pure["issues"]}

        self.assertIn("PERFIL_SEM_DOCENTE_ATIVO", strict_codes)
        self.assertNotIn("PERFIL_SEM_DOCENTE_ATIVO", pure_codes)

    def test_job_inherits_the_criterion_chosen_at_import(self) -> None:
        upload = self._upload("CLUSTER_PREFERENCIAL").json()

        created = self.client.post(
            "/api/jobs",
            json={"upload_id": upload["id"], "confirm_warnings": True},
        )

        self.assertEqual(202, created.status_code)
        self.assertEqual("CLUSTER_PREFERENCIAL", created.json()["criterion"])


class RedundantClusterPolicyTests(unittest.TestCase):
    """ALOCAR_CLUSTER não pode ser adicionada sobre baseline já em cluster."""

    def setUp(self) -> None:
        self.data_dir = REPO_ROOT / "data" / "test_runs" / uuid.uuid4().hex
        self.data_dir.mkdir(parents=True, exist_ok=False)
        self.database = Database(self.data_dir / "app.sqlite3")
        self.database.initialize()

    def tearDown(self) -> None:
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def _scenario_on(self, criterion: str) -> str:
        self.database.create_upload({
            "id": "upload-1",
            "original_name": "base.xlsx",
            "stored_path": str(self.data_dir / "base.xlsx"),
            "module": 52,
            "criterion": criterion,
            "validation_status": "APROVADO",
            "validation_path": str(self.data_dir / "v.json"),
            "validation_csv_path": str(self.data_dir / "v.xlsx"),
            "created_at": "2026-08-24T00:00:00+00:00",
        })
        self.database.create_job({
            "id": "job-1",
            "upload_id": "upload-1",
            "status": "CONCLUIDA",
            "message": "ok",
            "module": 52,
            "require_optimal": True,
            "criterion": criterion,
            "created_at": "2026-08-24T00:00:00+00:00",
            "updated_at": "2026-08-24T00:00:00+00:00",
        })
        self.database.create_scenario({
            "id": "scenario-1",
            "baseline_job_id": "job-1",
            "name": "Cenário",
            "description": "",
            "status": "RASCUNHO",
            "created_at": "2026-08-24T00:00:00+00:00",
            "updated_at": "2026-08-24T00:00:00+00:00",
        })
        return "scenario-1"

    def test_cluster_baseline_refuses_the_redundant_policy(self) -> None:
        for criterion in ("CLUSTER_PREFERENCIAL", "CLUSTER_PURO"):
            with self.subTest(criterion=criterion):
                shutil.rmtree(self.data_dir, ignore_errors=True)
                self.data_dir.mkdir(parents=True, exist_ok=True)
                self.database = Database(self.data_dir / "app.sqlite3")
                self.database.initialize()
                scenario_id = self._scenario_on(criterion)

                with self.assertRaises(ScenarioError) as error:
                    add_scenario_policy(
                        self.database,
                        scenario_id,
                        policy_type="ALOCAR_CLUSTER",
                        target_type="CLUSTER",
                        target_value="GESTAO",
                    )
                self.assertIn("já utiliza o critério de cluster", str(error.exception))

    def test_scenario_inherits_the_baseline_criterion(self) -> None:
        self._scenario_on("CLUSTER_PURO")
        scenario = self.database.get_scenario("scenario-1")

        self.assertEqual("CLUSTER_PURO", scenario["criterion"])


if __name__ == "__main__":
    unittest.main()
