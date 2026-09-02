"""Estudo em lote: a mesma pergunta aplicada a vários módulos do ano.

Um estudo não é um segundo motor de cenários. Ele guarda a premissa por *chave
de negócio* — a chapa do docente, o código do curso ou o da disciplina, nunca a
linha da planilha — e projeta essa premissa em um cenário filho por módulo. Cada filho segue exatamente o caminho
auditado de sempre: materialização, motor secundário, manifesto, auditoria,
comparação contra a própria rodada-base e homologação individual.

A chave de negócio não é preciosismo. Ao fatiar a planilha anual por módulo, o
lote copia DOCENTES inteira e filtra MAPA PEDAGÓGICO; a linha de uma oferta
muda de módulo para módulo, e amarrar a premissa a um número de linha faria a
mesma pergunta significar coisas diferentes em cada recorte.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from ..config import Settings
from ..database import Database, utc_now
from .jobs import artifact_path, load_summary, public_job
from .scenarios import (
    ScenarioError,
    evaluate_change,
    _dump_value,
    _normalize_change_value,
    public_scenario,
    read_source_values,
    source_catalog,
)


DOCENTES_SHEET = "DOCENTES"

# Movimentos disponíveis no estudo, e a chave de negócio de cada alvo.
#
# O docente é endereçado pela chapa e a oferta pelo curso ou pela disciplina.
# Nenhum deles é a linha da planilha: a linha do docente até coincide entre os
# recortes hoje, mas a da oferta não — o recorte por módulo filtra o MAPA
# PEDAGÓGICO, e a linha 40 do módulo 51 não é a linha 40 do módulo 52. Mover
# "o curso ADM para quarta-feira" só é a mesma pergunta em todos os módulos
# quando o alvo é o curso.
STUDY_PREMISE_TYPES: dict[str, dict[str, Any]] = {
    "CAPACIDADE": {
        "entity_type": "teacher",
        "target_types": ("TEACHER_BADGE",),
        "fields": ("STATUS", "CH_LETIVA"),
    },
    "COMPATIBILIDADE": {
        "entity_type": "teacher",
        "target_types": ("TEACHER_BADGE",),
        "fields": ("PERFIL_DISCIPLINA",),
    },
    "AGENDA": {
        "entity_type": "offer",
        "target_types": ("COURSE", "DISCIPLINE"),
        "fields": ("DIA_AULA", "HORÁRIO", "ORDEM"),
    },
}

# Quantos alvos uma única submissão pode trazer. O mesmo espírito do teto da
# alteração em lote de um cenário: conter um filtro amplo demais que viraria
# uma transação enorme sem o operador perceber.
MAX_PREMISE_TARGETS = 100

# Teto de premissas por estudo. Uma pergunta executiva tem poucas premissas;
# um número muito maior indica edição em massa, que é trabalho do lote primário.
MAX_STUDY_PREMISES = 50


class StudyError(ValueError):
    pass


def _normalize_badge(value: Any) -> str:
    """Chapa comparável entre a planilha e o que a tela devolve.

    A mesma chapa aparece ora como número, ora como texto com zeros à esquerda,
    conforme a formatação da célula. Comparar sem normalizar faria a premissa
    não encontrar o docente em um módulo e encontrar no outro.
    """
    text = str(value if value is not None else "").strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.lstrip("0") or text


def _teachers_fingerprint(source: Path) -> str:
    """Impressão digital da aba DOCENTES de uma rodada-base.

    Um estudo aponta para pessoas por chapa. Se as bases docentes dos módulos
    divergirem, a mesma chapa pode ser outra pessoa — ou não existir —, e a
    comparação entre módulos deixaria de responder à pergunta feita.
    """
    digest = hashlib.sha256()
    workbook = load_workbook(source, read_only=True, data_only=True)
    try:
        if DOCENTES_SHEET not in workbook.sheetnames:
            raise StudyError(
                f"A rodada-base não possui a aba {DOCENTES_SHEET}."
            )
        for values in workbook[DOCENTES_SHEET].iter_rows(values_only=True):
            if not any(value not in (None, "") for value in values):
                continue
            digest.update(
                "\x1f".join(
                    "" if value is None else str(value) for value in values
                ).encode("utf-8")
            )
            digest.update(b"\x1e")
    finally:
        workbook.close()
    return digest.hexdigest()


def _baseline_jobs(database: Database, batch_id: str) -> dict[int, dict[str, Any]]:
    """Rodadas concluídas do lote, por módulo."""
    return {
        int(job["module"]): job
        for job in database.jobs_for_batch(batch_id)
        if job["status"] == "CONCLUIDA" and job.get("round_dir")
    }


def available_batches(database: Database, limit: int = 50) -> list[dict[str, Any]]:
    """Lotes que podem servir de base para um estudo, com os módulos prontos.

    A tela precisa dizer *antes* da escolha quais módulos daquele lote têm
    rodada concluída — um lote parcialmente executado ainda serve, desde que o
    operador saiba que o estudo cobrirá menos do que o ano inteiro.
    """
    options: list[dict[str, Any]] = []
    for batch in database.list_batches(limit):
        baselines = _baseline_jobs(database, batch["id"])
        if not baselines:
            continue
        options.append({
            "id": batch["id"],
            "name": batch["name"],
            "criterion": batch["criterion"],
            "profile": batch["profile"],
            "created_at": batch["created_at"],
            "modules": [
                {
                    "module": module,
                    "baseline_job_id": baselines[module]["id"],
                    "round_name": baselines[module].get("round_name"),
                }
                for module in sorted(baselines)
            ],
        })
    return options


def create_study(
    settings: Settings,
    database: Database,
    *,
    batch_id: str,
    modules: list[int],
    name: str,
    description: str = "",
) -> dict[str, Any]:
    """Registra um estudo e o cenário filho de cada módulo escolhido."""
    name = name.strip()
    if len(name) < 3:
        raise StudyError("Informe um nome com pelo menos três caracteres.")
    batch = database.get_batch(batch_id)
    if not batch:
        raise StudyError("Lote não encontrado.")
    wanted = sorted(set(modules))
    if not wanted:
        raise StudyError("Selecione ao menos um módulo para o estudo.")
    if len(wanted) > settings.max_batch_modules:
        raise StudyError(
            f"O estudo cobre no máximo {settings.max_batch_modules} módulos."
        )
    baselines = _baseline_jobs(database, batch_id)
    missing = [module for module in wanted if module not in baselines]
    if missing:
        raise StudyError(
            "Sem rodada concluída no lote para o módulo "
            + ", ".join(str(item) for item in missing)
            + "."
        )

    # Uma base docente por módulo, e todas precisam ser a mesma. A verificação
    # acontece aqui, uma vez, e não a cada premissa: se as bases divergem, o
    # estudo inteiro é que não faz sentido.
    fingerprints: dict[int, str] = {}
    for module in wanted:
        try:
            source = artifact_path(baselines[module], "source_copy")
        except FileNotFoundError as exc:
            raise StudyError(
                f"A cópia auditada da rodada-base do módulo {module} não está disponível."
            ) from exc
        fingerprints[module] = _teachers_fingerprint(source)
    distinct = set(fingerprints.values())
    if len(distinct) > 1:
        divergent = [
            str(module)
            for module in wanted
            if fingerprints[module] != fingerprints[wanted[0]]
        ]
        raise StudyError(
            "As rodadas-base escolhidas não compartilham a mesma base docente "
            f"(divergem nos módulos {', '.join(divergent)}). "
            "Uma premissa por chapa apontaria para pessoas diferentes em cada módulo."
        )

    study_id = uuid.uuid4().hex
    now = utc_now()
    database.create_study({
        "id": study_id,
        "batch_id": batch_id,
        "name": name,
        "description": description.strip(),
        "status": "RASCUNHO",
        "modules_json": wanted,
        "created_at": now,
        "updated_at": now,
    })
    for module in wanted:
        scenario_id = uuid.uuid4().hex
        database.create_scenario({
            "id": scenario_id,
            "baseline_job_id": baselines[module]["id"],
            "name": f"{name} · M{module}",
            "description": description.strip(),
            "status": "RASCUNHO",
            "study_id": study_id,
            "created_at": now,
            "updated_at": now,
        })
        database.create_study_module({
            "study_id": study_id,
            "module": module,
            "baseline_job_id": baselines[module]["id"],
            "scenario_id": scenario_id,
        })
    return public_study(database, database.get_study(study_id) or {})


def module_catalogs(database: Database, study_id: str) -> dict[int, dict[str, Any]]:
    """Catálogo da rodada-base de cada módulo do estudo, na ordem dos módulos."""
    modules = database.study_modules(study_id)
    if not modules:
        raise StudyError("O estudo não possui módulos.")
    return {
        int(entry["module"]): source_catalog(database, str(entry["scenario_id"]))
        for entry in modules
        if entry["scenario_id"]
    }


def _aggregate_offer_targets(
    catalogs: dict[int, dict[str, Any]],
    key: str,
    name_field: str,
) -> list[dict[str, Any]]:
    """Agrupa as ofertas de todos os módulos por uma chave de negócio.

    O que a tela precisa saber antes de escolher um alvo é onde ele existe e
    onde ele dói: quantas ofertas o curso tem em cada módulo e quantas ficaram
    sem alocação na rodada-base. É essa contagem que responde "qual curso vive
    com disciplina sem docente" sem sair da tela.
    """
    grouped: dict[str, dict[str, Any]] = {}
    for module, catalog in sorted(catalogs.items()):
        for offer in catalog["offers"]:
            code = str(offer.get(key) or "").strip()
            if not code:
                continue
            record = grouped.setdefault(code, {
                "code": code,
                "name": str(offer.get(name_field) or code),
                "course_code": str(offer.get("course_code") or ""),
                "course_name": str(offer.get("course_name") or ""),
                "modules": {},
                "days": {},
                "times": {},
                "orders": {},
                "total_offers": 0,
                "total_unassigned": 0,
            })
            presence = record["modules"].setdefault(
                module, {"module": module, "offers": 0, "unassigned": 0}
            )
            presence["offers"] += 1
            record["total_offers"] += 1
            if offer.get("baseline_status") != "ALOCADA":
                presence["unassigned"] += 1
                record["total_unassigned"] += 1
            for field, bucket in (
                ("day", "days"), ("time", "times"), ("order", "orders")
            ):
                value = str(offer.get(field) or "").strip()
                if value:
                    record[bucket][value] = record[bucket].get(value, 0) + 1
    result = []
    for record in grouped.values():
        record["modules"] = [record["modules"][key] for key in sorted(record["modules"])]
        for bucket in ("days", "times", "orders"):
            record[bucket] = sorted(record[bucket])
        result.append(record)
    # Quem tem mais lacuna aparece primeiro: é o alvo mais provável de um
    # estudo de agenda, e deixá-lo no fim da lista esconderia a pergunta.
    result.sort(key=lambda item: (-item["total_unassigned"], item["name"]))
    return result


def study_catalog(database: Database, study_id: str) -> dict[str, Any]:
    """Alvos possíveis do estudo: docentes, cursos e disciplinas.

    Os docentes vêm de um módulo só, porque a criação já provou que a aba
    DOCENTES é idêntica em todos eles. Cursos e disciplinas são agregados de
    todos os módulos, já que cada um traz o seu próprio recorte do MAPA.
    """
    catalogs = module_catalogs(database, study_id)
    first = catalogs[min(catalogs)]
    days: dict[str, int] = {}
    times: dict[str, int] = {}
    orders: dict[str, int] = {}
    for catalog in catalogs.values():
        for offer in catalog["offers"]:
            for field, bucket in (
                ("day", days), ("time", times), ("order", orders)
            ):
                value = str(offer.get(field) or "").strip()
                if value:
                    bucket[value] = bucket.get(value, 0) + 1
    return {
        "modules": sorted(catalogs),
        "teachers": [
            {
                "badge": item["badge"],
                "name": item["name"],
                "status": item["status"],
                "job_function": item["job_function"],
                "teaching_capacity": item["teaching_capacity"],
                "contracted_capacity": item["contracted_capacity"],
                "manager": item["manager"],
                "profile": item["profile"],
            }
            for item in first["teachers"]
            if _normalize_badge(item["badge"])
        ],
        "courses": _aggregate_offer_targets(catalogs, "course_code", "course_name"),
        "disciplines": _aggregate_offer_targets(
            catalogs, "discipline_code", "discipline_name"
        ),
        # As faixas efetivamente praticadas no ano. Sugerir um horário que a
        # operação não usa não ajuda a decidir nada.
        "practiced": {
            "days": [{"value": key, "offers": days[key]} for key in sorted(days)],
            "times": [{"value": key, "offers": times[key]} for key in sorted(times)],
            "orders": [{"value": key, "offers": orders[key]} for key in sorted(orders)],
        },
    }


# ----------------------------------------------------------------------
# Premissas
# ----------------------------------------------------------------------


def _validate_premise(
    premise_type: str,
    target_type: str,
    field_name: str,
) -> dict[str, Any]:
    contract = STUDY_PREMISE_TYPES.get(premise_type)
    if not contract:
        raise StudyError(
            "Movimento não disponível no estudo em lote. "
            "Nesta versão o lote cobre movimentos de corpo docente."
        )
    if target_type not in contract["target_types"]:
        raise StudyError("Alvo inválido para o movimento selecionado.")
    if field_name not in contract["fields"]:
        raise StudyError(
            "A alteração solicitada não pertence ao contrato de cenários."
        )
    return contract


def _editable_study(database: Database, study_id: str) -> dict[str, Any]:
    study = database.get_study(study_id)
    if not study:
        raise StudyError("Estudo não encontrado.")
    running = [
        entry
        for entry in database.study_modules(study_id)
        if entry["scenario_id"]
        and (database.latest_scenario_job(str(entry["scenario_id"])) or {}).get(
            "status"
        )
        in {"QUEUED", "RUNNING"}
    ]
    if running:
        raise StudyError(
            "O estudo está simulando. Aguarde os módulos terminarem para editar "
            "as premissas."
        )
    return study


def _target_index(
    catalog: dict[str, Any],
    target_type: str,
) -> dict[str, str]:
    """Alvos conhecidos daquele tipo, da chave normalizada para o rótulo."""
    if target_type == "TEACHER_BADGE":
        return {
            _normalize_badge(item["badge"]): f"{item['name']} ({item['badge']})"
            for item in catalog["teachers"]
        }
    source = catalog["courses"] if target_type == "COURSE" else catalog["disciplines"]
    index: dict[str, str] = {}
    for item in source:
        modules = "/".join(f"M{row['module']}" for row in item["modules"])
        index[item["code"]] = f"{item['name']} ({item['code']}) · {modules}"
    return index


def add_study_premise(
    database: Database,
    study_id: str,
    *,
    premise_type: str,
    target_type: str,
    target_values: list[str],
    field_name: str,
    new_value: Any = None,
    adjustment: int | None = None,
) -> dict[str, Any]:
    """Grava uma premissa por alvo e reprojeta o estudo.

    Vários alvos de uma vez porque a pergunta raramente é sobre uma pessoa ou um
    curso só: "e se eu movesse estes três cursos para quarta" é uma pergunta, e
    obrigar a repetir o formulário três vezes não a torna mais clara.
    """
    study = _editable_study(database, study_id)
    premise_type = premise_type.strip().upper()
    target_type = target_type.strip().upper()
    field_name = field_name.strip().upper()
    wanted = [str(item or "").strip() for item in target_values]
    wanted = list(dict.fromkeys(item for item in wanted if item))
    _validate_premise(premise_type, target_type, field_name)
    if not wanted:
        raise StudyError("Escolha ao menos um alvo para a premissa.")
    if len(wanted) > MAX_PREMISE_TARGETS:
        raise StudyError(
            f"A premissa aceita no máximo {MAX_PREMISE_TARGETS} alvos por vez."
        )
    if len(database.list_study_premises(study_id)) + len(wanted) > MAX_STUDY_PREMISES:
        raise StudyError(
            f"O estudo aceita no máximo {MAX_STUDY_PREMISES} premissas."
        )

    if adjustment is not None:
        if field_name != "CH_LETIVA":
            raise StudyError("O ajuste relativo só se aplica a CH_LETIVA.")
        if isinstance(adjustment, bool) or not isinstance(adjustment, int):
            raise StudyError(
                "O ajuste de CH_LETIVA deve ser um número inteiro de horas."
            )
        if adjustment == 0:
            raise StudyError("O ajuste de CH_LETIVA precisa ser diferente de zero.")
        operation = "ADJUST"
        value: Any = adjustment
    else:
        operation = "SET"
        try:
            value = _normalize_change_value(field_name, new_value)
        except ScenarioError as exc:
            raise StudyError(str(exc)) from exc

    # O alvo precisa existir na base do estudo. Descobrir isso só na projeção
    # transformaria um erro de digitação em quatro módulos sem efeito nenhum.
    catalog = study_catalog(database, study_id)
    known = _target_index(catalog, target_type)
    normalize = _normalize_badge if target_type == "TEACHER_BADGE" else lambda item: item
    unknown = [item for item in wanted if normalize(item) not in known]
    if unknown:
        noun = {
            "TEACHER_BADGE": "chapa",
            "COURSE": "curso",
            "DISCIPLINE": "disciplina",
        }[target_type]
        raise StudyError(
            f"Alvo fora da base do estudo ({noun}): "
            + ", ".join(unknown[:5])
            + "."
        )

    now = utc_now()
    for item in wanted:
        database.upsert_study_premise({
            "id": uuid.uuid4().hex,
            "study_id": study_id,
            "premise_type": premise_type,
            "target_type": target_type,
            "target_value": item,
            "target_label": known[normalize(item)],
            "field_name": field_name,
            "operation": operation,
            "value_json": _dump_value(value),
            "created_at": now,
        })
    projection = project_study(database, study_id)
    return {
        "study": public_study(database, database.get_study(study_id) or study),
        "projection": projection,
    }


def delete_study_premise(database: Database, study_id: str, premise_id: str) -> bool:
    _editable_study(database, study_id)
    removed = database.delete_study_premise(study_id, premise_id)
    if removed:
        project_study(database, study_id)
    return removed


def public_premise(premise: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": premise["id"],
        "premise_type": premise["premise_type"],
        "target_type": premise["target_type"],
        "target_value": premise["target_value"],
        "target_label": premise["target_label"],
        "field_name": premise["field_name"],
        "operation": premise["operation"],
        "value": json.loads(premise["value_json"]),
        "created_at": premise["created_at"],
    }


# ----------------------------------------------------------------------
# Projeção
# ----------------------------------------------------------------------


def _change_signature(changes: list[dict[str, Any]]) -> tuple:
    """Identidade do conjunto de alterações de um cenário.

    Duas projeções com a mesma assinatura produzem a mesma planilha, e portanto
    a simulação já calculada continua valendo.
    """
    return tuple(sorted(
        (
            item["entity_type"],
            int(item["row_number"]),
            item["field_name"],
            item["new_value_json"],
        )
        for item in changes
    ))


def _premise_entity(premise: dict[str, Any]) -> str:
    """Aba da planilha em que a premissa escreve."""
    contract = STUDY_PREMISE_TYPES.get(premise["premise_type"])
    if not contract:
        raise StudyError(
            f"Movimento desconhecido no estudo: {premise['premise_type']}."
        )
    return str(contract["entity_type"])


def _resolve_targets(
    premise: dict[str, Any],
    catalog: dict[str, Any],
) -> list[int]:
    """Linhas daquele módulo atingidas pela premissa.

    É aqui que a chave de negócio vira número de linha, e por isso a conversão
    acontece uma vez por módulo: o mesmo curso ocupa linhas diferentes em cada
    recorte, e pode não existir em algum deles.
    """
    target_type = premise["target_type"]
    wanted = str(premise["target_value"] or "").strip()
    if target_type == "TEACHER_BADGE":
        badge = _normalize_badge(wanted)
        return sorted(
            item["row_number"]
            for item in catalog["teachers"]
            if _normalize_badge(item["badge"]) == badge
        )
    if target_type == "COURSE":
        return sorted(
            item["row_number"]
            for item in catalog["offers"]
            if str(item.get("course_code") or "").strip() == wanted
        )
    if target_type == "DISCIPLINE":
        return sorted(
            item["row_number"]
            for item in catalog["offers"]
            if str(item.get("discipline_code") or "").strip() == wanted
        )
    return []


def _project_module(
    database: Database,
    entry: dict[str, Any],
    premises: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reescreve as alterações do cenário de um módulo a partir das premissas.

    A reescrita é integral, e não incremental: apagar uma premissa no estudo
    precisa apagar exatamente o que ela havia produzido, e recomeçar do zero é
    a única forma de garantir isso sem rastrear a origem de cada célula.
    """
    module = int(entry["module"])
    scenario_id = str(entry["scenario_id"])
    scenario = database.get_scenario(scenario_id)
    if not scenario:
        return {
            "module": module,
            "applied_count": 0,
            "results": [],
            "locked": True,
            "reason": "O cenário deste módulo não existe mais.",
        }
    if scenario["status"] in {"EXECUTANDO", "HOMOLOGADO"}:
        return {
            "module": module,
            "applied_count": len(database.list_scenario_changes(scenario_id)),
            "results": [],
            "locked": True,
            "reason": (
                "Módulo homologado: as premissas atuais não foram aplicadas aqui."
                if scenario["status"] == "HOMOLOGADO"
                else "Módulo em simulação: as premissas serão aplicadas depois."
            ),
        }

    baseline = database.get_job(str(entry["baseline_job_id"]))
    if not baseline:
        return {
            "module": module,
            "applied_count": 0,
            "results": [],
            "locked": True,
            "reason": "A rodada-base deste módulo não existe mais.",
        }
    source = artifact_path(baseline, "source_copy")
    catalog = source_catalog(database, scenario_id)
    contracted = {
        item["row_number"]: item.get("contracted_capacity")
        for item in catalog["teachers"]
    }

    # Uma leitura por aba e campo, com todas as linhas de uma vez: o valor
    # antigo precisa ser exatamente o que a materialização vai reler da célula,
    # senão ela aborta acusando que a origem mudou. A aba entra na chave porque
    # PERFIL_DISCIPLINA existe dos dois lados — no docente é o que ele pode
    # assumir, na oferta é o que ela exige.
    rows_by_premise: dict[str, list[int]] = {}
    rows_by_source: dict[tuple[str, str], set[int]] = {}
    for premise in premises:
        rows = _resolve_targets(premise, catalog)
        rows_by_premise[premise["id"]] = rows
        if rows:
            key = (_premise_entity(premise), premise["field_name"])
            rows_by_source.setdefault(key, set()).update(rows)
    current: dict[tuple[str, str], dict[int, Any]] = {
        key: read_source_values(source, key[0], sorted(rows), key[1])
        for key, rows in rows_by_source.items()
    }

    # O conjunto de alterações antes da reescrita. Comparar depois é o que
    # distingue uma reprojeção que não mudou nada de uma que invalidou o
    # resultado já calculado.
    previous = _change_signature(database.list_scenario_changes(scenario_id))
    database.clear_scenario_changes(scenario_id)
    results: list[dict[str, Any]] = []
    applied_count = 0
    for premise in premises:
        rows = rows_by_premise[premise["id"]]
        if not rows:
            results.append({
                "premise_id": premise["id"],
                "applied": 0,
                "reason": "O alvo não existe neste módulo.",
            })
            continue
        value = json.loads(premise["value_json"])
        relative = premise["operation"] == "ADJUST"
        entity_type = _premise_entity(premise)
        values = current[(entity_type, premise["field_name"])]
        applied_here = 0
        refusal = ""
        for row_number in rows:
            old_value = values[row_number]
            target, why = evaluate_change(
                premise["field_name"],
                old_value,
                target=None if relative else value,
                adjustment=int(value) if relative else None,
                contracted_capacity=contracted.get(row_number),
            )
            if why:
                refusal = refusal or why
                continue
            database.upsert_scenario_change({
                "id": uuid.uuid4().hex,
                "scenario_id": scenario_id,
                "change_type": premise["premise_type"],
                "entity_type": entity_type,
                "row_number": row_number,
                "field_name": premise["field_name"],
                "old_value_json": _dump_value(old_value),
                "new_value_json": _dump_value(target),
                "created_at": utc_now(),
            })
            applied_here += 1
        applied_count += applied_here
        results.append({
            "premise_id": premise["id"],
            "applied": applied_here,
            "reason": "" if applied_here else refusal,
        })

    # Um cenário cujas alterações mudaram volta a ser rascunho. Sem isso a tela
    # continuaria exibindo a cobertura da simulação anterior ao lado das
    # premissas novas — o número mais perigoso da ferramenta, porque parece uma
    # resposta à pergunta que está escrita na tela e é a resposta a outra.
    current_signature = _change_signature(database.list_scenario_changes(scenario_id))
    if scenario["status"] != "RASCUNHO":
        if current_signature == previous:
            # A reprojeção reescreveu exatamente as mesmas alterações, então a
            # planilha materializada seria idêntica e a simulação continua
            # valendo. `upsert_scenario_change` derruba o cenário para rascunho
            # a cada escrita — proteção certa para quem edita uma premissa à
            # mão, mas aqui a reescrita é o método, e não uma mudança.
            database.update_scenario(scenario_id, status=scenario["status"])
        else:
            database.update_scenario(scenario_id, status="RASCUNHO")
    return {
        "module": module,
        "applied_count": applied_count,
        "results": results,
        "locked": False,
        "reason": "",
    }


