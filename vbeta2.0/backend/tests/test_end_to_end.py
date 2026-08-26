"""Fluxo completo pela API, com o motor real, e a integridade dos artefatos.

Os demais testes verificam peças. Este verifica a promessa: uma planilha entra
pela API, o motor principal roda como subprocesso de verdade, a rodada é
publicada e todas as telas que leem essa rodada precisam contar a mesma
história. Um número que diverge entre Dashboard, Insights e a lista de
decisões não é uma diferença de arredondamento — é a aplicação afirmando duas
coisas incompatíveis sobre o mesmo resultado.

A segunda metade cobre a garantia que a tela de Exportação anuncia ao usuário:
os artefatos são conferidos por SHA-256 antes de serem entregues. Um resultado
adulterado depois da auditoria precisa ser recusado, e não baixado.
"""

from __future__ import annotations

import json
import shutil
import time as clock
import unittest
import uuid
from datetime import time
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.config import Settings
from app.main import create_app


REPO_ROOT = Path(__file__).resolve().parents[2]
XLSX_MEDIA_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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

# Uma oferta a mais do que os docentes conseguem cobrir. Uma base 100% coberta
# nunca exercitaria motivo de pendência, lacuna por curso nem o painel de
# oportunidades — justamente o que o operador mais consulta.
OFFERS = (
    ("D1", "a", "1ª", "SEGUNDA", 19, "5"),
    ("D2", "a", "2ª", "TERÇA", 19, "10"),
    ("D3", "a", "ESTENDIDA", "QUARTA", 20, "10"),
    ("D4", "z", "1ª", "QUINTA", 19, "5"),
)


def workbook_bytes() -> bytes:
    workbook = Workbook()
    mapa = workbook.active
    mapa.title = "MAPA PEDAGÓGICO"
    mapa.append(MAPA_HEADERS)
    for code, profile, order, day, hour, proof in OFFERS:
        mapa.append((
            "C1", "Curso Um", f"CURR{code}", code, f"Disciplina {code}",
            profile, 2025, 52, "1º", order, "VALIDADO",
            "ESTENDIDA" if order == "ESTENDIDA" else "5 SEMANAS",
            "ONLINE", proof, "N", "CLUSTER", "GESTAO", "Coordenador",
            "CLT EAD", "CURSO ÚNICO", day, time(hour, 0), "AO VIVO",
        ))
    docentes = workbook.create_sheet("DOCENTES")
    docentes.append(DOCENTES_HEADERS)
    docentes.append((
        "Docente A", "000000000001", "PROFESSOR REGENTE", 40, 6, "Gestor",
        "ATIVO", "a",
    ))
    docentes.append((
        "Docente B", "000000000002", "PROFESSOR REGENTE", 40, 4, "Gestor",
        "ATIVO", "a",
    ))
    buffer = BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


