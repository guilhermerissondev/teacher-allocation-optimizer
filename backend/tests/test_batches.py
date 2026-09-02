"""Processamento em lote: separação por módulo, validação e enfileiramento."""

from __future__ import annotations

import json
import sys
import unittest
import uuid
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.batches import (  # noqa: E402
    BatchError,
    inspect_workbook,
    split_workbook_by_module,
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


def offer_row(code: str, module: int, hour: str = "19:00") -> list:
    """Linha de oferta válida em todos os domínios que a validação cobra."""
    return [
        "ADM", "Administração", "CUR1", code, f"Disciplina {code}",
        "gestão", 2024, module, "1º", "1ª", "VALIDADO", "5 SEMANAS",
        "ONLINE", "5", "N", "CLUSTER", "GESTÃO E NEGÓCIOS", "Coord",
        "CLT EAD", "CURSO ÚNICO", "SEGUNDA", hour, "AO VIVO",
    ]


def offer_row_com_ressalva(code: str, module: int, hour: str = "19:00") -> list:
    """Oferta válida, mas com METODOLOGIA divergente da ORDEM.

    Gera `ORDEM_METODOLOGIA_DIVERGENTE`, de severidade MÉDIA e não bloqueante —
    exatamente a ressalva que o operador precisa ler antes de confirmar.
    """
    linha = offer_row(code, module, hour)
    linha[list(MAPA_HEADERS).index("METODOLOGIA")] = "ESTENDIDA"
    return linha


def teacher_row(name: str, badge: str) -> list:
    return [name, badge, "PROFESSOR REGENTE", 40, 8, "Gestor", "ATIVO", "gestão"]


def build_workbook(path: Path, offers: list[list]) -> Path:
    workbook = Workbook()
    mapa = workbook.active
    mapa.title = "MAPA PEDAGÓGICO"
    mapa.append(list(MAPA_HEADERS))
    for row in offers:
        mapa.append(row)
    docentes = workbook.create_sheet("DOCENTES")
    docentes.append(list(DOCENTES_HEADERS))
    docentes.append(teacher_row("Ana", "000000000001"))
    docentes.append(teacher_row("Bruno", "000000000002"))
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    workbook.close()
    return path


class BatchWorkbookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.data_dir = REPO_ROOT / "data" / "test_runs" / uuid.uuid4().hex
        self.data_dir.mkdir(parents=True, exist_ok=False)

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_inspect_reports_every_module_present(self) -> None:
        path = build_workbook(
            self.data_dir / "anual.xlsx",
            [
                offer_row("D51", 51), offer_row("D51B", 51, "21:00"),
                offer_row("D52", 52),
                offer_row("D99", 99),
            ],
        )
        found = inspect_workbook(path)
        self.assertEqual(
            [
                {"module": 51, "rows": 2, "supported": True},
                {"module": 52, "rows": 1, "supported": True},
                {"module": 99, "rows": 1, "supported": False},
            ],
            found["modules"],
        )
        self.assertEqual(0, found["rows_without_module"])

    def test_inspect_refuses_workbook_without_module_column(self) -> None:
        workbook = Workbook()
        mapa = workbook.active
        mapa.title = "MAPA PEDAGÓGICO"
        mapa.append([header for header in MAPA_HEADERS if header != "MÓD"])
        workbook.create_sheet("DOCENTES").append(list(DOCENTES_HEADERS))
        path = self.data_dir / "sem_modulo.xlsx"
        workbook.save(path)
        workbook.close()
        with self.assertRaises(BatchError) as context:
            inspect_workbook(path)
        self.assertIn("MÓD", str(context.exception))

    def test_split_keeps_only_the_requested_module_and_all_teachers(self) -> None:
        source = build_workbook(
            self.data_dir / "anual.xlsx",
            [offer_row("D51", 51), offer_row("D52", 52), offer_row("D52B", 52, "21:00")],
        )
        destination = split_workbook_by_module(
            source, 52, self.data_dir / "recorte.xlsx"
        )
        workbook = load_workbook(destination, read_only=True, data_only=True)
        try:
            mapa = workbook["MAPA PEDAGÓGICO"]
            rows = list(mapa.iter_rows(min_row=2, values_only=True))
            module_index = list(MAPA_HEADERS).index("MÓD")
            self.assertEqual([52, 52], [row[module_index] for row in rows])
            self.assertEqual(
                list(MAPA_HEADERS),
                [cell for cell in next(mapa.iter_rows(min_row=1, max_row=1, values_only=True))],
            )
            # O corpo docente não se divide por módulo: a capacidade é
            # consumida dentro de cada módulo separadamente.
            docentes = workbook["DOCENTES"]
            self.assertEqual(3, docentes.max_row)
        finally:
            workbook.close()

    def test_split_refuses_module_absent_from_the_workbook(self) -> None:
        source = build_workbook(self.data_dir / "so_51.xlsx", [offer_row("D51", 51)])
        with self.assertRaises(BatchError) as context:
            split_workbook_by_module(source, 54, self.data_dir / "vazio.xlsx")
        self.assertIn("módulo 54", str(context.exception))


class BatchApiTests(unittest.TestCase):
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
        import shutil

        self.client_context.__exit__(None, None, None)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def _upload(self, path: Path, field: str = "files") -> tuple:
        return (
            field,
            (
                path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )

    def test_inspect_endpoint_lists_modules_per_file(self) -> None:
        anual = build_workbook(
            self.data_dir / "anual.xlsx",
            [offer_row("D51", 51), offer_row("D52", 52)],
        )
        response = self.client.post(
            "/api/batches/inspect", files=[self._upload(anual)]
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual([51, 52], payload["available_modules"])
        self.assertEqual("anual.xlsx", payload["files"][0]["filename"])

    def test_single_workbook_with_many_modules_becomes_one_upload_per_module(self) -> None:
        anual = build_workbook(
            self.data_dir / "anual.xlsx",
            [
                offer_row("D51", 51),
                offer_row("D52", 52), offer_row("D52B", 52, "21:00"),
            ],
        )
        response = self.client.post(
            "/api/batches",
            files=[self._upload(anual)],
            data={"modules": "51,52", "name": "Ano letivo"},
        )
        self.assertEqual(201, response.status_code, response.text)
        payload = response.json()
        self.assertEqual([51, 52], [item["module"] for item in payload["modules"]])
        self.assertTrue(all(item["runnable"] for item in payload["modules"]))
        self.assertTrue(all(item["upload_id"] for item in payload["modules"]))
        # O recorte precisa ser identificável como recorte daquele módulo.
        self.assertEqual("anual_M51.xlsx", payload["modules"][0]["filename"])

        database = self.app.state.database
        for entry in payload["modules"]:
            upload = database.get_upload(entry["upload_id"])
            self.assertEqual(entry["module"], upload["module"])

    def test_one_workbook_per_module_is_used_without_rewriting(self) -> None:
        m51 = build_workbook(self.data_dir / "M51.xlsx", [offer_row("D51", 51)])
        m52 = build_workbook(self.data_dir / "M52.xlsx", [offer_row("D52", 52)])
        response = self.client.post(
            "/api/batches",
            files=[self._upload(m51), self._upload(m52)],
            data={"modules": "51,52"},
        )
        self.assertEqual(201, response.status_code, response.text)
        payload = response.json()
        # Planilha que já é de um módulo só conserva o nome original.
        self.assertEqual(
            ["M51.xlsx", "M52.xlsx"],
            [item["filename"] for item in payload["modules"]],
        )

    def test_create_and_read_return_the_same_shape(self) -> None:
        """Criar e consultar um lote precisam devolver a mesma forma.

        A tela usa a resposta da criação para desenhar o passo seguinte. Quando
        `POST` devolvia um dicionário parecido, mas sem `status` e `totals`, o
        primeiro render depois da validação quebrava com "Cannot read
        properties of undefined" e a página inteira sumia — o tipo do cliente
        dizia `ModuleBatch`, e os campos não estavam lá.
        """
        anual = build_workbook(
            self.data_dir / "anual.xlsx",
            [offer_row("D51", 51), offer_row("D52", 52)],
        )
        created = self.client.post(
            "/api/batches", files=[self._upload(anual)], data={"modules": "51,52"}
        )
        self.assertEqual(201, created.status_code, created.text)
        criado = created.json()
        lido = self.client.get(f"/api/batches/{criado['id']}").json()

        self.assertEqual(sorted(lido), sorted(criado))
        self.assertEqual(lido, criado)
        # Os campos que a tela lê logo de cara precisam existir na criação.
        for campo in ("status", "totals", "modules"):
            self.assertIn(campo, criado)
        for campo in ("offers", "allocated", "coverage_pct", "modules", "runnable",
                      "queued_or_running", "concluded"):
            self.assertIn(campo, criado["totals"])
        for entrada in criado["modules"]:
            self.assertEqual(
                sorted(entrada),
                sorted({"module", "upload_id", "filename", "validation_status",
                        "runnable", "reason", "validation", "job", "kpis"}),
            )

        # A listagem também: é a mesma forma em todo lugar.
        listado = self.client.get("/api/batches").json()[0]
        self.assertEqual(sorted(criado), sorted(listado))

    def test_batch_refuses_ambiguous_or_missing_modules(self) -> None:
        primeira = build_workbook(self.data_dir / "a.xlsx", [offer_row("A", 52)])
        segunda = build_workbook(self.data_dir / "b.xlsx", [offer_row("B", 52, "21:00")])
        ambiguous = self.client.post(
            "/api/batches",
            files=[self._upload(primeira), self._upload(segunda)],
            data={"modules": "52"},
        )
        self.assertEqual(422, ambiguous.status_code)
        self.assertIn("Mais de uma planilha", ambiguous.json()["detail"])

        missing = self.client.post(
            "/api/batches",
            files=[self._upload(primeira)],
            data={"modules": "53"},
        )
        self.assertEqual(422, missing.status_code)
        self.assertIn("Nenhuma planilha", missing.json()["detail"])

        unsupported = self.client.post(
            "/api/batches",
            files=[self._upload(primeira)],
            data={"modules": "60"},
        )
        self.assertEqual(422, unsupported.status_code)
        self.assertIn("51 a 54", unsupported.json()["detail"])

    def test_warnings_are_confirmed_after_reading_them_not_before(self) -> None:
        """Mesmo fluxo da rodada única: validar, ler as ressalvas, confirmar.

        A confirmação é reavaliada na execução, e não congelada na criação do
        lote; sem isso o operador teria de aceitar ressalvas que ainda não viu.
        """
        anual = build_workbook(
            self.data_dir / "anual.xlsx", [offer_row_com_ressalva("D52", 52)]
        )
        created = self.client.post(
            "/api/batches", files=[self._upload(anual)], data={"modules": "52"}
        )
        self.assertEqual(201, created.status_code, created.text)
        payload = created.json()
        entry = payload["modules"][0]
        self.assertEqual("APROVADO_COM_RESSALVAS", entry["validation_status"])
        self.assertFalse(entry["runnable"])
        self.assertIn("ressalvas", entry["reason"])
        # A tela precisa das ocorrências para o operador decidir.
        self.assertTrue(entry["validation"]["issue_groups"] > 0)
        self.assertEqual(0, entry["validation"]["blocking_issue_groups"])

        blocked = self.client.post(f"/api/batches/{payload['id']}/runs")
        self.assertEqual(409, blocked.status_code)
        self.assertIn("confirme as ressalvas", blocked.json()["detail"].lower())

        manager = self.app.state.job_manager
        pending: Future = Future()
        with patch.object(manager.executor, "submit", return_value=pending):
            released = self.client.post(
                f"/api/batches/{payload['id']}/runs", json={"confirm_warnings": True}
            )
        self.assertEqual(202, released.status_code, released.text)
        self.assertEqual(1, released.json()["totals"]["queued_or_running"])
        pending.cancel()

    def test_run_enqueues_one_job_per_module_and_reports_progress(self) -> None:
        anual = build_workbook(
            self.data_dir / "anual.xlsx",
            [offer_row("D51", 51), offer_row("D52", 52)],
        )
        created = self.client.post(
            "/api/batches",
            files=[self._upload(anual)],
            data={"modules": "51,52"},
        )
        self.assertEqual(201, created.status_code, created.text)
        batch_id = created.json()["id"]

        manager = self.app.state.job_manager
        pending: Future = Future()
        with patch.object(manager.executor, "submit", return_value=pending):
            started = self.client.post(
                f"/api/batches/{batch_id}/runs", json={"confirm_warnings": True}
            )
        self.assertEqual(202, started.status_code, started.text)
        payload = started.json()
        self.assertEqual("EXECUTANDO", payload["status"])
        self.assertEqual(2, payload["totals"]["queued_or_running"])
        jobs = [item["job"] for item in payload["modules"]]
        self.assertEqual([51, 52], [job["module"] for job in jobs])
        self.assertTrue(all(job["batch_id"] == batch_id for job in jobs))
        self.assertTrue(all(job["status"] == "QUEUED" for job in jobs))

        listed = self.client.get("/api/batches").json()
        self.assertEqual([batch_id], [item["id"] for item in listed])

        # Reexecutar não pode duplicar rodadas já enfileiradas.
        with patch.object(manager.executor, "submit", return_value=pending):
            again = self.client.post(
                f"/api/batches/{batch_id}/runs", json={"confirm_warnings": True}
            )
        self.assertEqual(409, again.status_code)
        pending.cancel()

    def test_batch_stays_running_while_the_engine_reports_its_own_states(self) -> None:
        """Uma rodada em RESOLVENDO não pode encerrar o lote como PARCIAL.

        O motor publica estados próprios (VALIDANDO, RESOLVENDO, AUDITANDO) que
        substituem QUEUED/RUNNING no job. Ler apenas esses dois nomes fazia o
        painel declarar o lote terminado enquanto um módulo ainda rodava.
        """
        anual = build_workbook(
            self.data_dir / "anual.xlsx",
            [offer_row("D51", 51), offer_row("D52", 52)],
        )
        created = self.client.post(
            "/api/batches",
            files=[self._upload(anual)],
            data={"modules": "51,52"},
        )
        batch_id = created.json()["id"]
        manager = self.app.state.job_manager
        pending: Future = Future()
        with patch.object(manager.executor, "submit", return_value=pending):
            self.client.post(f"/api/batches/{batch_id}/runs", json={"confirm_warnings": True})

        database = self.app.state.database
        jobs = database.jobs_for_batch(batch_id)
        # O primeiro módulo termina; o segundo entra em RESOLVENDO no motor.
        database.update_job(jobs[0]["id"], status="CONCLUIDA", message="ok")
        round_dir = self.data_dir / "rodada_em_curso"
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "status.json").write_text(
            json.dumps({"state": "RESOLVENDO", "message": "Executando CP-SAT.", "history": []}),
            encoding="utf-8",
        )
        database.update_job(jobs[1]["id"], round_name="rodada_001", round_dir=str(round_dir))

        payload = self.client.get(f"/api/batches/{batch_id}").json()
        self.assertEqual("RESOLVENDO", payload["modules"][1]["job"]["status"])
        self.assertEqual("EXECUTANDO", payload["status"])
        self.assertEqual(1, payload["totals"]["queued_or_running"])
        pending.cancel()



class BatchDeletionTests(unittest.TestCase):
    """Exclusao de um lote do historico.

    O lote e a unica porta para apagar rodadas em bloco, e a cascata alcanca
    cenarios construidos sobre elas. Um engano aqui destroi trabalho que o
    operador nao consegue refazer, entao cada caminho tem teste proprio.
    """

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
        import shutil

        self.client_context.__exit__(None, None, None)
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def _upload(self, path: Path) -> tuple:
        return (
            "files",
            (
                path.name,
                path.read_bytes(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        )

    def _criar_lote(self, modulos: str = "51,52") -> dict:
        anual = build_workbook(
            self.data_dir / "anual.xlsx",
            [offer_row("D51", 51), offer_row("D52", 52)],
        )
        resposta = self.client.post(
            "/api/batches",
            files=[self._upload(anual)],
            data={"modules": modulos, "name": "Lote de teste"},
        )
        self.assertEqual(201, resposta.status_code, resposta.text)
        return resposta.json()

    def _registrar_job(self, batch_id: str, upload_id: str, status: str = "CONCLUIDA") -> str:
        job_id = uuid.uuid4().hex
        agora = "2026-01-01T00:00:00+00:00"
        self.database.create_job({
            "id": job_id,
            "upload_id": upload_id,
            "status": status,
            "message": "",
            "module": 51,
            "require_optimal": True,
            "batch_id": batch_id,
            "created_at": agora,
            "updated_at": agora,
        })
        return job_id

    def test_lote_sem_rodada_sai_do_historico_com_os_uploads_dele(self) -> None:
        lote = self._criar_lote()
        upload_ids = [item["upload_id"] for item in lote["modules"]]
        self.assertTrue(all(upload_ids))

        resposta = self.client.delete(f"/api/batches/{lote['id']}")

        self.assertEqual(200, resposta.status_code, resposta.text)
        corpo = resposta.json()
        self.assertEqual(lote["id"], corpo["batch_id"])
        self.assertEqual(0, corpo["deleted_rounds"])
        self.assertIsNone(self.database.get_batch(lote["id"]))
        # Um lote que nunca rodou ainda assim criou uploads na validacao.
        for upload_id in upload_ids:
            self.assertIsNone(self.database.get_upload(upload_id))

    def test_exclusao_leva_junto_rodadas_e_cenarios_do_lote(self) -> None:
        lote = self._criar_lote()
        upload_id = lote["modules"][0]["upload_id"]
        job_id = self._registrar_job(lote["id"], upload_id)
        cenario_id = uuid.uuid4().hex
        agora = "2026-01-01T00:00:00+00:00"
        self.database.create_scenario({
            "id": cenario_id,
            "baseline_job_id": job_id,
            "name": "Cenario sobre a rodada do lote",
            "status": "RASCUNHO",
            "created_at": agora,
            "updated_at": agora,
        })

        resposta = self.client.delete(f"/api/batches/{lote['id']}")

        self.assertEqual(200, resposta.status_code, resposta.text)
        corpo = resposta.json()
        self.assertEqual(1, corpo["deleted_rounds"])
        self.assertEqual(1, corpo["deleted_scenarios"])
        self.assertIsNone(self.database.get_job(job_id))
        self.assertIsNone(self.database.get_scenario(cenario_id))

    def test_lote_com_modulo_na_fila_nao_pode_ser_excluido(self) -> None:
        lote = self._criar_lote()
        upload_id = lote["modules"][0]["upload_id"]
        job_id = self._registrar_job(lote["id"], upload_id, status="RUNNING")

        resposta = self.client.delete(f"/api/batches/{lote['id']}")

        self.assertEqual(409, resposta.status_code, resposta.text)
        # Nada pode ter sido removido antes da recusa.
        self.assertIsNotNone(self.database.get_batch(lote["id"]))
        self.assertIsNotNone(self.database.get_job(job_id))

    def test_lote_inexistente_devolve_404(self) -> None:
        resposta = self.client.delete(f"/api/batches/{uuid.uuid4().hex}")
        self.assertEqual(404, resposta.status_code)

    def test_upload_usado_por_outra_rodada_sobrevive_a_exclusao(self) -> None:
        lote = self._criar_lote()
        upload_id = lote["modules"][0]["upload_id"]
        # Uma rodada avulsa, fora do lote, compartilha o mesmo upload.
        avulso = uuid.uuid4().hex
        agora = "2026-01-01T00:00:00+00:00"
        self.database.create_job({
            "id": avulso,
            "upload_id": upload_id,
            "status": "CONCLUIDA",
            "message": "",
            "module": 51,
            "require_optimal": True,
            "created_at": agora,
            "updated_at": agora,
        })

        resposta = self.client.delete(f"/api/batches/{lote['id']}")

        self.assertEqual(200, resposta.status_code, resposta.text)
        # O upload continua porque outra rodada ainda depende dele.
        self.assertIsNotNone(self.database.get_upload(upload_id))
        self.assertIsNotNone(self.database.get_job(avulso))

    def test_simulacao_nao_altera_o_banco(self) -> None:
        lote = self._criar_lote()
        upload_id = lote["modules"][0]["upload_id"]
        job_id = self._registrar_job(lote["id"], upload_id)

        plano = self.database.delete_batch(lote["id"], dry_run=True)

        self.assertEqual([lote["id"]], plano["batch_ids"])
        self.assertIn(job_id, plano["primary_job_ids"])
        # dry_run so descreve o que aconteceria.
        self.assertIsNotNone(self.database.get_batch(lote["id"]))
        self.assertIsNotNone(self.database.get_job(job_id))

    def test_plano_simulado_e_o_mesmo_que_a_exclusao_executa(self) -> None:
        lote = self._criar_lote()
        self._registrar_job(lote["id"], lote["modules"][0]["upload_id"])

        plano = self.database.delete_batch(lote["id"], dry_run=True)
        executado = self.database.delete_batch(lote["id"])

        # O servico compara os dois para abortar se o estado mudar no meio.
        for chave in ("batch_ids", "scenario_ids", "job_ids", "primary_job_ids", "upload_ids"):
            self.assertEqual(plano[chave], executado[chave], chave)


if __name__ == "__main__":
    unittest.main()
