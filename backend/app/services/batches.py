"""Processamento de vários módulos em uma única operação.

O lote é orquestração, e não uma segunda regra de negócio: cada módulo vira
uma rodada independente, validada e resolvida pelo mesmo pipeline auditado.
Quando uma planilha traz mais de um módulo, ela é separada em uma planilha por
módulo *antes* da validação, de modo que o motor continua recebendo exatamente
o que sempre recebeu — uma base de um módulo só.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any, BinaryIO

from openpyxl import Workbook, load_workbook

from ..config import Settings
from ..database import Database, utc_now
from .jobs import load_summary, public_job
from .uploads import (
    UploadValidationError,
    safe_filename,
    save_upload_stream,
)


MAPA_SHEET = "MAPA PEDAGÓGICO"
DOCENTES_SHEET = "DOCENTES"
MODULE_COLUMN = "MÓD"
SUPPORTED_MODULES = (51, 52, 53, 54)


class BatchError(ValueError):
    pass


def _headers(worksheet: Any) -> dict[str, int]:
    """Mapa cabeçalho -> índice de coluna (base 1)."""
    return {
        str(cell.value or "").strip(): cell.column
        for cell in next(worksheet.iter_rows(min_row=1, max_row=1))
        if str(cell.value or "").strip()
    }


def _row_has_content(values: tuple[Any, ...]) -> bool:
    return any(value is not None and str(value).strip() for value in values)


def inspect_workbook(path: Path) -> dict[str, Any]:
    """Quais módulos existem no arquivo e quantas linhas cada um tem.

    Serve para a tela mostrar o conteúdo antes de o operador confirmar o lote,
    tanto no caso de uma planilha por módulo quanto no de uma planilha anual.
    """
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl levanta tipos variados
        raise BatchError(f"Não foi possível ler a planilha: {exc}") from exc
    try:
        missing = [
            sheet for sheet in (MAPA_SHEET, DOCENTES_SHEET)
            if sheet not in workbook.sheetnames
        ]
        if missing:
            raise BatchError(
                "Aba obrigatória ausente: " + ", ".join(missing)
            )
        worksheet = workbook[MAPA_SHEET]
        headers = _headers(worksheet)
        if MODULE_COLUMN not in headers:
            raise BatchError(
                f"A coluna {MODULE_COLUMN} não existe em {MAPA_SHEET}; "
                "sem ela não há como separar a planilha por módulo."
            )
        index = headers[MODULE_COLUMN] - 1
        counts: dict[int, int] = {}
        unreadable = 0
        for values in worksheet.iter_rows(min_row=2, values_only=True):
            if not _row_has_content(values):
                continue
            raw = values[index] if index < len(values) else None
            try:
                module = int(raw)
            except (TypeError, ValueError):
                unreadable += 1
                continue
            counts[module] = counts.get(module, 0) + 1
        return {
            "modules": [
                {
                    "module": module,
                    "rows": counts[module],
                    "supported": module in SUPPORTED_MODULES,
                }
                for module in sorted(counts)
            ],
            "rows_without_module": unreadable,
        }
    finally:
        workbook.close()


def split_workbook_by_module(source: Path, module: int, destination: Path) -> Path:
    """Gera uma planilha contendo somente as linhas do módulo pedido.

    DOCENTES é copiada inteira: o corpo docente não é dividido por módulo, e a
    capacidade é consumida dentro de cada módulo separadamente.
    """
    workbook = load_workbook(source, read_only=True, data_only=True)
    try:
        if MAPA_SHEET not in workbook.sheetnames or DOCENTES_SHEET not in workbook.sheetnames:
            raise BatchError("A planilha precisa das abas MAPA PEDAGÓGICO e DOCENTES.")
        mapa = workbook[MAPA_SHEET]
        headers = _headers(mapa)
        if MODULE_COLUMN not in headers:
            raise BatchError(f"A coluna {MODULE_COLUMN} não existe em {MAPA_SHEET}.")
        index = headers[MODULE_COLUMN] - 1

        output = Workbook()
        out_mapa = output.active
        out_mapa.title = MAPA_SHEET
        rows = mapa.iter_rows(min_row=1, values_only=True)
        out_mapa.append(next(rows))
        kept = 0
        for values in rows:
            if not _row_has_content(values):
                continue
            raw = values[index] if index < len(values) else None
            try:
                if int(raw) != module:
                    continue
            except (TypeError, ValueError):
                continue
            out_mapa.append(values)
            kept += 1
        if not kept:
            output.close()
            raise BatchError(f"A planilha não possui linhas do módulo {module}.")

        out_docentes = output.create_sheet(DOCENTES_SHEET)
        for values in workbook[DOCENTES_SHEET].iter_rows(min_row=1, values_only=True):
            out_docentes.append(values)

        destination.parent.mkdir(parents=True, exist_ok=True)
        output.save(destination)
        output.close()
        return destination
    finally:
        workbook.close()


def _prepare_module_file(
    source: Path,
    module: int,
    present_modules: list[int],
    workdir: Path,
) -> Path:
    """Devolve o arquivo que representa esse módulo.

    Uma planilha que já contém só o módulo pedido segue intacta — não há por
    que reescrever, e preservar o arquivo original evita qualquer diferença
    entre o que o operador enviou e o que foi validado.
    """
    if present_modules == [module]:
        return source
    return split_workbook_by_module(
        source, module, workdir / f"modulo_{module}.xlsx"
    )


def create_batch(
    files: list[tuple[str | None, BinaryIO]],
    modules: list[int],
    settings: Settings,
    database: Database,
    *,
    name: str = "",
    criterion: str = "PERFIL_EXATO",
    profile: str = "PROVA_COMPLETA",
    margin_offers: int | None = None,
    require_optimal: bool = True,
    time_limit_seconds: float | None = None,
    confirm_warnings: bool = False,
) -> dict[str, Any]:
    """Valida e registra um lote, um upload por módulo pedido.

    Não enfileira nada: quem decide executar é o chamador, depois de conferir
    a validação de cada módulo. Módulos reprovados ficam registrados no lote
    com o motivo, e os demais seguem normalmente.
    """
    wanted = sorted(set(modules))
    if not wanted:
        raise BatchError("Selecione ao menos um módulo para o lote.")
    unsupported = [item for item in wanted if item not in SUPPORTED_MODULES]
    if unsupported:
        raise BatchError(
            "Módulo fora do intervalo aceito (51 a 54): "
            + ", ".join(str(item) for item in unsupported)
        )
    if len(wanted) > settings.max_batch_modules:
        raise BatchError(
            f"O lote aceita no máximo {settings.max_batch_modules} módulos por vez."
        )
    if not files:
        raise BatchError("Envie ao menos uma planilha.")

    batch_id = uuid.uuid4().hex
    workdir = settings.batch_dir / batch_id
    workdir.mkdir(parents=True, exist_ok=False)

    entries: list[dict[str, Any]] = []
    try:
        # 1. Materializa cada arquivo enviado e descobre o que ele contém.
        sources: list[dict[str, Any]] = []
        for position, (filename, stream) in enumerate(files, start=1):
            original = safe_filename(filename)
            stored = workdir / f"origem_{position:02d}.xlsx"
            with stored.open("wb") as target:
                shutil.copyfileobj(stream, target, length=1024 * 1024)
            if stored.stat().st_size == 0:
                raise BatchError(f"A planilha {original} está vazia.")
            if stored.stat().st_size > settings.max_upload_bytes:
                raise BatchError(f"A planilha {original} excede o limite de 50 MB.")
            found = inspect_workbook(stored)
            sources.append({
                "original_name": original,
                "path": stored,
                "modules": [item["module"] for item in found["modules"]],
            })

        # 2. Cada módulo precisa vir de exatamente uma planilha, senão o lote
        #    misturaria bases diferentes sem o operador perceber.
        owners: dict[int, list[dict[str, Any]]] = {}
        for module in wanted:
            owners[module] = [
                item for item in sources if module in item["modules"]
            ]
        missing = [module for module in wanted if not owners[module]]
        if missing:
            raise BatchError(
                "Nenhuma planilha enviada contém o módulo "
                + ", ".join(str(item) for item in missing)
                + "."
            )
        ambiguous = [module for module in wanted if len(owners[module]) > 1]
        if ambiguous:
            raise BatchError(
                "Mais de uma planilha contém o módulo "
                + ", ".join(str(item) for item in ambiguous)
                + ". Envie uma origem por módulo."
            )

        # 3. Uma validação por módulo, pelo mesmo caminho do envio individual.
        for module in wanted:
            origin = owners[module][0]
            module_file = _prepare_module_file(
                origin["path"], module, origin["modules"], workdir
            )
            display_name = origin["original_name"]
            if module_file != origin["path"]:
                display_name = f"{Path(display_name).stem}_M{module}.xlsx"
            try:
                with module_file.open("rb") as handle:
                    upload = save_upload_stream(
                        handle,
                        display_name,
                        module,
                        settings,
                        database,
                        criterion,
                        profile,
                        margin_offers,
                    )
            except UploadValidationError as exc:
                entries.append({
                    "module": module,
                    "upload_id": None,
                    "filename": display_name,
                    "validation_status": "REPROVADO",
                    "runnable": False,
                    "reason": str(exc),
                    "validation": None,
                })
                continue
            report = upload["validation"]
            status = report["status"]
            runnable = status != "REPROVADO" and (
                status != "APROVADO_COM_RESSALVAS" or confirm_warnings
            )
            reason = ""
            if status == "REPROVADO":
                reason = "A base do módulo foi reprovada na validação."
            elif status == "APROVADO_COM_RESSALVAS" and not confirm_warnings:
                reason = "Confirme as ressalvas para liberar este módulo."
            entries.append({
                "module": module,
                "upload_id": upload["id"],
                "filename": upload["filename"],
                "validation_status": status,
                "runnable": runnable,
                "reason": reason,
                # Os mesmos números que a rodada única mostra no passo de
                # validação, para que o lote não obrigue o operador a abrir a
                # planilha de pendências só para saber o tamanho do problema.
                "validation": {
                    "allocating_rows": report.get("metadata", {}).get("allocating_rows", 0),
                    "issue_groups": report.get("summary", {}).get("issue_groups", 0),
                    "blocking_issue_groups": report.get("summary", {}).get(
                        "blocking_issue_groups", 0
                    ),
                    "by_severity": report.get("summary", {}).get("by_severity", {}),
                    "issues": [
                        {
                            "severity": issue.get("severity", ""),
                            "code": issue.get("code", ""),
                            "sheet": issue.get("sheet") or "",
                            "column": issue.get("column") or "",
                            "message": issue.get("message", ""),
                            "rows": (issue.get("rows") or [])[:6],
                            "count": issue.get("count", 0),
                        }
                        for issue in report.get("issues", [])
                    ],
                },
            })
    except Exception:
        shutil.rmtree(workdir, ignore_errors=True)
        raise

    database.create_batch({
        "id": batch_id,
        "name": name.strip() or f"Lote de {len(wanted)} módulo(s)",
        "criterion": criterion,
        "profile": profile,
        "margin_offers": margin_offers,
        "require_optimal": require_optimal,
        "time_limit_seconds": time_limit_seconds,
        "modules_json": entries,
        "created_at": utc_now(),
    })
    # Criar e consultar devolvem exatamente a mesma forma. Montar aqui um dicionário
    # parecido, porém sem `status` e `totals`, fazia a tela quebrar no primeiro
    # render depois da validação: o tipo dizia `ModuleBatch`, mas os campos não
    # estavam lá.
    stored = database.get_batch(batch_id)
    if stored is None:  # pragma: no cover - falha de escrita no SQLite
        raise BatchError("O lote não pôde ser registrado.")
    return public_batch(database, stored)


def public_batch(database: Database, batch: dict[str, Any]) -> dict[str, Any]:
    """Lote com o estado atual de cada módulo, pronto para a tela.

    Cada linha combina o que a validação decidiu na criação com o que a rodada
    daquele módulo alcançou até agora. Os indicadores vêm do resumo auditado,
    e não de contagem própria, para que o painel do lote e o Dashboard do
    módulo nunca contem coisas diferentes.
    """
    jobs_by_module = {
        int(job["module"]): job for job in database.jobs_for_batch(batch["id"])
    }
    modules: list[dict[str, Any]] = []
    for entry in batch["modules"]:
        module = int(entry["module"])
        row: dict[str, Any] = dict(entry)
        job = jobs_by_module.get(module)
        row["job"] = public_job(job) if job else None
        row["kpis"] = None
        if job and job.get("round_dir"):
            try:
                summary = load_summary(job)
            except (FileNotFoundError, ValueError, KeyError):
                summary = None
            if summary:
                transmissions = int(summary.get("transmissions", 0) or 0)
                allocated = int(summary.get("allocated", 0) or 0)
                row["kpis"] = {
                    "transmissions": transmissions,
                    "allocated": allocated,
                    "unassigned": int(summary.get("unassigned", 0) or 0),
                    "used_teachers": int(summary.get("used_teachers", 0) or 0),
                    "solver_status": summary.get("solver_status"),
                    "coverage_pct": (
                        round(100 * allocated / transmissions, 2)
                        if transmissions
                        else 0.0
                    ),
                }
        modules.append(row)

    # Uma rodada em andamento não fica em QUEUED/RUNNING: `public_job` troca o
    # status pelo estado que o motor publica (VALIDANDO, RESOLVENDO, AUDITANDO,
    # PUBLICANDO). Quem decide se ainda há trabalho é a flag `terminal`, e não
    # uma lista de nomes de estado — senão o lote se declara encerrado no meio.
    jobs = [row["job"] for row in modules if row["job"]]
    pending = [job for job in jobs if not job["terminal"]]
    concluded = [job for job in jobs if job["status"] == "CONCLUIDA"]
    if not jobs:
        status = "AGUARDANDO"
    elif pending:
        status = "EXECUTANDO"
    elif len(concluded) == len(jobs):
        status = "CONCLUIDO"
    else:
        status = "PARCIAL"

    covered = [row for row in modules if row["kpis"]]
    total_offers = sum(row["kpis"]["transmissions"] for row in covered)
    total_allocated = sum(row["kpis"]["allocated"] for row in covered)
    return {
        "id": batch["id"],
        "name": batch["name"],
        "criterion": batch["criterion"],
        "profile": batch["profile"],
        "margin_offers": batch["margin_offers"],
        "require_optimal": bool(batch["require_optimal"]),
        "time_limit_seconds": batch["time_limit_seconds"],
        "created_at": batch["created_at"],
        "status": status,
        "modules": modules,
        "totals": {
            "modules": len(modules),
            "runnable": sum(1 for row in modules if row["runnable"]),
            "queued_or_running": len(pending),
            "concluded": len(concluded),
            "offers": total_offers,
            "allocated": total_allocated,
            "coverage_pct": (
                round(100 * total_allocated / total_offers, 2) if total_offers else 0.0
            ),
        },
    }


def module_is_runnable(entry: dict[str, Any], confirm_warnings: bool) -> bool:
    """O módulo pode ir para a fila agora?

    A confirmação de ressalvas é reavaliada aqui, e não congelada na criação:
    é o que permite o mesmo fluxo da rodada única — validar, ler as ressalvas
    e só então confirmar — em vez de exigir a confirmação às cegas.
    """
    if not entry.get("upload_id"):
        return False
    status = entry.get("validation_status")
    if status == "REPROVADO":
        return False
    if status == "APROVADO_COM_RESSALVAS":
        return bool(entry.get("runnable")) or confirm_warnings
    return True


def runnable_uploads(
    database: Database,
    batch: dict[str, Any],
    confirm_warnings: bool = False,
) -> list[dict[str, Any]]:
    """Uploads do lote que podem ir para a fila, sem repetir o que já rodou."""
    already = {int(job["module"]) for job in database.jobs_for_batch(batch["id"])}
    uploads: list[dict[str, Any]] = []
    for entry in batch["modules"]:
        module = int(entry["module"])
        if module in already or not module_is_runnable(entry, confirm_warnings):
            continue
        upload = database.get_upload(str(entry["upload_id"]))
        if upload:
            uploads.append(upload)
    return uploads
