from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any, Iterable

from .normalization import normalize

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


def declares_teacher_clusters(teachers: Iterable["Teacher"]) -> bool:
    """A base informa o cluster do docente?

    Quando informa, o cluster passa a ser a referencia dos metodos por cluster.
    Bases anteriores a esse contrato nao trazem a coluna e seguem pela uniao de
    perfis das ofertas, preservando o resultado que ja produziam.
    """
    return any(teacher.clusters for teacher in teachers)


def teacher_meets_offer(
    transmission: "Transmission",
    teacher: "Teacher",
    criterion: Any,
    cluster_profiles: dict[str, frozenset[str]],
    cluster_reference: bool = False,
) -> bool:
    """Aderencia do docente a oferta sob o criterio vigente.

    Nos metodos por cluster com o cluster declarado nos dois lados, a
    comparacao e direta entre clusters: o perfil deixa de mediar a candidatura,
    que era o ponto fragil quando a taxonomia de perfil estava incompleta.
    """
    if cluster_reference and uses_cluster(criterion):
        cluster = normalize(transmission.cluster)
        if cluster:
            return cluster in teacher.clusters
        # Oferta sem cluster nao forma grupo e segue restrita ao proprio perfil.
        return has_exact_profile(transmission, teacher)
    accepted = eligible_profiles_for(transmission, criterion, cluster_profiles)
    return bool(accepted.intersection(teacher.profiles))


def eligibility_basis(
    transmission: "Transmission",
    teacher: "Teacher",
    criterion: Any,
    cluster_reference: bool = False,
) -> str:
    """Como a candidatura foi aceita, para o relatorio explicar a decisao."""
    if has_exact_profile(transmission, teacher):
        return "PERFIL_EXATO"
    if not uses_cluster(criterion):
        return "INDEFINIDA"
    if cluster_reference and normalize(transmission.cluster):
        return "CLUSTER_DECLARADO"
    return "CLUSTER"


def falls_back_to_profile(transmission: "Transmission", criterion: Any) -> bool:
    """Indica oferta que, no método por cluster, seguiu pelo perfil exato."""
    return uses_cluster(criterion) and not transmission.cluster.strip()
