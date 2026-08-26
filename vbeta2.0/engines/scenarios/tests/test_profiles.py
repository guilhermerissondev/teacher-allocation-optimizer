from __future__ import annotations

import sys
import unittest
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from motor_alocacao import (  # noqa: E402
    PROFILE_ACCEPTED_MARGIN,
    PROFILE_FAST,
    PROFILE_FULL_PROOF,
    PROFILE_PROVEN_COVERAGE,
    SOLVER_PROFILES,
    STATUS_FEASIBLE,
    STATUS_OPTIMAL,
    STATUS_PROVEN_COVERAGE,
    STATUS_WITH_MARGIN,
    USABLE_SOLVER_STATUSES,
    Problem,
    Teacher,
    Transmission,
    audit_allocation,
    is_promotable,
    is_usable_status,
    normalize_profile,
    profile_policy,
    solve_allocation,
    status_meets,
)


def teacher(identifier: int, profiles=("a",), capacity: int = 10) -> Teacher:
    return Teacher(
        identifier, f"Docente {identifier}", f"{identifier:012d}",
        "PROFESSOR REGENTE", 40, capacity, "Gestor", "ATIVO",
        frozenset(profiles), ", ".join(profiles),
    )


def transmission(identifier: int, profiles=("a",), start=time(19, 0)) -> Transmission:
    return Transmission(
        identifier, identifier + 2, "C", "Curso", "CURR", f"D{identifier}",
        "Disciplina", frozenset(profiles), ", ".join(profiles), "Curso único",
        "SEGUNDA", start, "1ª", "GESTAO", "Coordenador",
    )


class ProfileContractTests(unittest.TestCase):
    def test_normalizes_and_refuses_unknown(self):
        self.assertEqual(PROFILE_FULL_PROOF, normalize_profile("prova completa"))
        self.assertEqual(PROFILE_FULL_PROOF, normalize_profile(None))
        self.assertEqual(PROFILE_FAST, normalize_profile("exploracao_rapida".upper()))
        with self.assertRaises(ValueError):
            normalize_profile("QUALQUER_COISA")

    def test_only_full_proof_is_promotable(self):
        promovíveis = [name for name in SOLVER_PROFILES if is_promotable(name)]
        self.assertEqual([PROFILE_FULL_PROOF], promovíveis)

    def test_full_proof_has_no_cap_and_no_margin(self):
        policy = profile_policy(PROFILE_FULL_PROOF)
        self.assertTrue(policy.prove_coverage)
        self.assertTrue(policy.prove_tiebreak)
        self.assertEqual(0, policy.coverage_gap_offers)
        self.assertIsNone(policy.deterministic_cap)
        self.assertEqual(STATUS_OPTIMAL, policy.required_status)

    def test_proven_coverage_proves_only_the_first_phase(self):
        policy = profile_policy(PROFILE_PROVEN_COVERAGE)
        self.assertTrue(policy.prove_coverage)
        self.assertFalse(policy.prove_tiebreak)
        self.assertIsNotNone(policy.deterministic_cap)
        self.assertEqual(STATUS_PROVEN_COVERAGE, policy.required_status)

    def test_margin_is_expressed_in_offers_and_can_be_set(self):
        self.assertEqual(2, profile_policy(PROFILE_ACCEPTED_MARGIN).coverage_gap_offers)
        self.assertEqual(7, profile_policy(PROFILE_ACCEPTED_MARGIN, 7).coverage_gap_offers)
        for invalido in (0, -1, True, 1.5):
            with self.subTest(valor=invalido):
                with self.assertRaises(ValueError):
                    profile_policy(PROFILE_ACCEPTED_MARGIN, invalido)

    def test_margin_is_ignored_by_profiles_that_do_not_use_it(self):
        # Informar margem num perfil sem margem não deve alterá-lo.
        self.assertEqual(0, profile_policy(PROFILE_FULL_PROOF, 9).coverage_gap_offers)


