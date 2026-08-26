from __future__ import annotations

from collections import defaultdict
from time import perf_counter

from ortools.sat.python import cp_model

from .domain import (
    MODULE_STAGES,
    STRICTO_MAX_DISCIPLINES_PER_MODULE,
    AllocationResult,
    Assignment,
    Problem,
)
from .criteria import (
    CRITERION_CLUSTER_PREFERRED,
    has_exact_profile,
    normalize_criterion,
    uses_cluster,
)
from .eligibility import build_eligibility
from .grasp import build_grasp_hint
from .profiles import (
    PROFILE_FULL_PROOF,
    STATUS_FEASIBLE,
    STATUS_OPTIMAL,
    STATUS_PROVEN_COVERAGE,
    STATUS_WITH_MARGIN,
    profile_policy,
)
from .policies import cluster_policy_eligibility, scenario_policies


# A tabela cresce sob demanda em vez de nascer com um teto fixo. Um teto fixo
# transformava qualquer base acima dele em IndexError dentro do solver, e uma
# planilha maior que o previsto e um cenario de operacao, nao um defeito da
# base. Crescer preserva a reprodutibilidade porque a sequencia de primos e
# unica: a oferta de indice N recebe sempre o N-esimo primo, qualquer que seja
# o tamanho da rodada que a pediu.
_CANONICAL_PRIMES: list[int] = []


def _primes(count: int) -> tuple[int, ...]:
    """Os ``count`` primeiros primos, usados como peso por oferta."""
    if count < 0:
        raise ValueError("A quantidade de primos nao pode ser negativa.")
    candidate = _CANONICAL_PRIMES[-1] + 1 if _CANONICAL_PRIMES else 2
    while len(_CANONICAL_PRIMES) < count:
        if all(
            candidate % prime
            for prime in _CANONICAL_PRIMES
            if prime * prime <= candidate
        ):
            _CANONICAL_PRIMES.append(candidate)
        candidate += 1
    return tuple(_CANONICAL_PRIMES[:count])


def _apply_tiebreak_cap(solver: cp_model.CpSolver, execution_policy) -> None:
    """Limita as fases de desempate quando o perfil nao exige prova delas."""
    if not execution_policy.prove_tiebreak and execution_policy.deterministic_cap:
        solver.parameters.max_deterministic_time = execution_policy.deterministic_cap


def _status_name(status: cp_model.CpSolverStatus) -> str:
    names = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }
    return names.get(status, str(status))


def _new_solver(
    max_time_seconds: float | None,
    phase_fraction: float,
    workers: int,
    random_seed: int,
) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    if max_time_seconds is not None and max_time_seconds > 0:
        solver.parameters.max_time_in_seconds = max_time_seconds * phase_fraction
    solver.parameters.num_search_workers = workers
    solver.parameters.random_seed = random_seed
    return solver


def _replace_hints(
    model: cp_model.CpModel,
    solver: cp_model.CpSolver,
    variables: tuple[cp_model.IntVar, ...],
) -> None:
    """Usa a melhor solução da fase anterior como warm start da próxima."""
    model.clear_hints()
    for variable in variables:
        model.add_hint(variable, solver.value(variable))


def _assignment_snapshot(
    problem: Problem,
    eligible: dict[int, list[int]],
    assignment_vars: dict[tuple[int, int], cp_model.IntVar],
    solver: cp_model.CpSolver,
) -> dict[int, int | None]:
    return {
        transmission.id: next(
            (
                teacher_id
                for teacher_id in eligible[transmission.id]
                if solver.value(assignment_vars[(transmission.id, teacher_id)])
            ),
            None,
        )
        for transmission in problem.transmissions
    }


def _allocation_reason(
    problem: Problem,
    transmission_id: int,
    teacher_id: int,
    eligible: dict[int, list[int]],
) -> str:
    teacher = problem.teachers[teacher_id]
    candidates = eligible[transmission_id]
    if len(candidates) == 1:
        return "Único docente elegível por perfil, carga e horário"
    if teacher.is_stricto:
        return (
            "Docente Stricto elegível, respeitando o limite de "
            f"{STRICTO_MAX_DISCIPLINES_PER_MODULE} disciplinas no módulo"
        )
    capacities = {
        candidate: problem.teachers[candidate].teaching_capacity
        for candidate in candidates
    }
    if capacities[teacher_id] == max(capacities.values()) and len(set(capacities.values())) > 1:
        return "Docente elegível priorizado pela maior CH letiva"
    # A contagem permanece em CANDIDATOS_ELEGÍVEIS; manter o texto estável
    # evita fragmentar indicadores e integrações por quantidade de candidatos.
    return "Docente elegível selecionado entre alternativas igualmente ótimas"