def project_study(database: Database, study_id: str) -> list[dict[str, Any]]:
    """Projeta as premissas do estudo em cada módulo e relata o efeito."""
    premises = database.list_study_premises(study_id)
    return [
        _project_module(database, entry, premises)
        for entry in database.study_modules(study_id)
        if entry["scenario_id"]
    ]


def runnable_scenarios(database: Database, study_id: str) -> list[str]:
    """Cenários do estudo que têm o que simular agora.

    Um módulo sem alteração projetada não vai para a fila: o motor secundário
    recusaria uma simulação sem premissa, e enfileirá-lo só produziria um erro
    no lugar de uma linha honesta dizendo que ali nada muda.
    """
    ready: list[str] = []
    for entry in database.study_modules(study_id):
        scenario_id = entry["scenario_id"]
        if not scenario_id:
            continue
        scenario = database.get_scenario(str(scenario_id))
        if not scenario or scenario["status"] in {"EXECUTANDO", "HOMOLOGADO"}:
            continue
        if database.list_scenario_changes(str(scenario_id)):
            ready.append(str(scenario_id))
    return ready


# ----------------------------------------------------------------------
# Leitura
# ----------------------------------------------------------------------


def _module_kpis(job: dict[str, Any] | None) -> dict[str, Any] | None:
    if not job or not job.get("round_dir") or job["status"] != "CONCLUIDA":
        return None
    try:
        summary = load_summary(job)
    except (FileNotFoundError, ValueError, KeyError):
        return None
    transmissions = int(summary.get("transmissions", 0) or 0)
    allocated = int(summary.get("allocated", 0) or 0)
    return {
        "transmissions": transmissions,
        "allocated": allocated,
        "unassigned": int(summary.get("unassigned", 0) or 0),
        "used_teachers": int(summary.get("used_teachers", 0) or 0),
        "solver_status": summary.get("solver_status"),
        "coverage_pct": (
            round(100 * allocated / transmissions, 2) if transmissions else 0.0
        ),
    }


