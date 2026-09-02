from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    @contextmanager
    def session(self):
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.session() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS uploads (
                    id TEXT PRIMARY KEY,
                    original_name TEXT NOT NULL,
                    stored_path TEXT NOT NULL,
                    module INTEGER NOT NULL,
                    validation_status TEXT NOT NULL,
                    validation_path TEXT NOT NULL,
                    validation_csv_path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    upload_id TEXT NOT NULL REFERENCES uploads(id),
                    status TEXT NOT NULL,
                    message TEXT NOT NULL,
                    module INTEGER NOT NULL,
                    require_optimal INTEGER NOT NULL,
                    time_limit_seconds REAL,
                    round_name TEXT,
                    round_dir TEXT,
                    process_id INTEGER,
                    exit_code INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_jobs_created_at
                    ON jobs(created_at DESC);

                CREATE TABLE IF NOT EXISTS scenarios (
                    id TEXT PRIMARY KEY,
                    baseline_job_id TEXT NOT NULL REFERENCES jobs(id),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    promoted_at TEXT
                );

                CREATE TABLE IF NOT EXISTS scenario_changes (
                    id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
                    change_type TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    row_number INTEGER NOT NULL,
                    field_name TEXT NOT NULL,
                    old_value_json TEXT NOT NULL,
                    new_value_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(scenario_id, entity_type, row_number, field_name)
                );

                CREATE TABLE IF NOT EXISTS scenario_runs (
                    scenario_id TEXT NOT NULL REFERENCES scenarios(id),
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    input_path TEXT NOT NULL,
                    changes_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (scenario_id, job_id)
                );

                CREATE TABLE IF NOT EXISTS scenario_policies (
                    id TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
                    policy_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_value TEXT NOT NULL,
                    configuration_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(scenario_id, policy_type, target_type, target_value)
                );

                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    criterion TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    margin_offers INTEGER,
                    require_optimal INTEGER NOT NULL,
                    time_limit_seconds REAL,
                    modules_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_batches_created_at
                    ON batches(created_at DESC);

                -- Um estudo aplica a mesma pergunta a vários módulos do ano.
                -- Ele não guarda linha de planilha: guarda a premissa por
                -- chave de negócio (chapa, curso, disciplina) e projeta essa
                -- premissa em um cenário filho por módulo na hora de simular.
                -- É o que permite "demitir a partir do módulo 51" continuar
                -- significando a mesma pessoa quando a planilha anual é
                -- fatiada e as linhas do MAPA PEDAGÓGICO mudam de lugar.
                CREATE TABLE IF NOT EXISTS scenario_studies (
                    id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL REFERENCES batches(id),
                    name TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    modules_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_scenario_studies_created_at
                    ON scenario_studies(created_at DESC);

                CREATE TABLE IF NOT EXISTS scenario_study_premises (
                    id TEXT PRIMARY KEY,
                    study_id TEXT NOT NULL
                        REFERENCES scenario_studies(id) ON DELETE CASCADE,
                    premise_type TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_value TEXT NOT NULL,
                    target_label TEXT NOT NULL DEFAULT '',
                    field_name TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(study_id, premise_type, target_type, target_value, field_name)
                );

                -- O cenário filho é apagado junto com o módulo do estudo, e o
                -- módulo do estudo é apagado junto com o cenário filho: as duas
                -- direções existem porque tanto o reset de cenários quanto a
                -- exclusão de um lote já removem linhas de `scenarios`.
                CREATE TABLE IF NOT EXISTS scenario_study_modules (
                    study_id TEXT NOT NULL
                        REFERENCES scenario_studies(id) ON DELETE CASCADE,
                    module INTEGER NOT NULL,
                    baseline_job_id TEXT NOT NULL
                        REFERENCES jobs(id) ON DELETE CASCADE,
                    scenario_id TEXT REFERENCES scenarios(id) ON DELETE CASCADE,
                    PRIMARY KEY (study_id, module)
                );

                CREATE TABLE IF NOT EXISTS official_results (
                    module INTEGER PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    scenario_id TEXT REFERENCES scenarios(id),
                    selected_at TEXT NOT NULL
                );
                """
            )
            job_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(jobs)")
            }
            if "kind" not in job_columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN kind TEXT NOT NULL DEFAULT 'PRIMARY'"
                )
            if "scenario_id" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN scenario_id TEXT")
            # Bases anteriores à 2.0 não escolhiam critério: elas permanecem
            # válidas e assumem o comportamento histórico de perfil exato.
            if "criterion" not in job_columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN criterion TEXT NOT NULL "
                    "DEFAULT 'PERFIL_EXATO'"
                )
            # Rodadas anteriores a 2.0 sempre exigiram prova completa.
            if "profile" not in job_columns:
                connection.execute(
                    "ALTER TABLE jobs ADD COLUMN profile TEXT NOT NULL "
                    "DEFAULT 'PROVA_COMPLETA'"
                )
            if "margin_offers" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN margin_offers INTEGER")
            # Rodadas anteriores ao processamento em lote não pertencem a lote
            # algum; a coluna nula preserva exatamente esse significado.
            if "batch_id" not in job_columns:
                connection.execute("ALTER TABLE jobs ADD COLUMN batch_id TEXT")
            scenario_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(scenarios)")
            }
            # Cenários anteriores ao estudo em lote são avulsos, e a coluna nula
            # preserva exatamente esse significado.
            if "study_id" not in scenario_columns:
                connection.execute("ALTER TABLE scenarios ADD COLUMN study_id TEXT")
            upload_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(uploads)")
            }
            if "criterion" not in upload_columns:
                connection.execute(
                    "ALTER TABLE uploads ADD COLUMN criterion TEXT NOT NULL "
                    "DEFAULT 'PERFIL_EXATO'"
                )
            if "profile" not in upload_columns:
                connection.execute(
                    "ALTER TABLE uploads ADD COLUMN profile TEXT NOT NULL "
                    "DEFAULT 'PROVA_COMPLETA'"
                )
            if "margin_offers" not in upload_columns:
                connection.execute("ALTER TABLE uploads ADD COLUMN margin_offers INTEGER")

    def recover_incomplete_jobs(self) -> None:
        now = utc_now()
        with self.session() as connection:
            connection.execute(
                """
                UPDATE jobs
                   SET status = 'INTERROMPIDA',
                       message = 'O servidor foi reiniciado durante esta execução.',
                       updated_at = ?
                 WHERE status IN ('QUEUED', 'RUNNING')
                """,
                (now,),
            )
            connection.execute(
                """
                UPDATE scenarios
                   SET status = 'FALHA', updated_at = ?
                 WHERE status = 'EXECUTANDO'
                """,
                (now,),
            )
            connection.execute(
                """
                UPDATE scenario_studies
                   SET status = 'FALHA', updated_at = ?
                 WHERE status = 'EXECUTANDO'
                """,
                (now,),
            )

    def create_upload(self, payload: dict[str, Any]) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO uploads (
                    id, original_name, stored_path, module, validation_status,
                    validation_path, validation_csv_path, criterion,
                    profile, margin_offers, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["original_name"],
                    payload["stored_path"],
                    payload["module"],
                    payload["validation_status"],
                    payload["validation_path"],
                    payload["validation_csv_path"],
                    payload.get("criterion", "PERFIL_EXATO"),
                    payload.get("profile", "PROVA_COMPLETA"),
                    payload.get("margin_offers"),
                    payload["created_at"],
                ),
            )

    def get_upload(self, upload_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM uploads WHERE id = ?", (upload_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_uploads_with_job_count(self) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT uploads.*, COUNT(jobs.id) AS job_count
                  FROM uploads
             LEFT JOIN jobs ON jobs.upload_id = uploads.id
              GROUP BY uploads.id
              ORDER BY uploads.created_at
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_upload_if_unused(self, upload_id: str) -> bool:
        with self.session() as connection:
            cursor = connection.execute(
                """
                DELETE FROM uploads
                 WHERE id = ?
                   AND NOT EXISTS (
                       SELECT 1 FROM jobs WHERE jobs.upload_id = uploads.id
                   )
                """,
                (upload_id,),
            )
        return cursor.rowcount > 0

    def count_inflight_jobs(self, kind: str) -> int:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                  FROM jobs
                 WHERE kind = ? AND status IN ('QUEUED', 'RUNNING')
                """,
                (kind,),
            ).fetchone()
        return int(row["total"] if row else 0)

    def create_job(self, payload: dict[str, Any]) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO jobs (
                    id, upload_id, status, message, module, require_optimal,
                    time_limit_seconds, kind, scenario_id, criterion,
                    profile, margin_offers, batch_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["upload_id"],
                    payload["status"],
                    payload["message"],
                    payload["module"],
                    int(payload["require_optimal"]),
                    payload.get("time_limit_seconds"),
                    payload.get("kind", "PRIMARY"),
                    payload.get("scenario_id"),
                    payload.get("criterion", "PERFIL_EXATO"),
                    payload.get("profile", "PROVA_COMPLETA"),
                    payload.get("margin_offers"),
                    payload.get("batch_id"),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )

    def create_batch(self, payload: dict[str, Any]) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO batches (
                    id, name, criterion, profile, margin_offers,
                    require_optimal, time_limit_seconds, modules_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["name"],
                    payload.get("criterion", "PERFIL_EXATO"),
                    payload.get("profile", "PROVA_COMPLETA"),
                    payload.get("margin_offers"),
                    int(payload.get("require_optimal", True)),
                    payload.get("time_limit_seconds"),
                    json.dumps(payload["modules_json"], ensure_ascii=False),
                    payload["created_at"],
                ),
            )

    def get_batch(self, batch_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
        if not row:
            return None
        batch = dict(row)
        batch["modules"] = json.loads(batch.pop("modules_json"))
        return batch

    def list_batches(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM batches ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        batches = []
        for row in rows:
            batch = dict(row)
            batch["modules"] = json.loads(batch.pop("modules_json"))
            batches.append(batch)
        return batches

    def jobs_for_batch(self, batch_id: str) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT jobs.*, uploads.original_name, uploads.stored_path,
                       uploads.validation_status, uploads.validation_path,
                       uploads.validation_csv_path,
                       EXISTS(
                           SELECT 1 FROM official_results
                            WHERE official_results.job_id = jobs.id
                       ) AS is_official
                  FROM jobs
                  JOIN uploads ON uploads.id = jobs.upload_id
                 WHERE jobs.batch_id = ?
                 ORDER BY jobs.module
                """,
                (batch_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_job(self, job_id: str, **changes: Any) -> None:
        if not changes:
            return
        changes["updated_at"] = utc_now()
        columns = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [job_id]
        with self.session() as connection:
            connection.execute(
                f"UPDATE jobs SET {columns} WHERE id = ?",  # noqa: S608
                values,
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT jobs.*, uploads.original_name, uploads.stored_path,
                       uploads.validation_status, uploads.validation_path,
                       uploads.validation_csv_path,
                       EXISTS(
                           SELECT 1 FROM official_results
                            WHERE official_results.job_id = jobs.id
                       ) AS is_official
                  FROM jobs
                  JOIN uploads ON uploads.id = jobs.upload_id
                 WHERE jobs.id = ?
                """,
                (job_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_jobs(
        self,
        limit: int = 100,
        kind: str | None = "PRIMARY",
    ) -> list[dict[str, Any]]:
        with self.session() as connection:
            where = "WHERE jobs.kind = ?" if kind else ""
            parameters: tuple[Any, ...] = (kind, limit) if kind else (limit,)
            rows = connection.execute(
                f"""
                SELECT jobs.*, uploads.original_name, uploads.validation_status,
                       EXISTS(
                           SELECT 1 FROM official_results
                            WHERE official_results.job_id = jobs.id
                       ) AS is_official
                  FROM jobs
                  JOIN uploads ON uploads.id = jobs.upload_id
                 {where}
                 ORDER BY jobs.created_at DESC
                 LIMIT ?
                """,  # noqa: S608 - fragmento SQL interno e controlado
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def create_scenario(self, payload: dict[str, Any]) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO scenarios (
                    id, baseline_job_id, name, description, status,
                    study_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["baseline_job_id"],
                    payload["name"],
                    payload.get("description", ""),
                    payload["status"],
                    payload.get("study_id"),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )

    def update_scenario(self, scenario_id: str, **changes: Any) -> None:
        if not changes:
            return
        changes["updated_at"] = utc_now()
        columns = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [scenario_id]
        with self.session() as connection:
            connection.execute(
                f"UPDATE scenarios SET {columns} WHERE id = ?",  # noqa: S608
                values,
            )

    def get_scenario(self, scenario_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT scenarios.*,
                       jobs.module,
                       jobs.upload_id,
                       jobs.criterion AS criterion,
                       jobs.profile AS profile,
                       jobs.margin_offers AS margin_offers,
                       jobs.round_name AS baseline_round,
                       uploads.original_name AS baseline_filename,
                       official_results.job_id AS official_job_id
                  FROM scenarios
                  JOIN jobs ON jobs.id = scenarios.baseline_job_id
                  JOIN uploads ON uploads.id = jobs.upload_id
             LEFT JOIN official_results
                    ON official_results.scenario_id = scenarios.id
                 WHERE scenarios.id = ?
                """,
                (scenario_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_scenarios(
        self,
        limit: int = 100,
        *,
        include_study_children: bool = False,
    ) -> list[dict[str, Any]]:
        """Cenários avulsos, na ordem em que foram criados.

        Os filhos de um estudo ficam de fora por padrão: eles são detalhe de um
        estudo, e listá-los junto encheria o seletor da tela com quatro entradas
        por pergunta feita.
        """
        scope = "" if include_study_children else "WHERE scenarios.study_id IS NULL"
        with self.session() as connection:
            rows = connection.execute(
                f"""
                SELECT scenarios.*,
                       jobs.module,
                       jobs.criterion AS criterion,
                       jobs.profile AS profile,
                       jobs.margin_offers AS margin_offers,
                       jobs.round_name AS baseline_round,
                       uploads.original_name AS baseline_filename,
                       official_results.job_id AS official_job_id,
                       (
                           SELECT scenario_runs.job_id
                             FROM scenario_runs
                            WHERE scenario_runs.scenario_id = scenarios.id
                            ORDER BY scenario_runs.created_at DESC
                            LIMIT 1
                       ) AS latest_job_id
                  FROM scenarios
                  JOIN jobs ON jobs.id = scenarios.baseline_job_id
                  JOIN uploads ON uploads.id = jobs.upload_id
             LEFT JOIN official_results
                    ON official_results.scenario_id = scenarios.id
                 {scope}
              ORDER BY scenarios.created_at DESC
                 LIMIT ?
                """,  # noqa: S608 - fragmento SQL interno e controlado
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_scenario_change(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO scenario_changes (
                    id, scenario_id, change_type, entity_type, row_number,
                    field_name, old_value_json, new_value_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id, entity_type, row_number, field_name)
                DO UPDATE SET
                    change_type = excluded.change_type,
                    new_value_json = excluded.new_value_json,
                    created_at = excluded.created_at
                """,
                (
                    payload["id"],
                    payload["scenario_id"],
                    payload["change_type"],
                    payload["entity_type"],
                    payload["row_number"],
                    payload["field_name"],
                    payload["old_value_json"],
                    payload["new_value_json"],
                    payload["created_at"],
                ),
            )
            now = utc_now()
            connection.execute(
                "UPDATE scenarios SET status = 'RASCUNHO', updated_at = ? WHERE id = ?",
                (now, payload["scenario_id"]),
            )
            row = connection.execute(
                """
                SELECT * FROM scenario_changes
                 WHERE scenario_id = ? AND entity_type = ?
                   AND row_number = ? AND field_name = ?
                """,
                (
                    payload["scenario_id"], payload["entity_type"],
                    payload["row_number"], payload["field_name"],
                ),
            ).fetchone()
        if not row:
            raise RuntimeError("A alteração do cenário não foi persistida.")
        return dict(row)

    def list_scenario_changes(self, scenario_id: str) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scenario_changes
                 WHERE scenario_id = ?
              ORDER BY created_at, row_number, field_name
                """,
                (scenario_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def clear_scenario_changes(self, scenario_id: str) -> int:
        """Esvazia as alterações de um cenário sem tocar no cenário em si.

        A projeção de um estudo reescreve as premissas do zero a cada edição,
        para que apagar uma premissa no estudo apague exatamente o que ela havia
        produzido em cada módulo, sem precisar rastrear a origem célula a célula.
        """
        with self.session() as connection:
            cursor = connection.execute(
                "DELETE FROM scenario_changes WHERE scenario_id = ?", (scenario_id,)
            )
        return cursor.rowcount

    def delete_scenario_change(self, scenario_id: str, change_id: str) -> bool:
        with self.session() as connection:
            cursor = connection.execute(
                "DELETE FROM scenario_changes WHERE scenario_id = ? AND id = ?",
                (scenario_id, change_id),
            )
            if cursor.rowcount > 0:
                connection.execute(
                    "UPDATE scenarios SET status = 'RASCUNHO', updated_at = ? WHERE id = ?",
                    (utc_now(), scenario_id),
                )
        return cursor.rowcount > 0

    def upsert_scenario_policy(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO scenario_policies (
                    id, scenario_id, policy_type, target_type, target_value,
                    configuration_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scenario_id, policy_type, target_type, target_value)
                DO UPDATE SET
                    configuration_json = excluded.configuration_json,
                    created_at = excluded.created_at
                """,
                (
                    payload["id"], payload["scenario_id"], payload["policy_type"],
                    payload["target_type"], payload["target_value"],
                    payload["configuration_json"], payload["created_at"],
                ),
            )
            now = utc_now()
            connection.execute(
                "UPDATE scenarios SET status = 'RASCUNHO', updated_at = ? WHERE id = ?",
                (now, payload["scenario_id"]),
            )
            row = connection.execute(
                """
                SELECT * FROM scenario_policies
                 WHERE scenario_id = ? AND policy_type = ?
                   AND target_type = ? AND target_value = ?
                """,
                (
                    payload["scenario_id"], payload["policy_type"],
                    payload["target_type"], payload["target_value"],
                ),
            ).fetchone()
        if not row:
            raise RuntimeError("A política do cenário não foi persistida.")
        return dict(row)

    def list_scenario_policies(self, scenario_id: str) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scenario_policies
                 WHERE scenario_id = ?
              ORDER BY created_at, policy_type, target_value
                """,
                (scenario_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_scenario_policy(self, scenario_id: str, policy_id: str) -> bool:
        with self.session() as connection:
            cursor = connection.execute(
                "DELETE FROM scenario_policies WHERE scenario_id = ? AND id = ?",
                (scenario_id, policy_id),
            )
            if cursor.rowcount > 0:
                connection.execute(
                    "UPDATE scenarios SET status = 'RASCUNHO', updated_at = ? WHERE id = ?",
                    (utc_now(), scenario_id),
                )
        return cursor.rowcount > 0

    def create_scenario_run(self, payload: dict[str, Any]) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO scenario_runs (
                    scenario_id, job_id, input_path, changes_path, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payload["scenario_id"],
                    payload["job_id"],
                    payload["input_path"],
                    payload["changes_path"],
                    payload["created_at"],
                ),
            )

    def latest_scenario_job(self, scenario_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT jobs.*, uploads.original_name, uploads.stored_path,
                       uploads.validation_status, uploads.validation_path,
                       uploads.validation_csv_path,
                       EXISTS(
                           SELECT 1 FROM official_results
                            WHERE official_results.job_id = jobs.id
                       ) AS is_official
                  FROM scenario_runs
                  JOIN jobs ON jobs.id = scenario_runs.job_id
                  JOIN uploads ON uploads.id = jobs.upload_id
                 WHERE scenario_runs.scenario_id = ?
              ORDER BY scenario_runs.created_at DESC
                 LIMIT 1
                """,
                (scenario_id,),
            ).fetchone()
        return dict(row) if row else None

    def promote_scenario(self, scenario_id: str, job_id: str, module: int) -> None:
        selected_at = utc_now()
        with self.session() as connection:
            previous = connection.execute(
                "SELECT scenario_id FROM official_results WHERE module = ?",
                (module,),
            ).fetchone()
            if previous and previous["scenario_id"] != scenario_id:
                connection.execute(
                    """
                    UPDATE scenarios
                       SET status = 'ARQUIVADO', updated_at = ?
                     WHERE id = ?
                    """,
                    (selected_at, previous["scenario_id"]),
                )
            connection.execute(
                """
                INSERT INTO official_results (module, job_id, scenario_id, selected_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(module) DO UPDATE SET
                    job_id = excluded.job_id,
                    scenario_id = excluded.scenario_id,
                    selected_at = excluded.selected_at
                """,
                (module, job_id, scenario_id, selected_at),
            )
            connection.execute(
                """
                UPDATE scenarios
                   SET status = 'HOMOLOGADO', promoted_at = ?, updated_at = ?
                 WHERE id = ?
                """,
                (selected_at, selected_at, scenario_id),
            )

    def official_job(self, module: int) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                """
                SELECT jobs.*, uploads.original_name, uploads.stored_path,
                       uploads.validation_status, uploads.validation_path,
                       uploads.validation_csv_path, 1 AS is_official
                  FROM official_results
                  JOIN jobs ON jobs.id = official_results.job_id
                  JOIN uploads ON uploads.id = jobs.upload_id
                 WHERE official_results.module = ?
                """,
                (module,),
            ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Estudos em lote
    # ------------------------------------------------------------------

    def create_study(self, payload: dict[str, Any]) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO scenario_studies (
                    id, batch_id, name, description, status,
                    modules_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload["batch_id"],
                    payload["name"],
                    payload.get("description", ""),
                    payload["status"],
                    json.dumps(payload["modules_json"], ensure_ascii=False),
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )

    def update_study(self, study_id: str, **changes: Any) -> None:
        if not changes:
            return
        changes["updated_at"] = utc_now()
        columns = ", ".join(f"{key} = ?" for key in changes)
        values = list(changes.values()) + [study_id]
        with self.session() as connection:
            connection.execute(
                f"UPDATE scenario_studies SET {columns} WHERE id = ?",  # noqa: S608
                values,
            )

    def _study_row(self, row: Any) -> dict[str, Any]:
        study = dict(row)
        study["modules"] = json.loads(study.pop("modules_json"))
        return study

    def get_study(self, study_id: str) -> dict[str, Any] | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT * FROM scenario_studies WHERE id = ?", (study_id,)
            ).fetchone()
        return self._study_row(row) if row else None

    def list_studies(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                "SELECT * FROM scenario_studies ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._study_row(row) for row in rows]

    def study_modules(self, study_id: str) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scenario_study_modules
                 WHERE study_id = ?
              ORDER BY module
                """,
                (study_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create_study_module(self, payload: dict[str, Any]) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO scenario_study_modules (
                    study_id, module, baseline_job_id, scenario_id
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    payload["study_id"],
                    payload["module"],
                    payload["baseline_job_id"],
                    payload.get("scenario_id"),
                ),
            )

    def upsert_study_premise(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO scenario_study_premises (
                    id, study_id, premise_type, target_type, target_value,
                    target_label, field_name, operation, value_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(study_id, premise_type, target_type, target_value, field_name)
                DO UPDATE SET
                    target_label = excluded.target_label,
                    operation = excluded.operation,
                    value_json = excluded.value_json,
                    created_at = excluded.created_at
                """,
                (
                    payload["id"],
                    payload["study_id"],
                    payload["premise_type"],
                    payload["target_type"],
                    payload["target_value"],
                    payload.get("target_label", ""),
                    payload["field_name"],
                    payload["operation"],
                    payload["value_json"],
                    payload["created_at"],
                ),
            )
            row = connection.execute(
                """
                SELECT * FROM scenario_study_premises
                 WHERE study_id = ?
                   AND premise_type = ?
                   AND target_type = ?
                   AND target_value = ?
                   AND field_name = ?
                """,
                (
                    payload["study_id"],
                    payload["premise_type"],
                    payload["target_type"],
                    payload["target_value"],
                    payload["field_name"],
                ),
            ).fetchone()
        return dict(row)

    def list_study_premises(self, study_id: str) -> list[dict[str, Any]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scenario_study_premises
                 WHERE study_id = ?
              ORDER BY created_at, id
                """,
                (study_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_study_premise(self, study_id: str, premise_id: str) -> bool:
        with self.session() as connection:
            cursor = connection.execute(
                "DELETE FROM scenario_study_premises WHERE study_id = ? AND id = ?",
                (study_id, premise_id),
            )
        return cursor.rowcount > 0

    def delete_study(self, study_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """Exclui um estudo junto com os cenários filhos que ele projetou.

        A cascata é a mesma do reset de cenários: um estudo não guarda resultado
        próprio, então o que precisa sair são as simulações de cada módulo.
        """
        with self.session() as connection:
            study = connection.execute(
                "SELECT id FROM scenario_studies WHERE id = ?", (study_id,)
            ).fetchone()
            if not study:
                raise ValueError("Estudo inexistente.")
            scenario_ids = [
                row["scenario_id"]
                for row in connection.execute(
                    """
                    SELECT scenario_id FROM scenario_study_modules
                     WHERE study_id = ? AND scenario_id IS NOT NULL
                    """,
                    (study_id,),
                ).fetchall()
            ]
            job_ids: list[str] = []
            round_dirs: list[str] = []
            if scenario_ids:
                placeholders = ",".join("?" for _ in scenario_ids)
                jobs = connection.execute(
                    f"SELECT id, round_dir FROM jobs WHERE scenario_id IN ({placeholders})",  # noqa: S608
                    scenario_ids,
                ).fetchall()
                job_ids = [row["id"] for row in jobs]
                round_dirs = [row["round_dir"] for row in jobs if row["round_dir"]]
                if job_ids:
                    job_placeholders = ",".join("?" for _ in job_ids)
                    running = connection.execute(
                        f"SELECT COUNT(*) AS total FROM jobs WHERE id IN ({job_placeholders}) AND status IN ('QUEUED', 'RUNNING')",  # noqa: S608
                        job_ids,
                    ).fetchone()["total"]
                    if running:
                        raise ValueError(
                            "Não é possível excluir o estudo enquanto houver "
                            "módulo na fila ou em execução."
                        )
            plan = {
                "study_ids": [study_id],
                "scenario_ids": scenario_ids,
                "job_ids": job_ids,
                "primary_job_ids": [],
                "round_dirs": round_dirs,
                "upload_dirs": [],
                "upload_ids": [],
            }
            if dry_run:
                return plan
            if scenario_ids:
                placeholders = ",".join("?" for _ in scenario_ids)
                connection.execute(
                    f"DELETE FROM official_results WHERE scenario_id IN ({placeholders})",  # noqa: S608
                    scenario_ids,
                )
                connection.execute(
                    f"DELETE FROM scenario_runs WHERE scenario_id IN ({placeholders})",  # noqa: S608
                    scenario_ids,
                )
            if job_ids:
                job_placeholders = ",".join("?" for _ in job_ids)
                connection.execute(
                    f"DELETE FROM jobs WHERE id IN ({job_placeholders})",  # noqa: S608
                    job_ids,
                )
            if scenario_ids:
                placeholders = ",".join("?" for _ in scenario_ids)
                connection.execute(
                    f"DELETE FROM scenarios WHERE id IN ({placeholders})",  # noqa: S608
                    scenario_ids,
                )
            connection.execute(
                "DELETE FROM scenario_studies WHERE id = ?", (study_id,)
            )
        return plan

    @staticmethod
    def _drop_empty_studies(connection: sqlite3.Connection) -> None:
        """Um estudo sem nenhum módulo restante não descreve mais nada.

        Acontece quando o reset de cenários ou a exclusão de um lote leva
        embora os cenários filhos: a casca ficaria no histórico prometendo uma
        comparação que não existe mais.
        """
        connection.execute(
            """
            DELETE FROM scenario_studies
             WHERE NOT EXISTS (
                 SELECT 1 FROM scenario_study_modules
                  WHERE scenario_study_modules.study_id = scenario_studies.id
             )
            """
        )

    def reset_scenarios(
        self,
        scope: str,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if scope not in {"latest", "all"}:
            raise ValueError("Escopo de limpeza inválido.")
        with self.session() as connection:
            if scope == "latest":
                # O último cenário pode ser o filho de um estudo. Levar só ele
                # deixaria o estudo respondendo à mesma pergunta com um módulo a
                # menos, sem nada na tela explicando o buraco: a unidade de
                # limpeza passa a ser o estudo inteiro.
                latest = connection.execute(
                    "SELECT id, study_id FROM scenarios ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if not latest:
                    scenario_ids = []
                elif latest["study_id"]:
                    scenario_ids = [
                        row["id"]
                        for row in connection.execute(
                            "SELECT id FROM scenarios WHERE study_id = ?",
                            (latest["study_id"],),
                        ).fetchall()
                    ]
                else:
                    scenario_ids = [latest["id"]]
            else:
                scenario_ids = [
                    row["id"]
                    for row in connection.execute(
                        "SELECT id FROM scenarios ORDER BY created_at DESC"
                    ).fetchall()
                ]
            if not scenario_ids:
                return {"scenario_ids": [], "job_ids": [], "primary_job_ids": [], "round_dirs": [], "upload_dirs": []}
            placeholders = ",".join("?" for _ in scenario_ids)
            running = connection.execute(
                f"SELECT COUNT(*) AS total FROM jobs WHERE scenario_id IN ({placeholders}) AND status IN ('QUEUED', 'RUNNING')",  # noqa: S608
                scenario_ids,
            ).fetchone()["total"]
            if running:
                raise ValueError("Não é possível zerar cenários enquanto houver simulação em andamento.")
            jobs = connection.execute(
                f"SELECT id, round_dir FROM jobs WHERE scenario_id IN ({placeholders})",  # noqa: S608
                scenario_ids,
            ).fetchall()
            job_ids = [row["id"] for row in jobs]
            plan = {
                "scenario_ids": scenario_ids,
                "job_ids": job_ids,
                "primary_job_ids": [],
                "round_dirs": [row["round_dir"] for row in jobs if row["round_dir"]],
                "upload_dirs": [],
                "upload_ids": [],
            }
            if dry_run:
                return plan
            connection.execute(
                f"DELETE FROM official_results WHERE scenario_id IN ({placeholders})",  # noqa: S608
                scenario_ids,
            )
            connection.execute(
                f"DELETE FROM scenario_runs WHERE scenario_id IN ({placeholders})",  # noqa: S608
                scenario_ids,
            )
            if job_ids:
                job_placeholders = ",".join("?" for _ in job_ids)
                connection.execute(
                    f"DELETE FROM jobs WHERE id IN ({job_placeholders})",  # noqa: S608
                    job_ids,
                )
            connection.execute(
                f"DELETE FROM scenarios WHERE id IN ({placeholders})",  # noqa: S608
                scenario_ids,
            )
            self._drop_empty_studies(connection)
        return plan

    def delete_batch(self, batch_id: str, *, dry_run: bool = False) -> dict[str, Any]:
        """Remove um lote do historico junto com o que ele produziu.

        Segue a mesma cascata do reset de rodadas-base: as rodadas do lote, os
        cenarios construidos sobre elas e os uploads que ficariam orfaos. Um
        lote que nunca chegou a executar nao tem rodada alguma, e ainda assim
        precisa liberar os uploads que a validacao criou.
        """
        with self.session() as connection:
            batch = connection.execute(
                "SELECT id, modules_json FROM batches WHERE id = ?", (batch_id,)
            ).fetchone()
            if not batch:
                raise ValueError("Lote inexistente.")
            batch_jobs = connection.execute(
                "SELECT id, upload_id, round_dir FROM jobs WHERE batch_id = ?", (batch_id,)
            ).fetchall()
            job_ids = [row["id"] for row in batch_jobs]
            scenario_ids: list[str] = []
            scenario_jobs: list[Any] = []
            if job_ids:
                job_placeholders = ",".join("?" for _ in job_ids)
                scenario_ids = [
                    row["id"]
                    for row in connection.execute(
                        f"SELECT id FROM scenarios WHERE baseline_job_id IN ({job_placeholders})",  # noqa: S608
                        job_ids,
                    ).fetchall()
                ]
                if scenario_ids:
                    scenario_placeholders = ",".join("?" for _ in scenario_ids)
                    scenario_jobs = connection.execute(
                        f"SELECT id, round_dir FROM jobs WHERE scenario_id IN ({scenario_placeholders})",  # noqa: S608
                        scenario_ids,
                    ).fetchall()
            all_job_ids = job_ids + [row["id"] for row in scenario_jobs]
            if all_job_ids:
                all_placeholders = ",".join("?" for _ in all_job_ids)
                running = connection.execute(
                    f"SELECT COUNT(*) AS total FROM jobs WHERE id IN ({all_placeholders}) AND status IN ('QUEUED', 'RUNNING')",  # noqa: S608
                    all_job_ids,
                ).fetchone()["total"]
                if running:
                    raise ValueError(
                        "Nao e possivel excluir o lote enquanto houver modulo na fila ou em execucao."
                    )
            # Uploads do lote: os das rodadas e tambem os que a validacao criou
            # para modulos que nunca rodaram.
            candidate_uploads = [row["upload_id"] for row in batch_jobs]
            for entry in json.loads(batch["modules_json"]):
                if entry.get("upload_id"):
                    candidate_uploads.append(str(entry["upload_id"]))
            upload_dirs: list[str] = []
            deleted_upload_ids: list[str] = []
            for upload_id in dict.fromkeys(candidate_uploads):
                if all_job_ids:
                    all_placeholders = ",".join("?" for _ in all_job_ids)
                    remaining = connection.execute(
                        f"SELECT COUNT(*) AS total FROM jobs WHERE upload_id = ? AND id NOT IN ({all_placeholders})",  # noqa: S608
                        [upload_id, *all_job_ids],
                    ).fetchone()["total"]
                else:
                    remaining = connection.execute(
                        "SELECT COUNT(*) AS total FROM jobs WHERE upload_id = ?", (upload_id,)
                    ).fetchone()["total"]
                if remaining:
                    continue
                upload = connection.execute(
                    "SELECT stored_path FROM uploads WHERE id = ?", (upload_id,)
                ).fetchone()
                if upload:
                    upload_dirs.append(str(Path(upload["stored_path"]).parent))
                    deleted_upload_ids.append(upload_id)
            study_ids = [
                row["id"]
                for row in connection.execute(
                    "SELECT id FROM scenario_studies WHERE batch_id = ?", (batch_id,)
                ).fetchall()
            ]
            plan = {
                "batch_ids": [batch_id],
                "study_ids": study_ids,
                "scenario_ids": scenario_ids,
                "job_ids": all_job_ids,
                "primary_job_ids": job_ids,
                "round_dirs": [
                    row["round_dir"]
                    for row in [*batch_jobs, *scenario_jobs]
                    if row["round_dir"]
                ],
                "upload_dirs": upload_dirs,
                "upload_ids": deleted_upload_ids,
            }
            if dry_run:
                return plan
            if all_job_ids:
                all_placeholders = ",".join("?" for _ in all_job_ids)
                connection.execute(
                    f"DELETE FROM official_results WHERE job_id IN ({all_placeholders})",  # noqa: S608
                    all_job_ids,
                )
            if scenario_ids:
                scenario_placeholders = ",".join("?" for _ in scenario_ids)
                connection.execute(
                    f"DELETE FROM official_results WHERE scenario_id IN ({scenario_placeholders})",  # noqa: S608
                    scenario_ids,
                )
                connection.execute(
                    f"DELETE FROM scenario_runs WHERE scenario_id IN ({scenario_placeholders})",  # noqa: S608
                    scenario_ids,
                )
                connection.execute(
                    f"DELETE FROM scenarios WHERE id IN ({scenario_placeholders})",  # noqa: S608
                    scenario_ids,
                )
            if all_job_ids:
                all_placeholders = ",".join("?" for _ in all_job_ids)
                connection.execute(
                    f"DELETE FROM jobs WHERE id IN ({all_placeholders})",  # noqa: S608
                    all_job_ids,
                )
            for upload_id in deleted_upload_ids:
                connection.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
            # Um estudo nasce colado num lote: sem o lote não há baseline por
            # módulo, e a chave estrangeira impediria a exclusão de qualquer
            # forma. Sai antes do lote, levando premissas e módulos na cascata.
            connection.execute(
                "DELETE FROM scenario_studies WHERE batch_id = ?", (batch_id,)
            )
            connection.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
        return plan

    def reset_primary_jobs(
        self,
        scope: str,
        *,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        if scope not in {"latest", "all"}:
            raise ValueError("Escopo de limpeza inválido.")
        with self.session() as connection:
            query = "SELECT id, upload_id, round_dir FROM jobs WHERE kind = 'PRIMARY' ORDER BY created_at DESC"
            if scope == "latest":
                query += " LIMIT 1"
            primary_jobs = connection.execute(query).fetchall()
            primary_ids = [row["id"] for row in primary_jobs]
            if not primary_ids:
                return {"scenario_ids": [], "job_ids": [], "primary_job_ids": [], "round_dirs": [], "upload_dirs": []}
            primary_placeholders = ",".join("?" for _ in primary_ids)
            scenarios = connection.execute(
                f"SELECT id FROM scenarios WHERE baseline_job_id IN ({primary_placeholders})",  # noqa: S608
                primary_ids,
            ).fetchall()
            scenario_ids = [row["id"] for row in scenarios]
            scenario_jobs = []
            if scenario_ids:
                scenario_placeholders = ",".join("?" for _ in scenario_ids)
                scenario_jobs = connection.execute(
                    f"SELECT id, round_dir FROM jobs WHERE scenario_id IN ({scenario_placeholders})",  # noqa: S608
                    scenario_ids,
                ).fetchall()
            all_job_ids = primary_ids + [row["id"] for row in scenario_jobs]
            all_job_placeholders = ",".join("?" for _ in all_job_ids)
            running = connection.execute(
                f"SELECT COUNT(*) AS total FROM jobs WHERE id IN ({all_job_placeholders}) AND status IN ('QUEUED', 'RUNNING')",  # noqa: S608
                all_job_ids,
            ).fetchone()["total"]
            if running:
                raise ValueError("Não é possível zerar rodadas enquanto houver execução vinculada em andamento.")
            upload_ids = list(dict.fromkeys(row["upload_id"] for row in primary_jobs))
            upload_dirs: list[str] = []
            deleted_upload_ids: list[str] = []
            for upload_id in upload_ids:
                remaining = connection.execute(
                    f"SELECT COUNT(*) AS total FROM jobs WHERE upload_id = ? AND id NOT IN ({all_job_placeholders})",  # noqa: S608
                    [upload_id, *all_job_ids],
                ).fetchone()["total"]
                if remaining:
                    continue
                upload = connection.execute(
                    "SELECT stored_path FROM uploads WHERE id = ?", (upload_id,),
                ).fetchone()
                if upload:
                    upload_dirs.append(str(Path(upload["stored_path"]).parent))
                    deleted_upload_ids.append(upload_id)
            plan = {
                "scenario_ids": scenario_ids,
                "job_ids": all_job_ids,
                "primary_job_ids": primary_ids,
                "round_dirs": [
                    row["round_dir"]
                    for row in [*primary_jobs, *scenario_jobs]
                    if row["round_dir"]
                ],
                "upload_dirs": upload_dirs,
                "upload_ids": deleted_upload_ids,
            }
            if dry_run:
                return plan
            connection.execute(
                f"DELETE FROM official_results WHERE job_id IN ({all_job_placeholders})",  # noqa: S608
                all_job_ids,
            )
            if scenario_ids:
                scenario_placeholders = ",".join("?" for _ in scenario_ids)
                connection.execute(
                    f"DELETE FROM official_results WHERE scenario_id IN ({scenario_placeholders})",  # noqa: S608
                    scenario_ids,
                )
                connection.execute(
                    f"DELETE FROM scenario_runs WHERE scenario_id IN ({scenario_placeholders})",  # noqa: S608
                    scenario_ids,
                )
                connection.execute(
                    f"DELETE FROM scenarios WHERE id IN ({scenario_placeholders})",  # noqa: S608
                    scenario_ids,
                )
            connection.execute(
                f"DELETE FROM jobs WHERE id IN ({all_job_placeholders})",  # noqa: S608
                all_job_ids,
            )
            for upload_id in deleted_upload_ids:
                connection.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
            self._drop_empty_studies(connection)
        return plan