def solve_allocation(
    problem: Problem,
    max_time_seconds: float | None = None,
    workers: int = 8,
    random_seed: int = 42,
    grasp_iterations: int = 0,
    grasp_alpha: float = 0.25,
    scenario_policy: dict | None = None,
    criterion: str | None = None,
    prove_canonicity: bool = False,
    canonicity_proof_budget: float = 120.0,
    profile: str = PROFILE_FULL_PROOF,
    margin_offers: int | None = None,
) -> AllocationResult:
    """Resolve a alocação base e três fases SWITCH lexicográficas.

    1. Minimiza transmissões não alocadas.
    2. SWITCH de cobertura: maximiza docentes ativos com alguma alocação.
    3. SWITCH de ocupação: preserva os ótimos anteriores e favorece maior CH.
    4. SWITCH de resgate: protege transmissões com candidato único.
    5. Aderência de perfil: exclusiva de CLUSTER_PREFERENCIAL, desempata as
       soluções já ótimas em favor da compatibilidade exata de perfil.
    6. Canonicaliza a solução ótima em busca determinística de um worker.
    """
    optimization_started = perf_counter()
    if grasp_iterations < 0:
        raise ValueError("O número de iterações GRASP não pode ser negativo.")
    criterion = normalize_criterion(
        problem.criterion if criterion is None else criterion
    )
    cluster_mode = uses_cluster(criterion)
    execution_policy = profile_policy(profile, margin_offers)
    model = cp_model.CpModel()
    base_eligibility = build_eligibility(problem, criterion)
    assignment_vars: dict[tuple[int, int], cp_model.IntVar] = {}
    unassigned_vars: dict[int, cp_model.IntVar] = {}
    transmission_by_id = {item.id: item for item in problem.transmissions}
    transmission_by_row = {item.excel_row: item for item in problem.transmissions}
    teacher_by_badge = {item.badge: item for item in problem.teachers}
    policies = scenario_policies(scenario_policy)
    eligible, cluster_override_pairs, cluster_targets = cluster_policy_eligibility(
        problem,
        base_eligibility,
        policies,
    )

    for transmission in problem.transmissions:
        unassigned = model.new_bool_var(f"unassigned_t{transmission.id}")
        unassigned_vars[transmission.id] = unassigned
        options = []
        for teacher_id in eligible[transmission.id]:
            variable = model.new_bool_var(f"assign_t{transmission.id}_p{teacher_id}")
            assignment_vars[(transmission.id, teacher_id)] = variable
            options.append(variable)
        model.add_exactly_one(options + [unassigned])

    # Restrições exclusivas do motor de cenários. Elas são aplicadas antes dos
    # objetivos lexicográficos e nunca existem no solver principal de vbeta.
    for policy in policies:
        policy_type = str(policy.get("policy_type") or "").upper()
        target_type = str(policy.get("target_type") or "").upper()
        target_value = str(policy.get("target_value") or "")
        if policy_type == "PRIORIDADE":
            targets = []
            if target_type == "COURSE":
                targets = [item for item in problem.transmissions if item.course == target_value]
            elif target_type == "OFFER" and target_value.isdigit():
                target = transmission_by_row.get(int(target_value))
                targets = [target] if target else []
            if not targets:
                raise ValueError(f"Política de prioridade sem oferta válida: {target_value}")
            for target in targets:
                model.add(unassigned_vars[target.id] == 0)
        elif policy_type == "FIXAR":
            if target_type != "OFFER" or not target_value.isdigit():
                raise ValueError("Política de fixação sem oferta válida.")
            target = transmission_by_row.get(int(target_value))
            badge = str((policy.get("configuration") or {}).get("teacher_badge") or "")
            teacher = teacher_by_badge.get(badge)
            if not target or not teacher or (target.id, teacher.id) not in assignment_vars:
                raise ValueError(
                    f"A alocação fixada da linha {target_value} para a chapa {badge} não é elegível."
                )
            model.add(assignment_vars[(target.id, teacher.id)] == 1)

    load_vars: dict[int, cp_model.IntVar] = {}
    stage_load_vars: dict[tuple[int, str], cp_model.IntVar] = {}
    used_vars: dict[int, cp_model.IntVar] = {}
    for teacher in problem.teachers:
        allocation_capacity = teacher.allocation_capacity(problem.hours_per_transmission)
        teacher_variables = {
            transmission_id: variable
            for (transmission_id, teacher_id), variable in assignment_vars.items()
            if teacher_id == teacher.id
        }
        max_total_load = problem.hours_per_transmission * len(teacher_variables)
        load = model.new_int_var(0, max_total_load, f"load_p{teacher.id}")
        load_vars[teacher.id] = load
        model.add(
            load
            == problem.hours_per_transmission * sum(teacher_variables.values())
        )
        for stage in MODULE_STAGES:
            stage_variables = [
                variable
                for transmission_id, variable in teacher_variables.items()
                if stage in transmission_by_id[transmission_id].module_stages
            ]
            stage_load = model.new_int_var(
                0,
                max(0, allocation_capacity),
                f"load_{stage.lower()}_p{teacher.id}",
            )
            stage_load_vars[(teacher.id, stage)] = stage_load
            model.add(
                stage_load
                == problem.hours_per_transmission * sum(stage_variables)
            )
            model.add(stage_load <= allocation_capacity)
        # A exceção Stricto continua limitada a duas disciplinas distintas no
        # módulo, ainda que elas ocorram em metades diferentes.
        if teacher.is_stricto:
            model.add(load <= allocation_capacity)
        used = model.new_bool_var(f"used_p{teacher.id}")
        used_vars[teacher.id] = used
        if teacher.is_active and teacher_variables:
            model.add(load >= problem.hours_per_transmission * used)
            model.add(load <= max_total_load * used)
        else:
            model.add(used == 0)

    by_teacher_stage_slot: dict[
        tuple[int, str, tuple[str, str]], list[cp_model.IntVar]
    ] = defaultdict(list)
    for (transmission_id, teacher_id), variable in assignment_vars.items():
        transmission = transmission_by_id[transmission_id]
        slot = transmission.slot
        if slot is not None:
            for stage in transmission.module_stages:
                by_teacher_stage_slot[(teacher_id, stage, slot)].append(variable)
    for variables in by_teacher_stage_slot.values():
        if len(variables) > 1:
            model.add_at_most_one(variables)

    grasp_hint = None
    grasp_wall_time = 0.0
    if grasp_iterations:
        grasp_started = perf_counter()
        grasp_hint = build_grasp_hint(
            problem,
            eligible,
            iterations=grasp_iterations,
            alpha=grasp_alpha,
            random_seed=random_seed,
        )
        grasp_wall_time = perf_counter() - grasp_started
        for (transmission_id, teacher_id), variable in assignment_vars.items():
            model.add_hint(variable, int(grasp_hint.assignments[transmission_id] == teacher_id))
        for transmission_id, variable in unassigned_vars.items():
            model.add_hint(variable, int(grasp_hint.assignments[transmission_id] is None))
        hint_loads = {teacher.id: 0 for teacher in problem.teachers}
        hint_stage_loads = {
            teacher.id: {stage: 0 for stage in MODULE_STAGES}
            for teacher in problem.teachers
        }
        for transmission_id, teacher_id in grasp_hint.assignments.items():
            if teacher_id is not None:
                hint_loads[teacher_id] += problem.hours_per_transmission
                for stage in transmission_by_id[transmission_id].module_stages:
                    hint_stage_loads[teacher_id][stage] += problem.hours_per_transmission
        for teacher_id, variable in load_vars.items():
            model.add_hint(variable, hint_loads[teacher_id])
            model.add_hint(used_vars[teacher_id], int(hint_loads[teacher_id] > 0))
            for stage in MODULE_STAGES:
                model.add_hint(
                    stage_load_vars[(teacher_id, stage)],
                    hint_stage_loads[teacher_id][stage],
                )

    exact_profile_pairs = {
        key
        for key in assignment_vars
        if has_exact_profile(transmission_by_id[key[0]], problem.teachers[key[1]])
    }
    profile_phase_enabled = (
        criterion == CRITERION_CLUSTER_PREFERRED
        and bool(exact_profile_pairs)
        and len(exact_profile_pairs) < len(assignment_vars)
    )
    phase_budget = (
        (0.26, 0.22, 0.17, 0.13, 0.12, 0.10)
        if profile_phase_enabled
        else (0.30, 0.25, 0.20, 0.15, 0.00, 0.10)
    )

    all_variables = tuple(assignment_vars.values()) + tuple(unassigned_vars.values()) + (
        tuple(load_vars.values())
        + tuple(stage_load_vars.values())
        + tuple(used_vars.values())
    )

    total_unassigned = sum(unassigned_vars.values())
    model.minimize(total_unassigned)
    first_solver = _new_solver(max_time_seconds, phase_budget[0], workers, random_seed)
    if execution_policy.coverage_gap_offers > 0:
        # A folga e expressa em OFERTAS porque o objetivo da fase 1 e uma
        # contagem de ofertas nao alocadas. "No maximo N ofertas abaixo do
        # melhor possivel" e uma frase de negocio com garantia atras.
        first_solver.parameters.absolute_gap_limit = float(execution_policy.coverage_gap_offers)
    if not execution_policy.prove_coverage and execution_policy.deterministic_cap:
        first_solver.parameters.max_deterministic_time = execution_policy.deterministic_cap
    first_status = first_solver.solve(model)
    coverage_bound = None
    if first_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        coverage_bound = int(round(first_solver.best_objective_bound))
    if first_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return AllocationResult(
            status="SEM_SOLUCAO",
            solver_status=_status_name(first_status),
            assignments=[],
            teacher_loads={},
            objective_unassigned=len(problem.transmissions),
            used_teacher_count=0,
            zero_active_teacher_count=sum(teacher.is_active for teacher in problem.teachers),
            high_capacity_score=None,
            rescue_scarcity_score=None,
            wall_time_seconds=perf_counter() - optimization_started,
            diagnostics={
                "message": "O CP-SAT não encontrou solução utilizável.",
                "eligibility_criterion": criterion,
                "eligibility_uses_cluster": cluster_mode,
                "execution_profile": execution_policy.name,
                "grasp_wall_time_seconds": grasp_wall_time,
                "cp_sat_wall_time_seconds": first_solver.wall_time,
                "stricto_max_disciplines_per_module": (
                    STRICTO_MAX_DISCIPLINES_PER_MODULE
                ),
            },
        )

    best_unassigned = int(round(first_solver.objective_value))
    model.add(total_unassigned == best_unassigned)
    _replace_hints(model, first_solver, all_variables)
    total_used = sum(used_vars.values())
    model.maximize(total_used)

    second_solver = _new_solver(max_time_seconds, phase_budget[1], workers, random_seed)
    _apply_tiebreak_cap(second_solver, execution_policy)
    second_status = second_solver.solve(model)
    if second_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        best_used = int(round(second_solver.objective_value))
    else:
        best_used = sum(int(first_solver.value(variable)) for variable in used_vars.values())
    second_incumbent = (
        second_solver
        if second_status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else first_solver
    )
    model.add(total_used == best_used)
    _replace_hints(model, second_incumbent, all_variables)

    # Entre soluções com a mesma cobertura, cada atribuição a um docente com
    # maior CH_LETIVA recebe peso maior. Isso reduz a ociosidade dos contratos
    # com maior capacidade sem retirar docentes já cobertos pelo SWITCH anterior.
    high_capacity_score = sum(
        problem.teachers[teacher_id].teaching_capacity * variable
        for (_, teacher_id), variable in assignment_vars.items()
    )
    model.maximize(high_capacity_score)
    third_solver = _new_solver(max_time_seconds, phase_budget[2], workers, random_seed + 1)
    _apply_tiebreak_cap(third_solver, execution_policy)
    third_status = third_solver.solve(model)

    if third_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        best_capacity_score = int(round(third_solver.objective_value))
    elif second_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        best_capacity_score = int(second_solver.value(high_capacity_score))
    else:
        best_capacity_score = int(first_solver.value(high_capacity_score))
    third_incumbent = (
        third_solver
        if third_status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        else second_incumbent
    )
    model.add(high_capacity_score == best_capacity_score)
    _replace_hints(model, third_incumbent, all_variables)

    # Protege apenas disciplinas com um único docente elegível. A cobertura total,
    # docentes utilizados e score de CH já estão fixados; disciplinas com dois ou
    # mais candidatos não recebem prioridade apenas por sua contagem de candidatos.
    scarcity_penalty = sum(
        unassigned_vars[transmission.id]
        for transmission in problem.transmissions
        if transmission.slot is not None and len(eligible[transmission.id]) == 1
    )
    model.minimize(scarcity_penalty)
    fourth_solver = _new_solver(max_time_seconds, phase_budget[3], workers, random_seed + 2)
    _apply_tiebreak_cap(fourth_solver, execution_policy)
    fourth_status = fourth_solver.solve(model)

    if fourth_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        fourth_incumbent = fourth_solver
        fourth_incumbent_status = fourth_status
        best_scarcity_score = int(round(fourth_solver.objective_value))
    elif third_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        fourth_incumbent = third_solver
        fourth_incumbent_status = third_status
        best_scarcity_score = int(third_solver.value(scarcity_penalty))
    elif second_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        fourth_incumbent = second_solver
        fourth_incumbent_status = second_status
        best_scarcity_score = int(second_solver.value(scarcity_penalty))
    else:
        fourth_incumbent = first_solver
        fourth_incumbent_status = first_status
        best_scarcity_score = int(first_solver.value(scarcity_penalty))

    # Os quatro objetivos de negócio já estão fixados. Removemos objetivo e
    # hints paralelos e buscamos uma solução canônica com um único worker. Isso
    # mantém o ganho do paralelismo na prova dos ótimos e evita que empates
    # produzam planilhas diferentes em execuções idênticas.
    model.add(scarcity_penalty == best_scarcity_score)

    # Fase exclusiva de CLUSTER_PREFERENCIAL. Os quatro ótimos de negócio já
    # estão fixados, então maximizar a aderência exata de perfil apenas escolhe,
    # entre soluções empatadas, a pedagogicamente mais aderente.
    exact_profile_score = sum(
        variable
        for key, variable in assignment_vars.items()
        if key in exact_profile_pairs
    )
    profile_solver: cp_model.CpSolver | None = None
    profile_status = None
    best_exact_profile_score = None
    if profile_phase_enabled:
        _replace_hints(model, fourth_incumbent, all_variables)
        model.maximize(exact_profile_score)
        profile_solver = _new_solver(
            max_time_seconds, phase_budget[4], workers, random_seed + 3
        )
        profile_status = profile_solver.solve(model)
        if profile_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            best_exact_profile_score = int(round(profile_solver.objective_value))
            fourth_incumbent = profile_solver
            fourth_incumbent_status = profile_status
        else:
            best_exact_profile_score = int(
                fourth_incumbent.value(exact_profile_score)
            )
        model.add(exact_profile_score == best_exact_profile_score)

    # Canonicalizacao por otimo unico.
    #
    # A versao anterior removia o objetivo e pedia "qualquer ponto viavel" a um
    # unico worker, contando com a busca determinística para reproduzir a mesma
    # planilha. Isso custava caro: com os quatro otimos fixados como igualdades,
    # um worker sozinho nao encontrava sequer uma solucao viavel em modelos
    # grandes, porque perdia o portfolio de estrategias que o CP-SAT roda em
    # paralelo.
    #
    # Aqui o determinismo passa a ser propriedade do MODELO, e nao da busca: o
    # desempate tem otimo unico, entao qualquer solver correto converge para a
    # mesma solucao, com qualquer numero de workers, semente ou maquina.
    #
    # O peso de cada atribuicao e o indice do docente multiplicado por um primo
    # proprio da oferta. Sem o primo, duas ofertas trocando de docente entre si
    # se cancelariam e o total empataria; com ele, o empate exigiria que uma
    # combinacao inteira de diferencas zerasse.
    model.clear_hints()
    canonical_weights = _primes(
        max((item.id for item in problem.transmissions), default=-1) + 1
    )
    canonical_score = sum(
        canonical_weights[transmission_id] * (teacher_id + 1) * variable
        for (transmission_id, teacher_id), variable in assignment_vars.items()
    )
    model.minimize(canonical_score)
    canonical_solver = _new_solver(
        max_time_seconds, phase_budget[5], workers, random_seed
    )
    canonical_status = canonical_solver.solve(model)
    if canonical_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        solver, final_status = canonical_solver, canonical_status
    else:
        solver, final_status = fourth_incumbent, fourth_incumbent_status

    # A canonicidade nao e assumida, e verificada: proibimos a solucao
    # encontrada, exigimos o mesmo valor de desempate e perguntamos ao solver
    # se existe outra. INFEASIBLE prova que a solucao publicada e a unica
    # possivel sob os otimos fixados, e essa prova vai para os diagnosticos.
    canonicity_proven = None
    canonical_value = None
    proof_wall_time = 0.0
    if canonical_status in (cp_model.OPTIMAL, cp_model.FEASIBLE) and prove_canonicity:
        canonical_value = int(round(canonical_solver.objective_value))
        chosen = [
            variable
            for variable in assignment_vars.values()
            if canonical_solver.value(variable)
        ]
        if chosen:
            proof_model = model.clone()
            proof_model.add(canonical_score == canonical_value)
            proof_model.add(sum(chosen) <= len(chosen) - 1)
            proof_model.clear_objective()
            proof_solver = _new_solver(
                max_time_seconds, phase_budget[5], workers, random_seed
            )
            # Orcamento DETERMINISTICO: a prova e uma atestacao sobre a solucao,
            # nao a solucao em si. Um teto de relogio tornaria o campo do
            # manifesto irreprodutivel; o teto deterministico nao. Sem teto, a
            # prova pode custar mais que toda a otimizacao.
            proof_solver.parameters.max_deterministic_time = canonicity_proof_budget
            proof_status = proof_solver.solve(proof_model)
            proof_wall_time = proof_solver.wall_time
            if proof_status == cp_model.INFEASIBLE:
                canonicity_proven = True
            elif proof_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
                canonicity_proven = False
            else:
                # Nao coube no orcamento: a rodada segue valida e otima, apenas
                # sem a atestacao de canonicidade.
                canonicity_proven = None
    elif canonical_status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        canonical_value = int(round(canonical_solver.objective_value))

    phase_statuses = [first_status, second_status, third_status, fourth_status]
    if profile_status is not None:
        phase_statuses.append(profile_status)
    coverage_proven = first_status == cp_model.OPTIMAL
    coverage_gap = (
        None
        if coverage_bound is None
        else max(0, best_unassigned - coverage_bound)
    )
    tiebreak_proven = all(
        status == cp_model.OPTIMAL for status in phase_statuses[1:]
    )
    if coverage_proven and tiebreak_proven and not coverage_gap:
        overall_solver_status = STATUS_OPTIMAL
    elif coverage_proven and not coverage_gap:
        # A cobertura esta provada; apenas o desempate entre solucoes de mesma
        # cobertura ficou sem prova.
        overall_solver_status = STATUS_PROVEN_COVERAGE
    elif coverage_gap is not None and coverage_gap <= execution_policy.coverage_gap_offers:
        overall_solver_status = STATUS_WITH_MARGIN
    else:
        overall_solver_status = STATUS_FEASIBLE

    loads = {
        teacher.id: int(solver.value(load_vars[teacher.id]))
        for teacher in problem.teachers
    }
    stage_loads = {
        teacher.id: {
            stage: int(solver.value(stage_load_vars[(teacher.id, stage)]))
            for stage in MODULE_STAGES
        }
        for teacher in problem.teachers
    }
    assigned_teacher = _assignment_snapshot(problem, eligible, assignment_vars, solver)
    occupied_stage_slots = {
        (teacher_id, stage, transmission_by_id[transmission_id].slot)
        for transmission_id, teacher_id in assigned_teacher.items()
        if teacher_id is not None
        for stage in transmission_by_id[transmission_id].module_stages
    }

    assignments: list[Assignment] = []
    for transmission in problem.transmissions:
        teacher_id = assigned_teacher[transmission.id]
        if teacher_id is not None:
            status, reason = "ALOCADA", ""
            if (transmission.id, teacher_id) in cluster_override_pairs:
                allocation_reason = (
                    f"Docente do cluster {transmission.cluster} alocado por decisão de cenário; "
                    "perfil exato flexibilizado"
                )
            elif cluster_mode and not has_exact_profile(
                transmission, problem.teachers[teacher_id]
            ):
                allocation_reason = (
                    f"Docente do cluster {transmission.cluster} elegível pelo "
                    "critério de cluster; perfil exato não disponível"
                )
            else:
                allocation_reason = _allocation_reason(
                    problem,
                    transmission.id,
                    teacher_id,
                    eligible,
                )
        elif transmission.slot is None:
            status, reason = "NAO_ALOCADA", "AGENDA_INVALIDA"
            allocation_reason = ""
        elif not eligible[transmission.id]:
            status, reason = "NAO_ALOCADA", "SEM_DOCENTE_COM_PERFIL_E_CARGA"
            allocation_reason = ""
        else:
            capacity_available = {
                candidate
                for candidate in eligible[transmission.id]
                if all(
                    stage_loads[candidate][stage]
                    + problem.hours_per_transmission
                    <= problem.teachers[candidate].allocation_capacity(
                        problem.hours_per_transmission
                    )
                    for stage in transmission.module_stages
                )
                and (
                    not problem.teachers[candidate].is_stricto
                    or loads[candidate] + problem.hours_per_transmission
                    <= problem.teachers[candidate].allocation_capacity(
                        problem.hours_per_transmission
                    )
                )
            }
            schedule_available = {
                candidate
                for candidate in eligible[transmission.id]
                if all(
                    (candidate, stage, transmission.slot)
                    not in occupied_stage_slots
                    for stage in transmission.module_stages
                )
            }
            if not capacity_available and not schedule_available:
                reason = "CAPACIDADE_E_HORARIO_COMBINADOS"
            elif not capacity_available:
                reason = "CAPACIDADE_LETIVA_ESGOTADA"
            elif not schedule_available:
                reason = "CHOQUE_DE_HORARIO"
            else:
                reason = "CAPACIDADE_E_HORARIO_COMBINADOS"
            status = "NAO_ALOCADA"
            allocation_reason = ""
        assignments.append(
            Assignment(
                transmission_id=transmission.id,
                teacher_id=teacher_id,
                status=status,
                reason=reason,
                eligible_teacher_count=len(eligible[transmission.id]),
                allocation_reason=allocation_reason,
            )
        )

    exact_profile_assignments = sum(
        has_exact_profile(
            transmission_by_id[item.transmission_id],
            problem.teachers[item.teacher_id],
        )
        for item in assignments
        if item.teacher_id is not None
    )
    cluster_profile_assignments = (
        sum(item.teacher_id is not None for item in assignments)
        - exact_profile_assignments
    )
    profile_fallback_rows = {
        transmission.excel_row
        for transmission in problem.transmissions
        if cluster_mode and not transmission.cluster.strip()
    }
    used_count = sum(load > 0 for load in loads.values())
    active_count = sum(teacher.is_active for teacher in problem.teachers)
    capacity_score = int(solver.value(high_capacity_score))
    rescue_score = int(solver.value(scarcity_penalty))
    return AllocationResult(
        status="COMPLETA" if best_unassigned == 0 else "PARCIAL",
        solver_status=overall_solver_status,
        assignments=assignments,
        teacher_loads=loads,
        objective_unassigned=best_unassigned,
        used_teacher_count=used_count,
        zero_active_teacher_count=active_count - used_count,
        high_capacity_score=capacity_score,
        rescue_scarcity_score=rescue_score,
        wall_time_seconds=perf_counter() - optimization_started,
        teacher_stage_loads=stage_loads,
        diagnostics={
            "cp_sat_wall_time_seconds": (
                first_solver.wall_time
                + second_solver.wall_time
                + third_solver.wall_time
                + fourth_solver.wall_time
                + (profile_solver.wall_time if profile_solver is not None else 0.0)
                + canonical_solver.wall_time
                + proof_wall_time
            ),
            "grasp_wall_time_seconds": grasp_wall_time,
            "phase_1_status": _status_name(first_status),
            "switch_1_teacher_coverage_status": _status_name(second_status),
            "scenario_policy_count": len(policies),
            "scenario_cluster_targets": sorted(cluster_targets),
            "scenario_cluster_override_candidates": len(cluster_override_pairs),
            "scenario_cluster_eligibility": {
                str(transmission.id): eligible[transmission.id]
                for transmission in problem.transmissions
                if transmission.cluster in cluster_targets
            },
            "scenario_cluster_override_pairs": [
                [transmission_id, teacher_id]
                for transmission_id, teacher_id in sorted(cluster_override_pairs)
            ],
            "scenario_cluster_override_assignments": sum(
                (item.transmission_id, item.teacher_id) in cluster_override_pairs
                for item in assignments if item.teacher_id is not None
            ),
            "switch_2_high_capacity_status": _status_name(third_status),
            "switch_3_scarcity_rescue_status": _status_name(fourth_status),
            "switch_4_profile_adherence_status": (
                _status_name(profile_status) if profile_status is not None else None
            ),
            "profile_adherence_phase_applied": profile_phase_enabled,
            "best_exact_profile_score": best_exact_profile_score,
            "canonicalization_status": _status_name(canonical_status),
            "canonicalization_workers": workers,
            "canonical_tiebreak_score": canonical_value,
            "canonicity_proven": canonicity_proven,
            "canonicity_proof_requested": prove_canonicity,
            "canonicity_proof_wall_time_seconds": proof_wall_time,
            "canonicity_proof_budget": canonicity_proof_budget,
            "selected_solution_phase_status": _status_name(final_status),
            "all_lexicographic_phases_optimal": overall_solver_status == "OPTIMAL",
            "best_used_teachers": best_used,
            "best_high_capacity_score": best_capacity_score,
            "scarcity_rescue_penalty": rescue_score,
            "unique_candidate_unassigned": rescue_score,
            "grasp_iterations": grasp_hint.iterations if grasp_hint else 0,
            "grasp_alpha": grasp_alpha,
            "grasp_hint_unassigned": grasp_hint.score[0] if grasp_hint else None,
            "grasp_hint_zero_active_teachers": grasp_hint.score[1] if grasp_hint else None,
            "grasp_hint_high_capacity_score": -grasp_hint.score[2] if grasp_hint else None,
            "grasp_hint_scarcity_penalty": grasp_hint.score[3] if grasp_hint else None,
            "cp_sat_time_limit_seconds": max_time_seconds,
            "stricto_max_disciplines_per_module": (
                STRICTO_MAX_DISCIPLINES_PER_MODULE
            ),
            "execution_profile": execution_policy.name,
            "profile_requires_status": execution_policy.required_status,
            "profile_promotable": execution_policy.promotable,
            "coverage_proven": coverage_proven,
            "coverage_bound": coverage_bound,
            "coverage_gap_offers": coverage_gap,
            "accepted_gap_offers": execution_policy.coverage_gap_offers,
            "tiebreak_proven": tiebreak_proven,
            "deterministic_cap": execution_policy.deterministic_cap,
            "eligibility_criterion": criterion,
            "eligibility_uses_cluster": cluster_mode,
            "exact_profile_assignments": exact_profile_assignments,
            "cluster_profile_assignments": cluster_profile_assignments,
            "profile_fallback_offers": sorted(profile_fallback_rows),
            "capacity_model": "WEEKLY_BY_MODULE_STAGE",
            "module_stage_order_mapping": {
                "1ª": [MODULE_STAGES[0]],
                "2ª": [MODULE_STAGES[1]],
                "ESTENDIDA": list(MODULE_STAGES),
            },
            "assignment_variables": len(assignment_vars),
            "teacher_slot_constraints": sum(
                len(items) > 1 for items in by_teacher_stage_slot.values()
            ),
            "teacher_stage_slot_constraints": sum(
                len(items) > 1 for items in by_teacher_stage_slot.values()
            ),
            "teacher_stage_capacity_constraints": len(stage_load_vars),
        },
    )
