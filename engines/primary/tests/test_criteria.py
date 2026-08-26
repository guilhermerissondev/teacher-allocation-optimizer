from __future__ import annotations

import sys
import unittest
from datetime import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from motor_alocacao import (  # noqa: E402
    CRITERION_CLUSTER_PREFERRED,
    CRITERION_CLUSTER_PURE,
    CRITERION_PROFILE,
    Problem,
    Teacher,
    Transmission,
    audit_allocation,
    build_eligibility,
    normalize_criterion,
    solve_allocation,
)


def teacher(identifier: int, profiles, capacity: int = 10) -> Teacher:
    return Teacher(
        identifier, f"Docente {identifier}", f"{identifier:012d}",
        "PROFESSOR REGENTE", 40, capacity, "Gestor", "ATIVO",
        frozenset(profiles), ", ".join(profiles),
    )


def transmission(
    identifier: int, profiles, cluster="GESTAO", day="SEGUNDA", start=time(19, 0),
) -> Transmission:
    return Transmission(
        identifier, identifier + 2, "C", "Curso", "CURR", f"D{identifier}",
        "Disciplina", frozenset(profiles), ", ".join(profiles), "Curso único",
        day, start, "1ª", cluster, "Coordenador",
    )


class CriterionContractTests(unittest.TestCase):
    def test_normalizes_case_and_rejects_unknown_values(self):
        self.assertEqual(CRITERION_PROFILE, normalize_criterion("perfil_exato"))
        self.assertEqual(CRITERION_PROFILE, normalize_criterion(None))
        self.assertEqual(CRITERION_CLUSTER_PURE, normalize_criterion("cluster puro"))
        with self.assertRaises(ValueError):
            normalize_criterion("CLUSTER_TOTAL")

    def test_problem_normalizes_its_criterion(self):
        problem = Problem(
            Path("t.xlsx"), (teacher(0, ["a"]),), (transmission(0, ["a"]),),
            criterion="cluster_preferencial",
        )
        self.assertEqual(CRITERION_CLUSTER_PREFERRED, problem.criterion)


class EligibilityByCriterionTests(unittest.TestCase):
    def setUp(self):
        # O perfil "b" so pertence ao cluster GESTAO por causa da oferta 1.
        self.teachers = (teacher(0, ["a"]), teacher(1, ["b"]))
        self.offers = (
            transmission(0, ["a"]),
            transmission(1, ["b"], start=time(21, 0)),
        )

    def _eligibility(self, criterion):
        problem = Problem(
            Path("t.xlsx"), self.teachers, self.offers, criterion=criterion
        )
        return build_eligibility(problem)

    def test_profile_criterion_requires_exact_intersection(self):
        self.assertEqual({0: [0], 1: [1]}, self._eligibility(CRITERION_PROFILE))

    def test_cluster_criterion_is_a_superset_of_the_profile_criterion(self):
        exact = self._eligibility(CRITERION_PROFILE)
        for criterion in (CRITERION_CLUSTER_PREFERRED, CRITERION_CLUSTER_PURE):
            widened = self._eligibility(criterion)
            for offer_id, candidates in exact.items():
                self.assertTrue(
                    set(candidates).issubset(set(widened[offer_id])),
                    f"{criterion} perdeu candidatos exatos na oferta {offer_id}",
                )
            self.assertEqual({0: [0, 1], 1: [0, 1]}, widened)

    def test_blank_cluster_falls_back_to_the_exact_profile(self):
        offers = (
            transmission(0, ["a"], cluster=""),
            transmission(1, ["b"], cluster="", start=time(21, 0)),
        )
        problem = Problem(
            Path("t.xlsx"), self.teachers, offers,
            criterion=CRITERION_CLUSTER_PURE,
        )
        # Sem cluster nao ha grupo: cada oferta continua restrita ao seu perfil.
        self.assertEqual({0: [0], 1: [1]}, build_eligibility(problem))


