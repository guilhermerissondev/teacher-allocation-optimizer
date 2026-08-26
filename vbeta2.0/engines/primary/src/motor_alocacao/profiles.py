from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PROFILE_FULL_PROOF = "PROVA_COMPLETA"
PROFILE_PROVEN_COVERAGE = "COBERTURA_PROVADA"
PROFILE_ACCEPTED_MARGIN = "MARGEM_ACEITA"
PROFILE_FAST = "EXPLORACAO_RAPIDA"

SOLVER_PROFILES = (
    PROFILE_FULL_PROOF,
    PROFILE_PROVEN_COVERAGE,
    PROFILE_ACCEPTED_MARGIN,
    PROFILE_FAST,
)

PROFILE_LABELS = {
    PROFILE_FULL_PROOF: "Prova completa",
    PROFILE_PROVEN_COVERAGE: "Cobertura provada",
    PROFILE_ACCEPTED_MARGIN: "Margem aceita",
    PROFILE_FAST: "Exploração rápida",
}

# Status publicados pelo solver, do mais forte para o mais fraco.
STATUS_OPTIMAL = "OPTIMAL"
STATUS_PROVEN_COVERAGE = "COBERTURA_PROVADA"
STATUS_WITH_MARGIN = "OTIMO_COM_MARGEM"
STATUS_FEASIBLE = "FEASIBLE"

_STATUS_STRENGTH = {
    STATUS_FEASIBLE: 0,
    STATUS_WITH_MARGIN: 1,
    STATUS_PROVEN_COVERAGE: 2,
    STATUS_OPTIMAL: 3,
}

# Todo status que o solver publica quando entrega uma alocação utilizável. O
# pipeline compara contra este conjunto, e não contra uma lista literal: um
# status novo em `_STATUS_STRENGTH` passa a ser aceito automaticamente, sem
# reprovar rodadas boas por vocabulário desatualizado.
USABLE_SOLVER_STATUSES = frozenset(_STATUS_STRENGTH)


@dataclass(frozen=True)
class ProfilePolicy:
    """Traduz um perfil de negócio em parâmetros de parada do solver.

    O perfil governa apenas *quanta garantia* a rodada oferece. Ele nunca
    altera as restrições acadêmicas nem o que a auditoria reconfere.
    """

    name: str
    prove_coverage: bool
    prove_tiebreak: bool
    coverage_gap_offers: int
    deterministic_cap: float | None
    required_status: str
    promotable: bool

    @property
    def label(self) -> str:
        return PROFILE_LABELS[self.name]


# O teto determinístico é reprodutível entre máquinas, ao contrário do tempo de
# relógio. Isso importa porque a canonicalização depende de o modelo, e não a
# busca, decidir a solução — um teto de relógio reintroduziria variação.
_POLICIES = {
    PROFILE_FULL_PROOF: ProfilePolicy(
        name=PROFILE_FULL_PROOF,
        prove_coverage=True,
        prove_tiebreak=True,
        coverage_gap_offers=0,
        deterministic_cap=None,
        required_status=STATUS_OPTIMAL,
        promotable=True,
    ),
    PROFILE_PROVEN_COVERAGE: ProfilePolicy(
        name=PROFILE_PROVEN_COVERAGE,
        prove_coverage=True,
        prove_tiebreak=False,
        coverage_gap_offers=0,
        deterministic_cap=60.0,
        required_status=STATUS_PROVEN_COVERAGE,
        promotable=False,
    ),
    PROFILE_ACCEPTED_MARGIN: ProfilePolicy(
        name=PROFILE_ACCEPTED_MARGIN,
        prove_coverage=False,
        prove_tiebreak=False,
        coverage_gap_offers=2,
        deterministic_cap=60.0,
        required_status=STATUS_WITH_MARGIN,
        promotable=False,
    ),
    PROFILE_FAST: ProfilePolicy(
        name=PROFILE_FAST,
        prove_coverage=False,
        prove_tiebreak=False,
        coverage_gap_offers=0,
        deterministic_cap=15.0,
        required_status=STATUS_FEASIBLE,
        promotable=False,
    ),
}


def normalize_profile(value: Any) -> str:
    """Aceita o perfil em qualquer caixa e recusa valores fora do contrato."""
    text = " ".join(str(value or "").strip().upper().split()).replace(" ", "_")
    if not text:
        return PROFILE_FULL_PROOF
    if text not in SOLVER_PROFILES:
        raise ValueError(
            f"Perfil de execução não suportado: {value!r}; "
            f"esperado {', '.join(SOLVER_PROFILES)}."
        )
    return text


def profile_policy(value: Any, gap_offers: int | None = None) -> ProfilePolicy:
    """Política do perfil, com a margem sobrescrita quando o usuário a define."""
    policy = _POLICIES[normalize_profile(value)]
    if gap_offers is None or policy.name != PROFILE_ACCEPTED_MARGIN:
        return policy
    if not isinstance(gap_offers, int) or isinstance(gap_offers, bool) or gap_offers < 1:
        raise ValueError("A margem aceita deve ser um inteiro de ofertas maior que zero.")
    return ProfilePolicy(
        name=policy.name,
        prove_coverage=policy.prove_coverage,
        prove_tiebreak=policy.prove_tiebreak,
        coverage_gap_offers=gap_offers,
        deterministic_cap=policy.deterministic_cap,
        required_status=policy.required_status,
        promotable=policy.promotable,
    )


def is_usable_status(achieved: Any) -> bool:
    """A rodada produziu uma alocação publicável?

    Só distingue "houve solução" de "não houve". A força da garantia é
    responsabilidade de :func:`status_meets`.
    """
    return str(achieved) in USABLE_SOLVER_STATUSES


def status_meets(achieved: str, required: str) -> bool:
    """A rodada entregou uma garantia ao menos tão forte quanto a prometida?"""
    return _STATUS_STRENGTH.get(achieved, -1) >= _STATUS_STRENGTH.get(required, 99)


def is_promotable(profile: Any) -> bool:
    """Somente prova completa pode virar referência oficial do módulo."""
    return _POLICIES[normalize_profile(profile)].promotable