def public_study(database: Database, study: dict[str, Any]) -> dict[str, Any]:
    """Estudo com o estado de cada módulo, pronto para a tela.

    O status exibido vem das rodadas dos filhos, e não da coluna gravada: as
    rodadas são a única fonte que sobrevive a um reinício do servidor no meio
    de uma simulação.
    """
    if not study:
        raise StudyError("Estudo não encontrado.")
    study_id = study["id"]
    premises = [
        public_premise(item) for item in database.list_study_premises(study_id)
    ]
    modules: list[dict[str, Any]] = []
    for entry in database.study_modules(study_id):
        scenario_id = entry["scenario_id"]
        scenario = database.get_scenario(str(scenario_id)) if scenario_id else None
        baseline = database.get_job(str(entry["baseline_job_id"]))
        job = (
            database.latest_scenario_job(str(scenario_id)) if scenario_id else None
        )
        # Uma simulação que ficou para trás das premissas atuais não é um
        # resultado, é história. Ela continua visível — o operador precisa saber
        # que aquele módulo já rodou —, mas sem os indicadores, que responderiam
        # a uma pergunta diferente da que está escrita na tela.
        stale = bool(
            job
            and job["status"] == "CONCLUIDA"
            and scenario
            and scenario["status"] == "RASCUNHO"
        )
        modules.append({
            "module": int(entry["module"]),
            "baseline_job_id": entry["baseline_job_id"],
            "scenario_id": scenario_id,
            "scenario": public_scenario(database, scenario) if scenario else None,
            "job": public_job(job) if job else None,
            "change_count": (
                len(database.list_scenario_changes(str(scenario_id)))
                if scenario_id
                else 0
            ),
            "stale": stale,
            "baseline_kpis": _module_kpis(baseline),
            "kpis": None if stale else _module_kpis(job),
            "promoted": bool(scenario and scenario.get("official_job_id")),
        })

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

    covered = [row for row in modules if row["kpis"] and row["baseline_kpis"]]
    baseline_offers = sum(row["baseline_kpis"]["transmissions"] for row in covered)
    baseline_allocated = sum(row["baseline_kpis"]["allocated"] for row in covered)
    study_offers = sum(row["kpis"]["transmissions"] for row in covered)
    study_allocated = sum(row["kpis"]["allocated"] for row in covered)
    baseline_coverage = (
        round(100 * baseline_allocated / baseline_offers, 2) if baseline_offers else 0.0
    )
    study_coverage = (
        round(100 * study_allocated / study_offers, 2) if study_offers else 0.0
    )
    return {
        "id": study_id,
        "batch_id": study["batch_id"],
        "name": study["name"],
        "description": study["description"],
        "created_at": study["created_at"],
        "updated_at": study["updated_at"],
        "status": status,
        "premises": premises,
        "modules": modules,
        "totals": {
            "modules": len(modules),
            "runnable": sum(
                1 for row in modules
                if row["change_count"] and not row["promoted"]
            ),
            "queued_or_running": len(pending),
            "concluded": len(concluded),
            "compared": len(covered),
            "baseline_offers": baseline_offers,
            "baseline_allocated": baseline_allocated,
            "allocated": study_allocated,
            "allocated_delta": study_allocated - baseline_allocated,
            "baseline_coverage_pct": baseline_coverage,
            "coverage_pct": study_coverage,
            "coverage_delta_pp": round(study_coverage - baseline_coverage, 2),
            "unassigned_delta": sum(
                row["kpis"]["unassigned"] - row["baseline_kpis"]["unassigned"]
                for row in covered
            ),
            "used_teachers_delta": sum(
                row["kpis"]["used_teachers"] - row["baseline_kpis"]["used_teachers"]
                for row in covered
            ),
        },
    }