class CriterionSolverTests(unittest.TestCase):
    def _solve(self, criterion, teachers, offers):
        problem = Problem(Path("t.xlsx"), teachers, offers, criterion=criterion)
        return problem, solve_allocation(problem, workers=2)

    def test_cluster_recovers_an_offer_that_profile_cannot_cover(self):
        teachers = (teacher(0, ["a"]),)
        offers = (transmission(0, ["a"]), transmission(1, ["b"], start=time(21, 0)))

        _, exact = self._solve(CRITERION_PROFILE, teachers, offers)
        _, widened = self._solve(CRITERION_CLUSTER_PURE, teachers, offers)

        self.assertEqual(1, exact.allocated_count)
        self.assertEqual(2, widened.allocated_count)

    def test_preferential_and_pure_share_every_business_optimum(self):
        teachers = (teacher(0, ["b"]), teacher(1, ["a"]))
        offers = (transmission(0, ["a"]), transmission(1, ["b"], day="NSA"))

        _, preferred = self._solve(CRITERION_CLUSTER_PREFERRED, teachers, offers)
        _, pure = self._solve(CRITERION_CLUSTER_PURE, teachers, offers)

        self.assertEqual(pure.allocated_count, preferred.allocated_count)
        self.assertEqual(pure.used_teacher_count, preferred.used_teacher_count)
        self.assertEqual(pure.objective_unassigned, preferred.objective_unassigned)
        self.assertEqual(pure.high_capacity_score, preferred.high_capacity_score)

    def test_preferential_breaks_the_tie_towards_the_exact_profile(self):
        # Empate real: mesma CH e mesma cobertura. So a aderencia os separa.
        teachers = (teacher(0, ["b"]), teacher(1, ["a"]))
        offers = (transmission(0, ["a"]), transmission(1, ["b"], day="NSA"))

        _, preferred = self._solve(CRITERION_CLUSTER_PREFERRED, teachers, offers)
        _, pure = self._solve(CRITERION_CLUSTER_PURE, teachers, offers)

        self.assertEqual(1, preferred.diagnostics["exact_profile_assignments"])
        self.assertEqual(0, pure.diagnostics["exact_profile_assignments"])
        self.assertTrue(preferred.diagnostics["profile_adherence_phase_applied"])
        self.assertFalse(pure.diagnostics["profile_adherence_phase_applied"])

    def test_profile_criterion_keeps_the_previous_phase_budget(self):
        teachers = (teacher(0, ["a"]),)
        offers = (transmission(0, ["a"]),)
        _, result = self._solve(CRITERION_PROFILE, teachers, offers)

        self.assertFalse(result.diagnostics["profile_adherence_phase_applied"])
        self.assertIsNone(result.diagnostics["switch_4_profile_adherence_status"])
        self.assertEqual(CRITERION_PROFILE, result.diagnostics["eligibility_criterion"])


class CriterionAuditTests(unittest.TestCase):
    def test_audit_approves_a_cluster_allocation_under_a_cluster_criterion(self):
        teachers = (teacher(0, ["a"]),)
        offers = (transmission(0, ["a"]), transmission(1, ["b"], start=time(21, 0)))
        problem = Problem(
            Path("t.xlsx"), teachers, offers, criterion=CRITERION_CLUSTER_PURE
        )
        result = solve_allocation(problem, workers=2)
        audit = audit_allocation(problem, result)

        self.assertEqual("APROVADO", audit.status)
        self.assertEqual(1, audit.checks["cluster_profile_allocations"])
        self.assertEqual(CRITERION_CLUSTER_PURE, audit.checks["eligibility_criterion"])

    def test_audit_rejects_a_cluster_allocation_under_the_profile_criterion(self):
        # Nao-regressao: a regra historica continua reprovando o que sempre
        # reprovou, mesmo depois de a auditoria virar sensivel ao criterio.
        teachers = (teacher(0, ["a"]),)
        offers = (transmission(0, ["a"]), transmission(1, ["b"], start=time(21, 0)))
        cluster_problem = Problem(
            Path("t.xlsx"), teachers, offers, criterion=CRITERION_CLUSTER_PURE
        )
        result = solve_allocation(cluster_problem, workers=2)

        strict_problem = Problem(
            Path("t.xlsx"), teachers, offers, criterion=CRITERION_PROFILE
        )
        audit = audit_allocation(strict_problem, result, criterion=CRITERION_PROFILE)

        self.assertEqual("REPROVADO", audit.status)
        self.assertIn("PERFIL_INCOMPATIVEL", {issue.code for issue in audit.issues})

    def test_audit_flags_a_criterion_that_differs_from_the_solver(self):
        teachers = (teacher(0, ["a"]),)
        offers = (transmission(0, ["a"]),)
        problem = Problem(
            Path("t.xlsx"), teachers, offers, criterion=CRITERION_PROFILE
        )
        result = solve_allocation(problem, workers=2)
        result.diagnostics["eligibility_criterion"] = CRITERION_CLUSTER_PURE

        audit = audit_allocation(problem, result, criterion=CRITERION_PROFILE)

        self.assertEqual("REPROVADO", audit.status)
        self.assertIn("CRITERIO_DIVERGENTE", {issue.code for issue in audit.issues})


if __name__ == "__main__":
    unittest.main()
