from __future__ import annotations

from .criteria import (
    cluster_profile_map,
    declares_teacher_clusters,
    normalize_criterion,
    teacher_meets_offer,
)
from .domain import CONTRACT_UNKNOWN, Problem, Teacher, Transmission


def is_teacher_eligible(
    problem: Problem,
    transmission: Transmission,
    teacher: Teacher,
    criterion: str | None = None,
    cluster_profiles: dict[str, frozenset[str]] | None = None,
    cluster_reference: bool | None = None,
) -> bool:
    """Candidatura básica sob o critério vigente.

    Só a aderência muda entre os critérios. Atividade, função reconhecida,
    capacidade e agenda continuam obrigatórias nos três métodos.
    """
    criterion = normalize_criterion(
        problem.criterion if criterion is None else criterion
    )
    if cluster_profiles is None:
        cluster_profiles = cluster_profile_map(problem.transmissions)
    if cluster_reference is None:
        cluster_reference = declares_teacher_clusters(problem.teachers)
    return (
        transmission.slot is not None
        and teacher.is_active
        and teacher.contract_family != CONTRACT_UNKNOWN
        and teacher.allocation_capacity(problem.hours_per_transmission)
        >= problem.hours_per_transmission
        and teacher_meets_offer(
            transmission, teacher, criterion, cluster_profiles, cluster_reference
        )
    )


def build_eligibility(
    problem: Problem,
    criterion: str | None = None,
) -> dict[int, list[int]]:
    criterion = normalize_criterion(
        problem.criterion if criterion is None else criterion
    )
    cluster_profiles = cluster_profile_map(problem.transmissions)
    cluster_reference = declares_teacher_clusters(problem.teachers)
    return {
        transmission.id: [
            teacher.id
            for teacher in problem.teachers
            if is_teacher_eligible(
                problem,
                transmission,
                teacher,
                criterion,
                cluster_profiles,
                cluster_reference,
            )
        ]
        for transmission in problem.transmissions
    }
