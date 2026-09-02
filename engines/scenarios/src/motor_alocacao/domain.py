from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from pathlib import Path

from .criteria import CRITERION_PROFILE, normalize_criterion


CONTRACT_EAD_POOL = "EAD_POOL"
CONTRACT_STRICTO = "STRICTO"
CONTRACT_UNKNOWN = "UNKNOWN"
STRICTO_MAX_DISCIPLINES_PER_MODULE = 2
MODULE_STAGE_1 = "PRIMEIRA_ETAPA"
MODULE_STAGE_2 = "SEGUNDA_ETAPA"
MODULE_STAGES = (MODULE_STAGE_1, MODULE_STAGE_2)

ORDER_FIRST = "1ª"
ORDER_SECOND = "2ª"
ORDER_EXTENDED = "ESTENDIDA"
MODULE_ORDERS = (ORDER_FIRST, ORDER_SECOND, ORDER_EXTENDED)

_ORDER_STAGES = {
    ORDER_FIRST: (MODULE_STAGE_1,),
    ORDER_SECOND: (MODULE_STAGE_2,),
    ORDER_EXTENDED: MODULE_STAGES,
}


def normalize_order(order: str) -> str:
    """Devolve a ORDEM canonica da disciplina."""
    normalized = " ".join(order.strip().upper().split())
    if normalized not in _ORDER_STAGES:
        raise ValueError(
            f"ORDEM não suportada: {order!r}; esperado 1ª, 2ª ou ESTENDIDA."
        )
    return normalized


def module_stages_for_order(order: str) -> tuple[str, ...]:
    """Retorna as metades do módulo em que a disciplina consome carga."""
    return _ORDER_STAGES[normalize_order(order)]


@dataclass(frozen=True)
class Teacher:
    id: int
    name: str
    badge: str
    job_function: str
    contracted_capacity: int
    teaching_capacity: int
    manager: str
    status: str
    profiles: frozenset[str]
    profile_text: str
    # Clusters declarados para o docente. Quando a base os informa, eles
    # passam a ser a referencia dos metodos por cluster, no lugar da uniao de
    # perfis das ofertas — que dependia da taxonomia de perfil estar coerente.
    clusters: frozenset[str] = frozenset()
    cluster_text: str = ""

    @property
    def is_active(self) -> bool:
        return self.status.strip().upper() == "ATIVO"

    @property
    def is_stricto(self) -> bool:
        return self.contract_family == CONTRACT_STRICTO

    @property
    def contract_family(self) -> str:
        normalized = " ".join(self.job_function.strip().upper().split())
        if normalized == "PROFESSOR DE ENSINO SUPERIOR PRESENCIAL":
            return CONTRACT_STRICTO
        if normalized in {
            "PROFESSOR DE ENSINO SUPERIOR EAD",
            "PROFESSOR REGENTE",
        }:
            return CONTRACT_EAD_POOL
        return CONTRACT_UNKNOWN

    def allocation_capacity(self, hours_per_transmission: int) -> int:
        """Capacidade usada pelo solver sem alterar as cargas originais da base."""
        if self.is_stricto:
            return hours_per_transmission * STRICTO_MAX_DISCIPLINES_PER_MODULE
        return self.teaching_capacity

    def allocatable_capacity(self, hours_per_transmission: int) -> int:
        """CH letiva que cabe em transmissões inteiras.

        A alocação acontece em blocos de hours_per_transmission, então a sobra
        que não fecha um bloco não tem como ser usada: 9h de CH letiva com
        blocos de 2h alocam no máximo 8h, e a hora restante fica ociosa por
        construção. Medir utilização contra as 9h originais faz o docente
        parecer menos usado do que o teto real permite.

        O solver não muda com isso — a restrição de inteiros já produzia o
        mesmo piso —, mas o denominador dos relatórios sim.
        """
        if hours_per_transmission <= 0:
            return self.teaching_capacity
        return (self.teaching_capacity // hours_per_transmission) * hours_per_transmission


@dataclass(frozen=True)
class Transmission:
    id: int
    excel_row: int
    course: str
    course_name: str
    curriculum: str
    discipline_code: str
    discipline_name: str
    profiles: frozenset[str]
    profile_text: str
    synergy: str
    day: str
    start_time: time | None
    order: str
    cluster: str
    coordinator: str

    @property
    def slot(self) -> tuple[str, str] | None:
        if not self.day or self.day == "NSA" or self.start_time is None:
            return None
        return self.day, self.start_time.strftime("%H:%M")

    @property
    def module_stages(self) -> tuple[str, ...]:
        return module_stages_for_order(self.order)

    @property
    def normalized_order(self) -> str:
        return normalize_order(self.order)

@dataclass(frozen=True)
class Problem:
    source: Path
    teachers: tuple[Teacher, ...]
    transmissions: tuple[Transmission, ...]
    hours_per_transmission: int = 2
    criterion: str = CRITERION_PROFILE

    def __post_init__(self) -> None:
        # Normaliza uma única vez para que solver, auditoria e relatório leiam
        # exatamente o mesmo critério a partir do problema carregado.
        object.__setattr__(self, "criterion", normalize_criterion(self.criterion))


@dataclass(frozen=True)
class Assignment:
    transmission_id: int
    teacher_id: int | None
    status: str
    reason: str
    eligible_teacher_count: int
    allocation_reason: str = ""


@dataclass
class AllocationResult:
    status: str
    solver_status: str
    assignments: list[Assignment]
    teacher_loads: dict[int, int]
    objective_unassigned: int
    used_teacher_count: int
    zero_active_teacher_count: int
    high_capacity_score: int | None
    rescue_scarcity_score: int | None
    wall_time_seconds: float
    diagnostics: dict[str, object] = field(default_factory=dict)
    teacher_stage_loads: dict[int, dict[str, int]] = field(default_factory=dict)

    @property
    def allocated_count(self) -> int:
        return sum(item.teacher_id is not None for item in self.assignments)

    @property
    def unassigned_count(self) -> int:
        return len(self.assignments) - self.allocated_count
