from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from .criteria import (
    CRITERION_LABELS,
    declares_teacher_clusters,
    has_exact_profile,
    uses_cluster,
)
from .normalization import normalize
from .domain import (
    MODULE_ORDERS,
    MODULE_STAGE_1,
    MODULE_STAGE_2,
    MODULE_STAGES,
    ORDER_EXTENDED,
    ORDER_FIRST,
    ORDER_SECOND,
    AllocationResult,
    Problem,
)


def contract_model_for(job_function: str, allocated: bool) -> str:
    if not allocated:
        return "A DEFINIR"
    normalized = " ".join(job_function.strip().upper().split())
    if normalized in {"PROFESSOR DE ENSINO SUPERIOR EAD", "PROFESSOR REGENTE"}:
        return "CLT EAD"
    if normalized == "PROFESSOR DE ENSINO SUPERIOR PRESENCIAL":
        return "CLT STRICTO"
    return "A DEFINIR"


def eligibility_basis_for(problem: Problem, transmission, teacher) -> str:
    """Base da elegibilidade de uma decisão já publicada.

    CLUSTER_DECLARADO distingue a candidatura aceita pelo cluster do docente
    da que veio pela união de perfis das ofertas do cluster: são caminhos
    diferentes e a auditoria precisa saber qual valeu.
    """
    if teacher is None:
        return ""
    if has_exact_profile(transmission, teacher):
        return "PERFIL_EXATO"
    if not uses_cluster(problem.criterion):
        return "INDEFINIDA"
    if declares_teacher_clusters(problem.teachers) and normalize(transmission.cluster):
        return "CLUSTER_DECLARADO"
    return "CLUSTER"


def regime_label_for(teacher) -> str:
    """Rótulo do regime de contratação usado na abertura por cargo.

    O regime é a carga contratada (T40, T20, T12...). O sufixo Mensalista
    separa o contrato Stricto, cujo teto semanal não se aplica.
    """
    hours = teacher.contracted_capacity
    label = f"T{hours} · {hours}h contratadas"
    return f"{label} · Mensalista" if teacher.is_stricto else label


def create_round_directory(base_dir: str | Path) -> Path:
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    numbers = []
    for item in base.glob("rodada_*"):
        if item.is_dir() and item.name.removeprefix("rodada_").isdigit():
            numbers.append(int(item.name.removeprefix("rodada_")))
    round_dir = base / f"rodada_{max(numbers, default=0) + 1:03d}"
    round_dir.mkdir(parents=False, exist_ok=False)
    return round_dir


def _autosize(worksheet) -> None:
    for column in worksheet.columns:
        width = min(60, max(len(str(cell.value or "")) for cell in column) + 2)
        worksheet.column_dimensions[get_column_letter(column[0].column)].width = width
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions
    for cell in worksheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E78")


