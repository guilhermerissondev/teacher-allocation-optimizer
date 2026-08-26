from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:  # pragma: no cover - apenas para tipagem estática
    from .domain import Teacher, Transmission


CRITERION_PROFILE = "PERFIL_EXATO"
CRITERION_CLUSTER_PREFERRED = "CLUSTER_PREFERENCIAL"
CRITERION_CLUSTER_PURE = "CLUSTER_PURO"

ELIGIBILITY_CRITERIA = (
    CRITERION_PROFILE,
    CRITERION_CLUSTER_PREFERRED,
    CRITERION_CLUSTER_PURE,
)

CLUSTER_CRITERIA = frozenset({CRITERION_CLUSTER_PREFERRED, CRITERION_CLUSTER_PURE})

CRITERION_LABELS = {
    CRITERION_PROFILE: "Perfil da disciplina",
    CRITERION_CLUSTER_PREFERRED: "Cluster com perfil preferencial",
    CRITERION_CLUSTER_PURE: "Cluster puro",
}


def normalize_criterion(value: Any) -> str:
    """Aceita o critério em qualquer caixa e recusa valores fora do contrato."""
    text = " ".join(str(value or "").strip().upper().split()).replace(" ", "_")
    if not text:
        return CRITERION_PROFILE
    if text not in ELIGIBILITY_CRITERIA:
        raise ValueError(
            f"Critério de elegibilidade não suportado: {value!r}; "
            f"esperado {', '.join(ELIGIBILITY_CRITERIA)}."
        )
    return text


def uses_cluster(criterion: Any) -> bool:
    return normalize_criterion(criterion) in CLUSTER_CRITERIA


def cluster_profile_map(
    transmissions: Iterable["Transmission"],
) -> dict[str, frozenset[str]]:
    """União dos perfis das ofertas de cada cluster nomeado.

    Ofertas sem CLUSTER preenchido não formam grupo: agregá-las produziria um
    conjunto sem significado pedagógico, então elas permanecem restritas ao
    próprio perfil mesmo nos métodos por cluster.
    """
    profiles: dict[str, set[str]] = defaultdict(set)
    for transmission in transmissions:
        cluster = transmission.cluster.strip()
        if not cluster:
            continue
        profiles[cluster].update(transmission.profiles)
    return {cluster: frozenset(values) for cluster, values in profiles.items()}


def eligible_profiles_for(
    transmission: "Transmission",
    criterion: Any,
    cluster_profiles: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Conjunto de perfis que torna um docente candidato a esta oferta."""
    if not uses_cluster(criterion):
        return transmission.profiles
    cluster = transmission.cluster.strip()
    if not cluster:
        return transmission.profiles
    return cluster_profiles.get(cluster, transmission.profiles)


def has_exact_profile(transmission: "Transmission", teacher: "Teacher") -> bool:
    """Aderência exata de perfil, independente do critério vigente."""
    return bool(transmission.profiles.intersection(teacher.profiles))


def falls_back_to_profile(transmission: "Transmission", criterion: Any) -> bool:
    """Indica oferta que, no método por cluster, seguiu pelo perfil exato."""
    return uses_cluster(criterion) and not transmission.cluster.strip()
