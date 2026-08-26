from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pipeline import (
    CRITERION_PROFILE,
    PROFILE_FULL_PROOF,
    SOLVER_PROFILES,
    DEFAULT_EXPECTED_MODULE,
    DEFAULT_INPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    EXIT_INPUT_CONFIG,
    ELIGIBILITY_CRITERIA,
    PipelineConfig,
    run_pipeline,
)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_INPUT_CONFIG, f"{self.prog}: erro: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        description="Valida, resolve e audita uma base de alocação docente.",
    )
    parser.add_argument(
        "--base",
        type=Path,
        help="XLSX explícito; se omitido, descobre exatamente um arquivo em entrada/.",
    )
    parser.add_argument("--entrada", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--resultado", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--modulo",
        type=int,
        default=DEFAULT_EXPECTED_MODULE,
        help=f"Módulo esperado na base (padrão: {DEFAULT_EXPECTED_MODULE}).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Workers das fases de otimização; a canonicalização final usa 1.",
    )
    parser.add_argument("--tempo-limite", type=float, default=None)
    parser.add_argument(
        "--perfil",
        choices=SOLVER_PROFILES,
        default=PROFILE_FULL_PROOF,
        help=(
            "Garantia exigida da rodada: PROVA_COMPLETA prova todas as fases; "
            "COBERTURA_PROVADA prova a cobertura e limita os desempates; "
            "MARGEM_ACEITA aceita folga provada em ofertas; "
            "EXPLORACAO_RAPIDA nao oferece garantia."
        ),
    )
    parser.add_argument(
        "--margem-ofertas",
        type=int,
        default=None,
        help="Folga aceita, em ofertas, quando o perfil e MARGEM_ACEITA.",
    )
    parser.add_argument(
        "--provar-canonicidade",
        action="store_true",
        help=(
            "Verifica que a solucao publicada e a unica canonica. Custa mais "
            "que toda a otimizacao e por isso nao e padrao."
        ),
    )
    parser.add_argument(
        "--criterio",
        choices=ELIGIBILITY_CRITERIA,
        default=CRITERION_PROFILE,
        help=(
            "Critério de elegibilidade: PERFIL_EXATO restringe à interseção "
            "exata de perfil; CLUSTER_PREFERENCIAL usa os perfis do cluster e "
            "desempata pelo perfil exato; CLUSTER_PURO usa apenas o cluster."
        ),
    )
    parser.add_argument(
        "--permitir-nao-otimo",
        action="store_true",
        help="Aceita FEASIBLE auditado; por padrão exige OPTIMAL.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    run = run_pipeline(
        PipelineConfig(
            input_dir=args.entrada,
            output_dir=args.resultado,
            base=args.base,
            workers=args.workers,
            max_time_seconds=args.tempo_limite,
            require_optimal=not args.permitir_nao_otimo,
            expected_module=args.modulo,
            criterion=args.criterio,
            profile=args.perfil,
            margin_offers=args.margem_ofertas,
            prove_canonicity=args.provar_canonicidade,
        )
    )
    print(f"Status: {run.state}")
    print(f"Código: {run.exit_code}")
    print(f"Mensagem: {run.message}")
    if run.round_dir:
        print(f"Rodada: {run.round_dir}")
        print(f"Status JSON: {run.status_path}")
        print(f"Manifesto: {run.manifest_path}")
    return run.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