def write_results(problem: Problem, result: AllocationResult, output_dir: str | Path) -> tuple[Path, Path]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    xlsx_path = output / "resultado_alocacao.xlsx"
    json_path = output / "resumo_alocacao.json"
    teachers = {teacher.id: teacher for teacher in problem.teachers}
    transmissions = {item.id: item for item in problem.transmissions}
    teacher_stage_counts = {
        teacher.id: {stage: 0 for stage in MODULE_STAGES}
        for teacher in problem.teachers
    }
    teacher_order_counts = {
        teacher.id: {order: 0 for order in MODULE_ORDERS}
        for teacher in problem.teachers
    }
    for assignment in result.assignments:
        if assignment.teacher_id is None:
            continue
        transmission = transmissions[assignment.transmission_id]
        for stage in transmission.module_stages:
            teacher_stage_counts[assignment.teacher_id][stage] += 1
        teacher_order_counts[assignment.teacher_id][transmission.normalized_order] += 1
    allocated_stage_hours = {
        stage: problem.hours_per_transmission
        * sum(counts[stage] for counts in teacher_stage_counts.values())
        for stage in MODULE_STAGES
    }
    # Governanca: a CH_LETIVA e um teto semanal, entao o estouro e apurado em
    # cada metade do modulo. Docentes Stricto ficam de fora porque a base
    # preserva CH_LETIVA zero e o contrato usa um limite proprio.
    teachers_over_capacity = sum(
        not teacher.is_stricto
        and teacher.allocatable_capacity(problem.hours_per_transmission)
        and problem.hours_per_transmission
        * max(teacher_stage_counts[teacher.id][stage] for stage in MODULE_STAGES)
        > teacher.allocatable_capacity(problem.hours_per_transmission)
        for teacher in problem.teachers
    )

    workbook = Workbook()
    summary = workbook.active
    summary.title = "RESUMO"
    summary.append(("INDICADOR", "VALOR"))
    criterion_label = CRITERION_LABELS.get(problem.criterion, problem.criterion)
    exact_profile_allocations = sum(
        has_exact_profile(
            transmissions[assignment.transmission_id],
            teachers[assignment.teacher_id],
        )
        for assignment in result.assignments
        if assignment.teacher_id is not None
    )
    cluster_profile_allocations = result.allocated_count - exact_profile_allocations
    summary_rows = (
        ("Status do motor", result.status),
        ("Status CP-SAT", result.solver_status),
        ("Critério de elegibilidade", criterion_label),
        ("Alocadas com perfil exato", exact_profile_allocations),
        ("Alocadas por cluster", cluster_profile_allocations),
        ("Transmissões", len(problem.transmissions)),
        ("Alocadas", result.allocated_count),
        ("Não alocadas", result.unassigned_count),
        ("Horas alocadas", result.allocated_count * problem.hours_per_transmission),
        (
            "Horas semanais alocadas - 1ª etapa",
            allocated_stage_hours[MODULE_STAGE_1],
        ),
        (
            "Horas semanais alocadas - 2ª etapa",
            allocated_stage_hours[MODULE_STAGE_2],
        ),
        ("Docentes acima da CH_LETIVA em alguma etapa", teachers_over_capacity),
        ("Docentes ativos", sum(teacher.is_active for teacher in problem.teachers)),
        ("Docentes com alocação", result.used_teacher_count),
        ("Docentes ativos sem alocação", result.zero_active_teacher_count),
        ("Score de ocupação por CH", result.high_capacity_score or 0),
        ("Penalidade de escassez após resgate", result.rescue_scarcity_score or 0),
        ("Tempo do solver (s)", round(result.wall_time_seconds, 3)),
    )
    for row in summary_rows:
        summary.append(row)
    _autosize(summary)

    allocations = workbook.create_sheet("ALOCACOES")
    allocations.append((
        "STATUS", "MOTIVO", "MOTIVO_ALOCACAO", "LINHA_ORIGEM", "CURSO",
        "NOME_CURSO", "CURRÍCULO",
        "COD_DISCIPLINA", "NOME_DISCIPLINA", "PERFIL_DISCIPLINA", "SINERGIA",
        "DIA_AULA", "HORÁRIO", "ORDEM", "CLUSTER", "COORDENADOR",
        "MODELO_CONTRATO", "DOCENTE", "CHAPA",
        "CANDIDATOS_ELEGÍVEIS", "BASE_ELEGIBILIDADE",
    ))
    for assignment in result.assignments:
        transmission = transmissions[assignment.transmission_id]
        teacher = teachers.get(assignment.teacher_id)
        allocations.append((
            assignment.status, assignment.reason, assignment.allocation_reason,
            transmission.excel_row,
            transmission.course, transmission.course_name, transmission.curriculum,
            transmission.discipline_code, transmission.discipline_name,
            transmission.profile_text, transmission.synergy, transmission.day,
            transmission.start_time.strftime("%H:%M") if transmission.start_time else "",
            transmission.order, transmission.cluster, transmission.coordinator,
            contract_model_for(teacher.job_function, True) if teacher else "A DEFINIR",
            teacher.name if teacher else "",
            teacher.badge if teacher else "", assignment.eligible_teacher_count,
            eligibility_basis_for(problem, transmission, teacher),
        ))
    _autosize(allocations)

    loads = workbook.create_sheet("DOCENTES")
    # CH_LETIVA preserva o valor da base; CH_LETIVA_ALOCÁVEL é o teto que a
    # alocação alcança de fato. Folgas e percentuais usam o segundo, porque a
    # sobra que não fecha uma transmissão nunca poderia ter sido ocupada.
    loads_headers = (
        "NOME", "CHAPA", "NM_FUNCAO", "CH_CONTRATADA", "CH_LETIVA",
        "CH_LETIVA_ALOCÁVEL", "GESTOR",
        "STATUS", "PERFIL_DISCIPLINA",
        "QTD_1ª_ORDEM", "QTD_2ª_ORDEM", "QTD_ESTENDIDA", "QTD_TRANSMISSÕES",
        "QTD_DISCIPLINAS_1ª_ETAPA", "CH_ALOCADA_1ª_ETAPA",
        "CH_DISPONÍVEL_1ª_ETAPA", "UTILIZAÇÃO_1ª_ETAPA",
        "QTD_DISCIPLINAS_2ª_ETAPA", "CH_ALOCADA_2ª_ETAPA",
        "CH_DISPONÍVEL_2ª_ETAPA", "UTILIZAÇÃO_2ª_ETAPA",
        "CH_ALOCADA_PICO", "CH_DISPONÍVEL", "UTILIZAÇÃO_PICO",
        "EXCEDE_CH_LETIVA", "SITUACAO_ALOCACAO",
    )
    loads.append(loads_headers)
    # Índice pelo nome: acrescentar uma coluna no meio já deslocou estes
    # números uma vez, e o formato de porcentagem foi parar na coluna errada.
    percent_columns = tuple(
        loads_headers.index(name) + 1
        for name in ("UTILIZAÇÃO_1ª_ETAPA", "UTILIZAÇÃO_2ª_ETAPA", "UTILIZAÇÃO_PICO")
    )
    # Abertura por cargo/regime: acumulada aqui para reaproveitar as cargas por
    # etapa já apuradas por docente, sem reler a aba DOCENTES depois.
    by_job_function: dict[str, dict[tuple[int, str], list[int]]] = {}
    for teacher in sorted(problem.teachers, key=lambda item: item.name):
        raw_used = result.teacher_loads.get(teacher.id, 0)
        order_counts = teacher_order_counts[teacher.id]
        first_count = teacher_stage_counts[teacher.id][MODULE_STAGE_1]
        second_count = teacher_stage_counts[teacher.id][MODULE_STAGE_2]
        # Cada etapa cobre cinco semanas e a CH_LETIVA é o teto semanal, então a
        # carga de cada metade é comparada com ela isoladamente. A ESTENDIDA
        # atravessa o módulo e por isso consome nas duas.
        first_load = first_count * problem.hours_per_transmission
        second_load = second_count * problem.hours_per_transmission
        peak_load = max(first_load, second_load)
        allocatable = teacher.allocatable_capacity(problem.hours_per_transmission)
        if teacher.is_stricto:
            # A base Stricto preserva CH_LETIVA zero e usa um limite especial de
            # disciplinas; por isso seus percentuais permanecem em 0%, a folga
            # fica zerada e o teto semanal não se aplica.
            allocatable = 0
            first_available = second_available = available = 0
            utilization = first_utilization = second_utilization = 0
            exceeds = "NSA"
        else:
            # Denominador é a CH letiva alocável, não a contratada: a fração de
            # hora que não fecha uma transmissão nunca esteve disponível, e
            # deixá-la no divisor subestimava a ocupação de todo mundo.
            first_available = allocatable - first_load
            second_available = allocatable - second_load
            available = allocatable - peak_load
            first_utilization = first_load / allocatable if allocatable else 0
            second_utilization = second_load / allocatable if allocatable else 0
            utilization = peak_load / allocatable if allocatable else 0
            exceeds = "SIM" if peak_load > allocatable else "NAO"
        loads.append((
            teacher.name, teacher.badge, teacher.job_function, teacher.contracted_capacity,
            teacher.teaching_capacity, allocatable, teacher.manager, teacher.status,
            teacher.profile_text,
            order_counts[ORDER_FIRST], order_counts[ORDER_SECOND],
            order_counts[ORDER_EXTENDED],
            raw_used // problem.hours_per_transmission,
            first_count, first_load, first_available, first_utilization,
            second_count, second_load, second_available, second_utilization,
            peak_load, available, utilization, exceeds,
            "ALOCADO" if raw_used else "SEM ALOCACAO",
        ))
        for column in percent_columns:
            loads.cell(loads.max_row, column).number_format = "0.0%"
        # Chave já colapsada: "PROFESSOR  REGENTE" e "PROFESSOR REGENTE" são o
        # mesmo cargo para contract_family, e precisam ser uma linha só aqui.
        regimes = by_job_function.setdefault(
            " ".join(teacher.job_function.split()), {}
        )
        totals = regimes.setdefault(
            (-teacher.contracted_capacity, regime_label_for(teacher)),
            [0, 0, 0, 0, 0, 0],
        )
        totals[0] += 1
        totals[1] += teacher.contracted_capacity
        # Stricto não tem CH letiva alocável, então fica fora do denominador.
        totals[2] += allocatable
        totals[3] += first_load
        totals[4] += second_load
        totals[5] += peak_load
    _autosize(loads)

    by_cargo = workbook.create_sheet("DOCENTES POR CARGO")
    by_cargo.append((
        "CARGO", "REGIME", "HEADCOUNT", "CH_CONTRATADA", "CH_LETIVA_ALOCÁVEL",
        "CH_ALOCADA_1ª_ETAPA", "UTILIZAÇÃO_1ª_ETAPA",
        "CH_ALOCADA_2ª_ETAPA", "UTILIZAÇÃO_2ª_ETAPA",
        "CH_ALOCADA_PICO", "UTILIZAÇÃO_PICO",
    ))

    def append_breakdown_row(cargo: str, regime: str, totals: list[int], bold: bool) -> None:
        headcount, contracted, allocable, first, second, peak = totals
        # Sem CH letiva alocável não há percentual a apurar (contrato Stricto).
        share = (lambda load: load / allocable) if allocable else (lambda load: "NSA")
        by_cargo.append((
            cargo, regime, headcount, contracted, allocable,
            first, share(first), second, share(second), peak, share(peak),
        ))
        row = by_cargo.max_row
        if allocable:
            for column in (7, 9, 11):
                by_cargo.cell(row, column).number_format = "0.0%"
        if bold:
            for cell in by_cargo[row]:
                cell.font = Font(bold=True)

    overall = [0, 0, 0, 0, 0, 0]
    for job_function in sorted(by_job_function):
        regimes = by_job_function[job_function]
        cargo_totals = [sum(values) for values in zip(*regimes.values())]
        append_breakdown_row(job_function, "TOTAL DO CARGO", cargo_totals, True)
        for key in sorted(regimes):
            append_breakdown_row(job_function, key[1], regimes[key], False)
        overall = [total + value for total, value in zip(overall, cargo_totals)]
    append_breakdown_row("TOTAL GERAL", "TOTAL GERAL", overall, True)
    _autosize(by_cargo)
    temporary_xlsx = xlsx_path.with_suffix(xlsx_path.suffix + ".tmp")
    workbook.save(temporary_xlsx)
    workbook.close()
    temporary_xlsx.replace(xlsx_path)

    reasons = Counter(item.reason for item in result.assignments if item.reason)
    allocation_reasons = Counter(
        item.allocation_reason for item in result.assignments if item.allocation_reason
    )
    payload = {
        "source": str(problem.source),
        "status": result.status,
        "solver_status": result.solver_status,
        "eligibility_criterion": problem.criterion,
        "eligibility_criterion_label": criterion_label,
        "exact_profile_allocations": exact_profile_allocations,
        "cluster_profile_allocations": cluster_profile_allocations,
        "transmissions": len(problem.transmissions),
        "allocated": result.allocated_count,
        "unassigned": result.unassigned_count,
        "hours_per_transmission": problem.hours_per_transmission,
        "allocated_hours": result.allocated_count * problem.hours_per_transmission,
        "allocated_stage_hours": {
            "first_stage": allocated_stage_hours[MODULE_STAGE_1],
            "second_stage": allocated_stage_hours[MODULE_STAGE_2],
        },
        "teachers_over_capacity": teachers_over_capacity,
        "unassigned_reasons": dict(reasons),
        "allocation_reasons": dict(allocation_reasons),
        "active_teachers": sum(teacher.is_active for teacher in problem.teachers),
        "used_teachers": result.used_teacher_count,
        "zero_active_teachers": result.zero_active_teacher_count,
        "high_capacity_score": result.high_capacity_score,
        "rescue_scarcity_score": result.rescue_scarcity_score,
        "wall_time_seconds": result.wall_time_seconds,
        "diagnostics": result.diagnostics,
        "decisions": [
            {
                "transmission_id": assignment.transmission_id,
                "source_row": transmissions[assignment.transmission_id].excel_row,
                "curriculum": transmissions[assignment.transmission_id].curriculum,
                "discipline_code": transmissions[assignment.transmission_id].discipline_code,
                "discipline_name": transmissions[assignment.transmission_id].discipline_name,
                "status": assignment.status,
                "unassigned_reason": assignment.reason,
                "allocation_reason": assignment.allocation_reason,
                "eligible_teacher_count": assignment.eligible_teacher_count,
                "eligibility_basis": eligibility_basis_for(
                    problem,
                    transmissions[assignment.transmission_id],
                    teachers.get(assignment.teacher_id),
                ),
                "contract_model": (
                    contract_model_for(
                        teachers[assignment.teacher_id].job_function,
                        True,
                    )
                    if assignment.teacher_id is not None
                    else "A DEFINIR"
                ),
                "teacher_id": assignment.teacher_id,
                "teacher_badge": (
                    teachers[assignment.teacher_id].badge
                    if assignment.teacher_id is not None
                    else None
                ),
                "teacher_name": (
                    teachers[assignment.teacher_id].name
                    if assignment.teacher_id is not None
                    else None
                ),
            }
            for assignment in result.assignments
        ],
    }
    temporary_json = json_path.with_suffix(json_path.suffix + ".tmp")
    temporary_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_json.replace(json_path)
    return xlsx_path, json_path