class StatusStrengthTests(unittest.TestCase):
    """A garantia entregue precisa ser comparável com a prometida."""

    def test_stronger_status_satisfies_weaker_requirement(self):
        self.assertTrue(status_meets(STATUS_OPTIMAL, STATUS_PROVEN_COVERAGE))
        self.assertTrue(status_meets(STATUS_OPTIMAL, STATUS_WITH_MARGIN))
        self.assertTrue(status_meets(STATUS_PROVEN_COVERAGE, STATUS_FEASIBLE))

    def test_weaker_status_never_satisfies_stronger_requirement(self):
        self.assertFalse(status_meets(STATUS_FEASIBLE, STATUS_OPTIMAL))
        self.assertFalse(status_meets(STATUS_WITH_MARGIN, STATUS_PROVEN_COVERAGE))
        self.assertFalse(status_meets(STATUS_PROVEN_COVERAGE, STATUS_OPTIMAL))

    def test_unknown_status_never_satisfies_anything(self):
        self.assertFalse(status_meets("INVENTADO", STATUS_FEASIBLE))


class ProfileSolverTests(unittest.TestCase):
    def _problem(self, profile):
        return Problem(
            Path("t.xlsx"),
            (teacher(0), teacher(1)),
            (transmission(0), transmission(1, start=time(21, 0))),
        ), profile

    def test_full_proof_reports_optimal_and_publishes_the_profile(self):
        problem, profile = self._problem(PROFILE_FULL_PROOF)
        result = solve_allocation(problem, workers=2, profile=profile)

        self.assertEqual(STATUS_OPTIMAL, result.solver_status)
        self.assertEqual(PROFILE_FULL_PROOF, result.diagnostics["execution_profile"])
        self.assertTrue(result.diagnostics["coverage_proven"])
        self.assertTrue(result.diagnostics["tiebreak_proven"])
        self.assertTrue(result.diagnostics["profile_promotable"])

    def test_every_profile_keeps_the_solution_auditable(self):
        # O perfil governa a garantia, nunca as restrições acadêmicas: a
        # auditoria precisa aprovar em todos eles.
        for profile in SOLVER_PROFILES:
            with self.subTest(profile=profile):
                problem, _ = self._problem(profile)
                result = solve_allocation(problem, workers=2, profile=profile)
                self.assertEqual("APROVADO", audit_allocation(problem, result).status)

    def test_profile_is_recorded_even_without_solution(self):
        # Oferta sem candidato: mesmo sem alocar nada, o perfil fica registrado.
        problem = Problem(
            Path("t.xlsx"), (teacher(0, ["a"]),), (transmission(0, ["z"]),),
        )
        result = solve_allocation(problem, workers=2, profile=PROFILE_FAST)
        self.assertEqual(PROFILE_FAST, result.diagnostics["execution_profile"])

    def test_every_promised_status_counts_as_a_usable_result(self):
        # Regressão: o pipeline reprovava COBERTURA_PROVADA e OTIMO_COM_MARGEM
        # como "sem solução utilizável", ainda que sejam garantias mais fortes
        # que FEASIBLE, que ele aceitava. Todo status que um perfil pode
        # prometer precisa ser utilizável.
        for profile in SOLVER_PROFILES:
            with self.subTest(profile=profile):
                promised = profile_policy(
                    profile,
                    2 if profile == PROFILE_ACCEPTED_MARGIN else None,
                ).required_status
                self.assertTrue(is_usable_status(promised), promised)

    def test_usable_statuses_are_exactly_the_ranked_ones(self):
        # A força relativa e a usabilidade descrevem o mesmo vocabulário: um
        # status classificável por status_meets é, por definição, publicável.
        self.assertEqual(
            {
                STATUS_FEASIBLE,
                STATUS_WITH_MARGIN,
                STATUS_PROVEN_COVERAGE,
                STATUS_OPTIMAL,
            },
            set(USABLE_SOLVER_STATUSES),
        )

    def test_solver_failures_are_not_usable(self):
        # Os nomes que o CP-SAT devolve quando não há solução nunca podem
        # atravessar o portão do pipeline.
        for status in ("INFEASIBLE", "MODEL_INVALID", "UNKNOWN", "SEM_SOLUCAO", ""):
            with self.subTest(status=status):
                self.assertFalse(is_usable_status(status))

    def test_unknown_profile_is_refused_by_the_solver(self):
        problem, _ = self._problem(PROFILE_FULL_PROOF)
        with self.assertRaises(ValueError):
            solve_allocation(problem, workers=2, profile="TURBO")


if __name__ == "__main__":
    unittest.main()
