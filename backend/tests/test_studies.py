"""Estudo em lote: a mesma premissa projetada sobre vários módulos do ano."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import unittest
import uuid
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

DOCENTES_HEADERS = (
    "CHAPA", "NOME", "NM_FUNCAO", "CH_CONTRATADA", "CH_LETIVA",
    "GESTOR", "STATUS", "PERFIL_DISCIPLINA",
)
MAPA_HEADERS = (
    "CURSO", "NOME_CURSO", "COD_DISCIPLINA", "NOME_DISCIPLINA", "DIA_AULA",
    "HORÁRIO", "ORDEM", "PERFIL_DISCIPLINA", "CLUSTER", "SINERGIA",
    "FORMATO_AULA",
)

# A base docente é a mesma em todos os módulos porque o recorte por módulo
# copia a aba DOCENTES inteira; é justamente essa igualdade que dá sentido a
# uma premissa por chapa valer para o ano todo.
DOCENTES = [
    ["100", "Ana Souza", "PROFESSOR REGENTE", 40, 8, "Gestor", "ATIVO", "GESTÃO"],
    ["200", "Bruno Lima", "PROFESSOR REGENTE", 20, 20, "Gestor", "ATIVO", "GESTÃO"],
]


def _artifact(path: Path, round_dir: Path) -> dict:
    return {
        "path": str(path.relative_to(round_dir)),
        "size_bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


class StudyApiTests(unittest.TestCase):
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
        self.database = self.app.state.database

    def tearDown(self) -> None:
        self.client_context.__exit__(None, None, None)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Fixture: um lote executado, com uma rodada-base concluída por módulo.
    # ------------------------------------------------------------------

    def _build_source(self, module: int, teachers: list[list]) -> Path:
        path = self.data_dir / f"base_M{module}.xlsx"
        workbook = Workbook()
        docentes = workbook.active
        docentes.title = "DOCENTES"
        docentes.append(list(DOCENTES_HEADERS))
        for row in teachers:
            docentes.append(row)
        mapa = workbook.create_sheet("MAPA PEDAGÓGICO")
        mapa.append(list(MAPA_HEADERS))
        mapa.append([
            "ADM", "Administração", f"ADM{module}", f"Disciplina {module}",
            "SEGUNDA", "19:00", "1ª", "GESTÃO", "GESTÃO E NEGÓCIOS",
            "Curso único", "Ao vivo",
        ])
        workbook.save(path)
        workbook.close()
        return path

    def _build_round(self, module: int, source: Path) -> Path:
        round_dir = self.data_dir / f"rodada_M{module}"
        source_copy = round_dir / "fonte" / source.name
        summary_path = round_dir / "alocacao" / "resumo_alocacao.json"
        source_copy.parent.mkdir(parents=True)
        summary_path.parent.mkdir(parents=True)
        shutil.copy2(source, source_copy)
        summary_path.write_text(
            json.dumps({
                "transmissions": 1,
                "allocated": 1,
                "unassigned": 0,
                "used_teachers": 1,
                "hours_per_transmission": 2,
                "solver_status": "OPTIMAL",
                "eligibility_criterion": "PERFIL_EXATO",
                "decisions": [{
                    "source_row": 2,
                    "status": "ALOCADA",
                    "discipline_code": f"ADM{module}",
                    "discipline_name": f"Disciplina {module}",
                    "teacher_badge": "100",
                    "teacher_name": "Ana Souza",
                    "contract_model": "CLT EAD",
                }],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        (round_dir / "manifesto.json").write_text(
            json.dumps({
                "artifacts": {
                    "source_copy": _artifact(source_copy, round_dir),
                    "allocation_summary": _artifact(summary_path, round_dir),
                },
                "phases": {
                    "validation": {"status": "APROVADO"},
                    "audit": {"status": "APROVADO"},
                },
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        return round_dir

    def _seed_batch(
        self,
        modules: tuple[int, ...] = (51, 52, 53),
        teachers_by_module: dict[int, list[list]] | None = None,
    ) -> str:
        """Um lote concluído: upload, rodada e artefatos por módulo."""
        batch_id = uuid.uuid4().hex
        now = "2026-07-15T00:00:00+00:00"
        entries = []
        for module in modules:
            teachers = (teachers_by_module or {}).get(module, DOCENTES)
            source = self._build_source(module, teachers)
            round_dir = self._build_round(module, source)
            upload_id = f"upload-{batch_id}-{module}"
            job_id = f"job-{batch_id}-{module}"
            self.database.create_upload({
                "id": upload_id, "original_name": source.name,
                "stored_path": str(source), "module": module,
                "validation_status": "APROVADO",
                "validation_path": str(self.data_dir / "v.json"),
                "validation_csv_path": str(self.data_dir / "v.xlsx"),
                "created_at": now,
            })
            self.database.create_job({
                "id": job_id, "upload_id": upload_id, "status": "CONCLUIDA",
                "message": "ok", "module": module, "require_optimal": True,
                "time_limit_seconds": None, "batch_id": batch_id,
                "created_at": now, "updated_at": now,
            })
            self.database.update_job(
                job_id,
                round_name=f"rodada_M{module}",
                round_dir=str(round_dir),
            )
            entries.append({
                "module": module, "upload_id": upload_id,
                "filename": source.name, "validation_status": "APROVADO",
                "runnable": True, "reason": "", "validation": None,
            })
        self.database.create_batch({
            "id": batch_id, "name": "Ano letivo", "criterion": "PERFIL_EXATO",
            "profile": "PROVA_COMPLETA", "margin_offers": None,
            "require_optimal": True, "time_limit_seconds": None,
            "modules_json": entries, "created_at": now,
        })
        return batch_id

    def _create_study(self, batch_id: str, modules: list[int]) -> dict:
        response = self.client.post("/api/studies", json={
            "batch_id": batch_id,
            "modules": modules,
            "name": "Demitir Ana a partir do 51",
            "description": "Ver o efeito do corte em cada módulo do ano.",
        })
        self.assertEqual(201, response.status_code, response.text)
        return response.json()

    # ------------------------------------------------------------------
    # Criação
    # ------------------------------------------------------------------

    def test_baseline_listing_only_offers_batches_with_finished_rounds(self) -> None:
        batch_id = self._seed_batch((51, 52))
        response = self.client.get("/api/studies/baselines")
        self.assertEqual(200, response.status_code)
        options = response.json()
        self.assertEqual([batch_id], [item["id"] for item in options])
        self.assertEqual([51, 52], [item["module"] for item in options[0]["modules"]])

    def test_study_creates_one_child_scenario_per_module(self) -> None:
        batch_id = self._seed_batch((51, 52, 53))
        study = self._create_study(batch_id, [51, 52, 53])
        self.assertEqual([51, 52, 53], [row["module"] for row in study["modules"]])
        self.assertTrue(all(row["scenario_id"] for row in study["modules"]))
        # Cada filho aponta para a rodada-base do seu próprio módulo.
        for row in study["modules"]:
            self.assertEqual(
                row["baseline_job_id"], row["scenario"]["baseline_job_id"]
            )
            self.assertEqual(study["id"], row["scenario"]["study_id"])

    def test_child_scenarios_stay_out_of_the_standalone_listing(self) -> None:
        """O seletor da tela lista perguntas, não os quatro módulos de cada uma."""
        batch_id = self._seed_batch((51, 52))
        self._create_study(batch_id, [51, 52])
        self.assertEqual([], self.client.get("/api/scenarios").json())

    def test_study_refuses_modules_without_a_finished_round(self) -> None:
        batch_id = self._seed_batch((51, 52))
        response = self.client.post("/api/studies", json={
            "batch_id": batch_id, "modules": [51, 54], "name": "Corte anual",
        })
        self.assertEqual(409, response.status_code)
        self.assertIn("módulo 54", response.json()["detail"])

    def test_study_refuses_divergent_teacher_bases(self) -> None:
        """Chapas diferentes entre módulos fariam a premissa mudar de alvo."""
        outra_base = [
            ["100", "Outra Pessoa", "PROFESSOR REGENTE", 40, 8, "Gestor", "ATIVO", "GESTÃO"],
        ]
        batch_id = self._seed_batch(
            (51, 52), teachers_by_module={52: outra_base}
        )
        response = self.client.post("/api/studies", json={
            "batch_id": batch_id, "modules": [51, 52], "name": "Corte anual",
        })
        self.assertEqual(409, response.status_code)
        detail = response.json()["detail"]
        self.assertIn("mesma base docente", detail)
        self.assertIn("52", detail)

    # ------------------------------------------------------------------
    # Premissas e projeção
    # ------------------------------------------------------------------

    def test_premise_by_badge_reaches_every_selected_module(self) -> None:
        batch_id = self._seed_batch((51, 52, 53))
        study = self._create_study(batch_id, [51, 52, 53])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100"], "field_name": "STATUS",
            "new_value": "DEMITIDO",
        })
        self.assertEqual(201, response.status_code, response.text)
        payload = response.json()
        self.assertEqual(
            [1, 1, 1], [item["applied_count"] for item in payload["projection"]]
        )
        # A premissa vira uma alteração concreta no cenário de cada módulo,
        # com o valor antigo lido da planilha daquele módulo.
        for row in payload["study"]["modules"]:
            changes = row["scenario"]["changes"]
            self.assertEqual(1, len(changes))
            self.assertEqual("STATUS", changes[0]["field_name"])
            self.assertEqual("ATIVO", changes[0]["old_value"])
            self.assertEqual("DEMITIDO", changes[0]["new_value"])
        self.assertEqual(3, payload["study"]["totals"]["runnable"])

    def test_module_scope_limits_the_premise_to_the_chosen_modules(self) -> None:
        """'A partir do 52' não pode mexer no 51."""
        batch_id = self._seed_batch((51, 52, 53))
        study = self._create_study(batch_id, [52, 53])
        self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100"], "field_name": "STATUS",
            "new_value": "DEMITIDO",
        })
        detail = self.client.get(f"/api/studies/{study['id']}").json()
        self.assertEqual([52, 53], [row["module"] for row in detail["modules"]])
        self.assertTrue(all(row["change_count"] == 1 for row in detail["modules"]))

    def test_premise_refused_in_a_module_is_reported_not_silently_dropped(self) -> None:
        """Bruno já usa toda a CH contratada: subir a letiva reprovaria a validação."""
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["200"], "field_name": "CH_LETIVA", "new_value": 40,
        })
        self.assertEqual(201, response.status_code, response.text)
        projection = response.json()["projection"]
        self.assertEqual([0, 0], [item["applied_count"] for item in projection])
        self.assertIn("CH contratada", projection[0]["results"][0]["reason"])

        # Sem alteração projetada não há o que simular, e a recusa é explícita.
        run = self.client.post(f"/api/studies/{study['id']}/runs")
        self.assertEqual(409, run.status_code)
        self.assertIn("Nenhum módulo", run.json()["detail"])

    def test_premise_repeating_the_current_value_is_refused_per_module(self) -> None:
        batch_id = self._seed_batch((51,))
        study = self._create_study(batch_id, [51])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100"], "field_name": "STATUS", "new_value": "ATIVO",
        })
        projection = response.json()["projection"]
        self.assertEqual(0, projection[0]["applied_count"])
        self.assertIn("já está nesse valor", projection[0]["results"][0]["reason"])

    def test_relative_adjustment_preserves_each_teacher_own_load(self) -> None:
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100"], "field_name": "CH_LETIVA", "adjustment": 4,
        })
        self.assertEqual(201, response.status_code, response.text)
        for row in response.json()["study"]["modules"]:
            change = row["scenario"]["changes"][0]
            self.assertEqual(8, change["old_value"])
            self.assertEqual(12, change["new_value"])

    def test_unknown_badge_is_refused_before_touching_any_module(self) -> None:
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["999"], "field_name": "STATUS", "new_value": "DEMITIDO",
        })
        self.assertEqual(409, response.status_code)
        self.assertIn("Alvo fora da base do estudo (chapa)", response.json()["detail"])
        detail = self.client.get(f"/api/studies/{study['id']}").json()
        self.assertTrue(all(row["change_count"] == 0 for row in detail["modules"]))

    def test_agenda_by_course_reaches_every_module(self) -> None:
        """"E se eu mudasse esse curso de dia?" vale para o ano todo."""
        batch_id = self._seed_batch((51, 52, 53))
        study = self._create_study(batch_id, [51, 52, 53])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "AGENDA", "target_type": "COURSE",
            "target_values": ["ADM"], "field_name": "DIA_AULA",
            "new_value": "QUARTA",
        })
        self.assertEqual(201, response.status_code, response.text)
        payload = response.json()
        self.assertEqual(
            [1, 1, 1], [item["applied_count"] for item in payload["projection"]]
        )
        # A premissa é do curso, mas escreve na linha que aquele módulo usa.
        for row in payload["study"]["modules"]:
            change = row["scenario"]["changes"][0]
            self.assertEqual("offer", change["entity_type"])
            self.assertEqual("DIA_AULA", change["field_name"])
            self.assertEqual("SEGUNDA", change["old_value"])
            self.assertEqual("QUARTA", change["new_value"])

    def test_agenda_by_discipline_only_touches_the_modules_that_have_it(self) -> None:
        """Cada módulo tem a sua disciplina; a premissa não inventa alvo nos outros."""
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "AGENDA", "target_type": "DISCIPLINE",
            "target_values": ["ADM51"], "field_name": "HORÁRIO",
            "new_value": "21:00",
        })
        self.assertEqual(201, response.status_code, response.text)
        projection = {item["module"]: item for item in response.json()["projection"]}
        self.assertEqual(1, projection[51]["applied_count"])
        self.assertEqual(0, projection[52]["applied_count"])
        self.assertIn("não existe neste módulo", projection[52]["results"][0]["reason"])

    def test_offer_and_teacher_premises_coexist_in_the_same_study(self) -> None:
        """Demitir alguém e mover um curso são premissas do mesmo estudo."""
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        for payload in (
            {"premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
             "target_values": ["100"], "field_name": "STATUS",
             "new_value": "DEMITIDO"},
            {"premise_type": "AGENDA", "target_type": "COURSE",
             "target_values": ["ADM"], "field_name": "DIA_AULA",
             "new_value": "QUARTA"},
        ):
            response = self.client.post(
                f"/api/studies/{study['id']}/premises", json=payload
            )
            self.assertEqual(201, response.status_code, response.text)
        detail = self.client.get(f"/api/studies/{study['id']}").json()
        for row in detail["modules"]:
            entities = sorted(
                item["entity_type"] for item in row["scenario"]["changes"]
            )
            self.assertEqual(["offer", "teacher"], entities)

    def test_agenda_refuses_a_course_absent_from_the_study(self) -> None:
        batch_id = self._seed_batch((51,))
        study = self._create_study(batch_id, [51])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "AGENDA", "target_type": "COURSE",
            "target_values": ["ENF"], "field_name": "DIA_AULA",
            "new_value": "QUARTA",
        })
        self.assertEqual(409, response.status_code)
        self.assertIn("Alvo fora da base do estudo (curso)", response.json()["detail"])

    def test_many_targets_become_one_premise_each(self) -> None:
        batch_id = self._seed_batch((51,))
        study = self._create_study(batch_id, [51])
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100", "200"], "field_name": "STATUS",
            "new_value": "DEMITIDO",
        })
        self.assertEqual(201, response.status_code, response.text)
        study_payload = response.json()["study"]
        self.assertEqual(2, len(study_payload["premises"]))
        self.assertEqual(
            ["100", "200"],
            sorted(item["target_value"] for item in study_payload["premises"]),
        )
        self.assertEqual(2, response.json()["projection"][0]["applied_count"])

    def test_catalog_reports_where_each_course_hurts(self) -> None:
        """A contagem de lacunas por módulo é o que aponta o curso a estudar."""
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        catalog = self.client.get(f"/api/studies/{study['id']}/catalog").json()
        self.assertEqual([51, 52], catalog["modules"])
        curso = next(item for item in catalog["courses"] if item["code"] == "ADM")
        self.assertEqual([51, 52], [row["module"] for row in curso["modules"]])
        self.assertEqual(2, curso["total_offers"])
        self.assertEqual(0, curso["total_unassigned"])
        self.assertEqual(["SEGUNDA"], curso["days"])
        # Cada módulo traz a sua disciplina, e o catálogo diz onde ela existe.
        codigos = {item["code"] for item in catalog["disciplines"]}
        self.assertEqual({"ADM51", "ADM52"}, codigos)
        self.assertEqual(
            [{"value": "SEGUNDA", "offers": 2}], catalog["practiced"]["days"]
        )

    def test_deleting_a_premise_undoes_what_it_produced_in_every_module(self) -> None:
        """A projeção é reescrita do zero, então apagar a premissa apaga o efeito."""
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        created = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100"], "field_name": "STATUS",
            "new_value": "DEMITIDO",
        }).json()
        premise_id = created["study"]["premises"][0]["id"]

        removed = self.client.delete(
            f"/api/studies/{study['id']}/premises/{premise_id}"
        )
        self.assertEqual(204, removed.status_code)
        detail = self.client.get(f"/api/studies/{study['id']}").json()
        self.assertEqual([], detail["premises"])
        self.assertTrue(all(row["change_count"] == 0 for row in detail["modules"]))
        for row in detail["modules"]:
            self.assertEqual([], row["scenario"]["changes"])

    def test_two_premises_on_the_same_teacher_coexist_by_field(self) -> None:
        batch_id = self._seed_batch((51,))
        study = self._create_study(batch_id, [51])
        for field, value in (("STATUS", "DEMITIDO"), ("CH_LETIVA", 4)):
            response = self.client.post(f"/api/studies/{study['id']}/premises", json={
                "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
                "target_values": ["100"], "field_name": field, "new_value": value,
            })
            self.assertEqual(201, response.status_code, response.text)
        detail = self.client.get(f"/api/studies/{study['id']}").json()
        self.assertEqual(2, len(detail["premises"]))
        self.assertEqual(2, detail["modules"][0]["change_count"])

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------

    def _fake_scenario_run(self, scenario_id: str, module: int) -> str:
        """Registra uma simulação concluída para aquele cenário do estudo.

        Aponta para os artefatos da rodada-base do módulo: o que os testes de
        estado precisam é de um job CONCLUIDA com resumo legível, e não de uma
        execução real do motor secundário.
        """
        scenario = self.database.get_scenario(scenario_id)
        job_id = uuid.uuid4().hex
        now = "2026-07-16T00:00:00+00:00"
        self.database.create_job({
            "id": job_id, "upload_id": scenario["upload_id"],
            "status": "CONCLUIDA", "message": "ok", "module": module,
            "require_optimal": True, "time_limit_seconds": None,
            "kind": "SCENARIO", "scenario_id": scenario_id,
            "created_at": now, "updated_at": now,
        })
        self.database.update_job(
            job_id,
            round_name=f"rodada_M{module}",
            round_dir=str(self.data_dir / f"rodada_M{module}"),
        )
        self.database.create_scenario_run({
            "scenario_id": scenario_id, "job_id": job_id,
            "input_path": str(self.data_dir / "entrada.xlsx"),
            "changes_path": str(self.data_dir / "alteracoes.json"),
            "created_at": now,
        })
        self.database.update_scenario(scenario_id, status="CONCLUIDO")
        return job_id

    def _premise(self, study_id: str) -> None:
        response = self.client.post(f"/api/studies/{study_id}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100"], "field_name": "STATUS",
            "new_value": "DEMITIDO",
        })
        self.assertEqual(201, response.status_code, response.text)

    def test_run_enqueues_every_module_at_once(self) -> None:
        """O teto normal da fila de cenários é 2; um estudo de 3 entra inteiro."""
        batch_id = self._seed_batch((51, 52, 53))
        study = self._create_study(batch_id, [51, 52, 53])
        self._premise(study["id"])

        manager = self.app.state.scenario_manager
        pending: Future = Future()
        with patch.object(manager.executor, "submit", return_value=pending):
            started = self.client.post(f"/api/studies/{study['id']}/runs")
        self.assertEqual(202, started.status_code, started.text)
        payload = started.json()
        self.assertEqual("EXECUTANDO", payload["status"])
        self.assertEqual(3, payload["totals"]["queued_or_running"])
        jobs = [row["job"] for row in payload["modules"]]
        self.assertEqual([51, 52, 53], [job["module"] for job in jobs])
        self.assertTrue(all(job["status"] == "QUEUED" for job in jobs))
        self.assertTrue(all(job["kind"] == "SCENARIO" for job in jobs))
        pending.cancel()

    def test_premises_are_frozen_while_the_study_simulates(self) -> None:
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        self._premise(study["id"])

        manager = self.app.state.scenario_manager
        pending: Future = Future()
        with patch.object(manager.executor, "submit", return_value=pending):
            self.client.post(f"/api/studies/{study['id']}/runs")
            blocked = self.client.post(f"/api/studies/{study['id']}/premises", json={
                "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
                "target_values": ["200"], "field_name": "STATUS",
                "new_value": "DEMITIDO",
            })
        self.assertEqual(409, blocked.status_code)
        self.assertIn("simulando", blocked.json()["detail"].lower())
        pending.cancel()

    def test_study_in_flight_cannot_be_deleted(self) -> None:
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        self._premise(study["id"])

        manager = self.app.state.scenario_manager
        pending: Future = Future()
        with patch.object(manager.executor, "submit", return_value=pending):
            self.client.post(f"/api/studies/{study['id']}/runs")
            blocked = self.client.delete(f"/api/studies/{study['id']}")
        self.assertEqual(409, blocked.status_code)
        self.assertIn("execução", blocked.json()["detail"])
        pending.cancel()

    def test_a_homologated_module_is_preserved_when_premises_change(self) -> None:
        """Reprojetar não pode reescrever o que já virou resultado oficial."""
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        self._premise(study["id"])
        homologado = study["modules"][0]["scenario_id"]
        self.database.update_scenario(str(homologado), status="HOMOLOGADO")

        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "CAPACIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["100"], "field_name": "CH_LETIVA", "adjustment": -4,
        })
        self.assertEqual(201, response.status_code, response.text)
        projection = {item["module"]: item for item in response.json()["projection"]}
        self.assertTrue(projection[51]["locked"])
        self.assertIn("homologado", projection[51]["reason"].lower())
        # O módulo aberto recebeu as duas premissas; o homologado ficou intacto.
        self.assertEqual(2, projection[52]["applied_count"])
        self.assertEqual(
            1, len(self.database.list_scenario_changes(str(homologado)))
        )

    def test_a_finished_module_is_marked_stale_when_premises_change(self) -> None:
        """O número da simulação anterior não pode ficar ao lado da premissa nova.

        É o erro mais perigoso possível aqui: a cobertura antiga parece uma
        resposta à pergunta escrita na tela, e é a resposta a outra pergunta.
        """
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        self._premise(study["id"])

        for entry in self.database.study_modules(study["id"]):
            self._fake_scenario_run(str(entry["scenario_id"]), int(entry["module"]))
        detail = self.client.get(f"/api/studies/{study['id']}").json()
        self.assertTrue(all(not row["stale"] for row in detail["modules"]))
        # Antes da mudança os indicadores estão lá; é justamente o que não pode
        # sobreviver à premissa nova.
        self.assertTrue(all(row["kpis"] for row in detail["modules"]))

        # Uma premissa nova muda o conjunto de alterações dos dois módulos.
        response = self.client.post(f"/api/studies/{study['id']}/premises", json={
            "premise_type": "COMPATIBILIDADE", "target_type": "TEACHER_BADGE",
            "target_values": ["200"], "field_name": "PERFIL_DISCIPLINA",
            "new_value": "SAÚDE",
        })
        self.assertEqual(201, response.status_code, response.text)
        for row in response.json()["study"]["modules"]:
            self.assertTrue(row["stale"], f"módulo {row['module']}")
            self.assertIsNone(row["kpis"])

    def test_reprojecting_the_same_premises_keeps_the_result_valid(self) -> None:
        """Reprojetar sem mudar nada não pode invalidar uma simulação boa."""
        batch_id = self._seed_batch((51,))
        study = self._create_study(batch_id, [51])
        self._premise(study["id"])
        scenario_id = str(self.database.study_modules(study["id"])[0]["scenario_id"])
        self._fake_scenario_run(scenario_id, 51)

        projection = self.client.get(f"/api/studies/{study['id']}/projection")
        self.assertEqual(200, projection.status_code, projection.text)
        detail = self.client.get(f"/api/studies/{study['id']}").json()
        self.assertFalse(detail["modules"][0]["stale"])
        self.assertEqual(
            "CONCLUIDO", self.database.get_scenario(scenario_id)["status"]
        )

    # ------------------------------------------------------------------
    # Leitura e exclusão
    # ------------------------------------------------------------------

    def test_catalog_lists_the_shared_teacher_base(self) -> None:
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        catalog = self.client.get(f"/api/studies/{study['id']}/catalog")
        self.assertEqual(200, catalog.status_code, catalog.text)
        self.assertEqual(
            ["100", "200"],
            sorted(item["badge"] for item in catalog.json()["teachers"]),
        )

    def test_study_totals_report_the_baseline_of_the_year(self) -> None:
        batch_id = self._seed_batch((51, 52, 53))
        study = self._create_study(batch_id, [51, 52, 53])
        self.assertEqual("AGUARDANDO", study["status"])
        self.assertEqual(3, study["totals"]["modules"])
        for row in study["modules"]:
            self.assertEqual(100.0, row["baseline_kpis"]["coverage_pct"])

    def test_create_and_read_return_the_same_shape(self) -> None:
        batch_id = self._seed_batch((51, 52))
        created = self._create_study(batch_id, [51, 52])
        read = self.client.get(f"/api/studies/{created['id']}").json()
        listed = self.client.get("/api/studies").json()[0]
        self.assertEqual(created, read)
        self.assertEqual(sorted(created), sorted(listed))

    def test_deleting_a_study_takes_its_child_scenarios(self) -> None:
        batch_id = self._seed_batch((51, 52))
        study = self._create_study(batch_id, [51, 52])
        scenario_ids = [row["scenario_id"] for row in study["modules"]]
        removed = self.client.delete(f"/api/studies/{study['id']}")
        self.assertEqual(200, removed.status_code, removed.text)
        self.assertEqual([], self.client.get("/api/studies").json())
        for scenario_id in scenario_ids:
            self.assertIsNone(self.database.get_scenario(str(scenario_id)))

    def test_deleting_the_batch_takes_the_studies_built_on_it(self) -> None:
        """Sem o lote não há rodada-base por módulo: o estudo perde o chão."""
        batch_id = self._seed_batch((51, 52))
        self._create_study(batch_id, [51, 52])
        removed = self.client.delete(f"/api/batches/{batch_id}")
        self.assertEqual(200, removed.status_code, removed.text)
        self.assertEqual([], self.client.get("/api/studies").json())

    def test_resetting_scenarios_clears_the_study_as_one_unit(self) -> None:
        """Zerar 'o último' não pode deixar o estudo com um módulo a menos."""
        batch_id = self._seed_batch((51, 52))
        self._create_study(batch_id, [51, 52])
        removed = self.client.delete("/api/scenarios?scope=latest")
        self.assertEqual(200, removed.status_code, removed.text)
        self.assertEqual(2, removed.json()["deleted_scenarios"])
        self.assertEqual([], self.client.get("/api/studies").json())


if __name__ == "__main__":
    unittest.main()