class EndToEndRoundTests(unittest.TestCase):
    """Sobe a aplicação real e roda o motor principal de verdade."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data_dir = REPO_ROOT / "data" / "test_runs" / uuid.uuid4().hex
        cls.data_dir.mkdir(parents=True, exist_ok=False)
        cls.settings = Settings(
            repo_root=REPO_ROOT,
            tela_dir=REPO_ROOT,
            vbeta_dir=REPO_ROOT / "engines" / "primary",
            data_dir=cls.data_dir,
        )
        cls.app = create_app(cls.settings)
        cls.client_context = TestClient(cls.app, base_url="http://localhost")
        cls.client = cls.client_context.__enter__()

        upload = cls.client.post(
            "/api/uploads",
            data={"module": "52", "criterion": "PERFIL_EXATO",
                  "profile": "PROVA_COMPLETA"},
            files={"file": ("base.xlsx", workbook_bytes(), XLSX_MEDIA_TYPE)},
        )
        assert upload.status_code == 200, upload.text
        cls.upload = upload.json()

        created = cls.client.post(
            "/api/jobs",
            json={"upload_id": cls.upload["id"], "confirm_warnings": True},
        )
        assert created.status_code == 202, created.text
        cls.job_id = created.json()["id"]

        # O motor roda como subprocesso; esperar é parte do contrato.
        deadline = clock.monotonic() + 300
        job = created.json()
        while clock.monotonic() < deadline:
            job = cls.client.get(f"/api/jobs/{cls.job_id}").json()
            if job["terminal"]:
                break
            clock.sleep(0.3)
        cls.job = job

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)
        shutil.rmtree(cls.data_dir, ignore_errors=True)

    def test_the_round_is_published_optimal_and_audited(self) -> None:
        self.assertEqual("CONCLUIDA", self.job["status"], self.job["message"])
        self.assertEqual(0, self.job["exit_code"])
        self.assertIsNotNone(self.job["round"])

        manifest = self.client.get(
            f"/api/jobs/{self.job_id}/artifacts/manifest"
        ).json()
        self.assertEqual("APROVADO", manifest["phases"]["audit"]["status"])
        self.assertEqual(
            "OPTIMAL", manifest["phases"]["solver"]["solver_status"]
        )
        self.assertIn(
            manifest["phases"]["validation"]["status"],
            {"APROVADO", "APROVADO_COM_RESSALVAS"},
        )
        self.assertEqual(0, manifest["phases"]["audit"]["issue_count"])

    def test_every_screen_reports_the_same_round(self) -> None:
        # O mesmo número, lido por caminhos independentes: resumo, planilha
        # (Dashboard), planilha + resumo (Insights) e a lista paginada.
        summary = self.client.get(f"/api/jobs/{self.job_id}/summary").json()
        dashboard = self.client.get(f"/api/dashboard/{self.job_id}").json()
        insights = self.client.get(f"/api/insights/{self.job_id}").json()
        allocations = self.client.get(
            f"/api/jobs/{self.job_id}/allocations",
            params={"page_size": 200},
        ).json()

        self.assertEqual(len(OFFERS), summary["transmissions"])
        self.assertEqual(summary["transmissions"], dashboard["kpis"]["transmissions"])
        self.assertEqual(summary["transmissions"], allocations["total"])
        self.assertEqual(summary["allocated"], dashboard["kpis"]["allocated"])
        self.assertEqual(summary["unassigned"], dashboard["kpis"]["unassigned"])
        self.assertAlmostEqual(
            dashboard["kpis"]["coverage_pct"],
            insights["kpis"]["coverage_pct"],
            places=2,
        )
        self.assertEqual(
            summary["allocated"],
            sum(
                item["status"] == "ALOCADA" for item in allocations["items"]
            ),
        )
        self.assertEqual(
            summary["unassigned"] * summary["hours_per_transmission"],
            insights["kpis"]["unassigned_demand_hours"],
        )
        self.assertEqual(
            summary["hours_per_transmission"],
            insights["kpis"]["hours_per_transmission"],
        )

    def test_the_uncoverable_offer_is_reported_with_a_reason(self) -> None:
        # A oferta de perfil "z" não tem docente compatível. Ela precisa
        # aparecer como pendência explicada, e não sumir silenciosamente.
        allocations = self.client.get(
            f"/api/jobs/{self.job_id}/allocations",
            params={"page_size": 200, "status": "NAO_ALOCADA"},
        ).json()
        self.assertEqual(1, allocations["total"])
        pending = allocations["items"][0]
        self.assertEqual("D4", pending["discipline_code"])
        self.assertEqual(
            "SEM_DOCENTE_COM_PERFIL_E_CARGA", pending["unassigned_reason"]
        )
        self.assertEqual(0, pending["eligible_teacher_count"])

        dashboard = self.client.get(f"/api/dashboard/{self.job_id}").json()
        self.assertEqual(
            [{"reason": "SEM_DOCENTE_COM_PERFIL_E_CARGA", "count": 1}],
            dashboard["unassigned_reasons"],
        )

    def test_every_allocation_carries_its_justification(self) -> None:
        # Auditabilidade: nenhuma decisão publicada pode ficar sem motivo.
        allocations = self.client.get(
            f"/api/jobs/{self.job_id}/allocations",
            params={"page_size": 200},
        ).json()
        for item in allocations["items"]:
            with self.subTest(discipline=item["discipline_code"]):
                if item["status"] == "ALOCADA":
                    self.assertTrue(item["allocation_reason"])
                    self.assertTrue(item["teacher_badge"])
                    self.assertFalse(item["unassigned_reason"])
                else:
                    self.assertTrue(item["unassigned_reason"])
                    self.assertIsNone(item["teacher_badge"])

    def test_all_published_artifacts_can_be_downloaded(self) -> None:
        for key in (
            "allocation_workbook",
            "allocation_summary",
            "audit_report",
            "validation_report",
            "validation_issues",
            "source_copy",
            "manifest",
            "status",
        ):
            with self.subTest(artifact=key):
                response = self.client.get(
                    f"/api/jobs/{self.job_id}/artifacts/{key}"
                )
                self.assertEqual(200, response.status_code)
                self.assertGreater(len(response.content), 0)


class ArtifactIntegrityTests(unittest.TestCase):
    """A conferência SHA-256 que a tela de Exportação promete ao usuário."""

    def setUp(self) -> None:
        self.data_dir = REPO_ROOT / "data" / "test_runs" / uuid.uuid4().hex
        self.data_dir.mkdir(parents=True, exist_ok=False)
        self.addCleanup(shutil.rmtree, self.data_dir, True)
        self.settings = Settings(
            repo_root=REPO_ROOT,
            tela_dir=REPO_ROOT,
            vbeta_dir=REPO_ROOT / "engines" / "primary",
            data_dir=self.data_dir,
        )
        self.app = create_app(self.settings)
        self.client_context = TestClient(self.app, base_url="http://localhost")
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)

        upload = self.client.post(
            "/api/uploads",
            data={"module": "52"},
            files={"file": ("base.xlsx", workbook_bytes(), XLSX_MEDIA_TYPE)},
        )
        self.assertEqual(200, upload.status_code, upload.text)
        created = self.client.post(
            "/api/jobs",
            json={"upload_id": upload.json()["id"], "confirm_warnings": True},
        )
        self.assertEqual(202, created.status_code, created.text)
        self.job_id = created.json()["id"]
        deadline = clock.monotonic() + 300
        while clock.monotonic() < deadline:
            job = self.client.get(f"/api/jobs/{self.job_id}").json()
            if job["terminal"]:
                break
            clock.sleep(0.3)
        self.assertEqual("CONCLUIDA", job["status"], job["message"])
        self.round_dir = Path(
            self.app.state.database.get_job(self.job_id)["round_dir"]
        )

    def _workbook_path(self) -> Path:
        manifest = json.loads(
            (self.round_dir / "manifesto.json").read_text(encoding="utf-8")
        )
        return self.round_dir / manifest["artifacts"]["allocation_workbook"]["path"]

    def test_a_tampered_workbook_is_refused_instead_of_served(self) -> None:
        workbook = self._workbook_path()
        original = workbook.read_bytes()
        self.assertEqual(
            200,
            self.client.get(
                f"/api/jobs/{self.job_id}/artifacts/allocation_workbook"
            ).status_code,
        )

        # Mesmo tamanho, conteúdo diferente: só o hash denuncia.
        workbook.write_bytes(b"X" + original[1:])
        response = self.client.get(
            f"/api/jobs/{self.job_id}/artifacts/allocation_workbook"
        )
        self.assertEqual(404, response.status_code)
        self.assertIn("diverge do manifesto", response.json()["detail"])

        # E o Dashboard, que lê a mesma planilha, também recusa.
        self.assertEqual(
            409, self.client.get(f"/api/dashboard/{self.job_id}").status_code
        )

        workbook.write_bytes(original)
        self.assertEqual(
            200,
            self.client.get(
                f"/api/jobs/{self.job_id}/artifacts/allocation_workbook"
            ).status_code,
        )

    def test_a_tampered_summary_blocks_the_published_numbers(self) -> None:
        manifest = json.loads(
            (self.round_dir / "manifesto.json").read_text(encoding="utf-8")
        )
        summary_path = (
            self.round_dir / manifest["artifacts"]["allocation_summary"]["path"]
        )
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        payload["allocated"] = 999
        summary_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )

        # Nenhuma tela pode publicar um número que a auditoria não assinou.
        self.assertEqual(
            409, self.client.get(f"/api/jobs/{self.job_id}/summary").status_code
        )
        self.assertEqual(
            409, self.client.get(f"/api/dashboard/{self.job_id}").status_code
        )
        self.assertEqual(
            404,
            self.client.get(
                f"/api/jobs/{self.job_id}/artifacts/allocation_summary"
            ).status_code,
        )

    def test_an_artifact_outside_the_round_is_never_served(self) -> None:
        # O manifesto é dado da rodada; um caminho relativo apontando para fora
        # dela não pode virar leitura de arquivo arbitrário.
        manifest_path = self.round_dir / "manifesto.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["artifacts"]["allocation_workbook"]["path"] = (
            "../../../../VERSION"
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

        response = self.client.get(
            f"/api/jobs/{self.job_id}/artifacts/allocation_workbook"
        )
        self.assertEqual(404, response.status_code)
        self.assertNotIn(
            "2.0", response.text, "o conteúdo de fora da rodada vazou"
        )


if __name__ == "__main__":
    unittest.main()
