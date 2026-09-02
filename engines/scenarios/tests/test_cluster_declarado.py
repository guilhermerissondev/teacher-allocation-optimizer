"""Cluster declarado no docente como referência dos métodos por cluster.

Antes deste contrato, a candidatura por cluster passava pelo perfil: o motor
expandia os perfis aceitos para a união dos perfis das ofertas do cluster. Isso
só funciona quando a taxonomia de perfil está completa e coerente. Com o
CLUSTER declarado nos dois lados, a comparação é direta e não depende disso.
"""
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
    build_eligibility,
)
from motor_alocacao.normalization import profile_tokens  # noqa: E402


def docente(identificador: int, perfis, clusters=(), capacidade: int = 10) -> Teacher:
    return Teacher(
        identificador, f"Docente {identificador}", f"{identificador:012d}",
        "PROFESSOR REGENTE", 40, capacidade, "Gestor", "ATIVO",
        frozenset(perfis), ", ".join(perfis),
        # Mesma tokenizacao que o loader aplica na coluna CLUSTER.
        profile_tokens(", ".join(clusters)), ", ".join(clusters),
    )


def oferta(identificador: int, perfis, cluster="SAÚDE") -> Transmission:
    return Transmission(
        identificador, identificador + 2, "C", "Curso", "CURR", f"D{identificador}",
        "Disciplina", frozenset(perfis), ", ".join(perfis), "Curso único",
        "SEGUNDA", time(19, 0), "1ª", cluster, "Coordenador",
    )


class ClusterDeclaradoTests(unittest.TestCase):
    def test_cluster_do_docente_substitui_o_perfil_na_candidatura(self) -> None:
        # O docente não tem nenhum perfil em comum com a oferta, mas declara o
        # cluster dela: sob o método por cluster, isso basta.
        problema = Problem(
            source=Path("base.xlsx"),
            teachers=(docente(0, ["enfermagem"], clusters=["SAÚDE"]),),
            transmissions=(oferta(0, ["radiologia"], cluster="SAÚDE"),),
            criterion=CRITERION_CLUSTER_PURE,
        )
        self.assertEqual([0], build_eligibility(problema)[0])

    def test_cluster_diferente_nao_torna_o_docente_candidato(self) -> None:
        problema = Problem(
            source=Path("base.xlsx"),
            teachers=(docente(0, ["enfermagem"], clusters=["EDUCAÇÃO"]),),
            transmissions=(oferta(0, ["radiologia"], cluster="SAÚDE"),),
            criterion=CRITERION_CLUSTER_PURE,
        )
        self.assertEqual([], build_eligibility(problema)[0])

    def test_a_comparacao_de_cluster_ignora_caixa_e_espacos(self) -> None:
        problema = Problem(
            source=Path("base.xlsx"),
            teachers=(docente(0, ["enfermagem"], clusters=["  saúde  "]),),
            transmissions=(oferta(0, ["radiologia"], cluster="SAÚDE"),),
            criterion=CRITERION_CLUSTER_PURE,
        )
        self.assertEqual([0], build_eligibility(problema)[0])

    def test_perfil_exato_nao_e_afetado_pelo_cluster_declarado(self) -> None:
        # O cluster só governa os métodos por cluster; no perfil exato ele não
        # abre nem fecha candidatura.
        problema = Problem(
            source=Path("base.xlsx"),
            teachers=(docente(0, ["enfermagem"], clusters=["SAÚDE"]),),
            transmissions=(oferta(0, ["radiologia"], cluster="SAÚDE"),),
            criterion=CRITERION_PROFILE,
        )
        self.assertEqual([], build_eligibility(problema)[0])

    def test_oferta_sem_cluster_continua_restrita_ao_proprio_perfil(self) -> None:
        # Oferta sem cluster não forma grupo: agregá-la produziria um conjunto
        # sem significado pedagógico.
        problema = Problem(
            source=Path("base.xlsx"),
            teachers=(
                docente(0, ["enfermagem"], clusters=["SAÚDE"]),
                docente(1, ["radiologia"], clusters=["SAÚDE"]),
            ),
            transmissions=(oferta(0, ["radiologia"], cluster=""),),
            criterion=CRITERION_CLUSTER_PURE,
        )
        self.assertEqual([1], build_eligibility(problema)[0])

    def test_base_sem_cluster_no_docente_mantem_a_regra_anterior(self) -> None:
        # Bases anteriores ao contrato 2.4 não trazem a coluna. O motor segue
        # pela união dos perfis das ofertas do cluster, como antes.
        problema = Problem(
            source=Path("base.xlsx"),
            teachers=(docente(0, ["enfermagem"]),),
            transmissions=(
                oferta(0, ["radiologia"], cluster="SAÚDE"),
                oferta(1, ["enfermagem"], cluster="SAÚDE"),
            ),
            criterion=CRITERION_CLUSTER_PURE,
        )
        elegiveis = build_eligibility(problema)
        # "enfermagem" está na união do cluster SAÚDE, então a oferta de
        # radiologia aceita o docente mesmo sem cluster declarado.
        self.assertEqual([0], elegiveis[0])

    def test_um_docente_pode_declarar_varios_clusters(self) -> None:
        problema = Problem(
            source=Path("base.xlsx"),
            teachers=(docente(0, ["enfermagem"], clusters=["SAÚDE", "EDUCAÇÃO"]),),
            transmissions=(
                oferta(0, ["radiologia"], cluster="SAÚDE"),
                oferta(1, ["pedagogia"], cluster="EDUCAÇÃO"),
                oferta(2, ["civil"], cluster="ENGENHARIAS"),
            ),
            criterion=CRITERION_CLUSTER_PURE,
        )
        elegiveis = build_eligibility(problema)
        self.assertEqual([0], elegiveis[0])
        self.assertEqual([0], elegiveis[1])
        self.assertEqual([], elegiveis[2])

    def test_cluster_preferencial_usa_a_mesma_candidatura_do_cluster_puro(self) -> None:
        # A diferença entre os dois métodos é de desempate, não de quem entra
        # na disputa.
        docentes = (docente(0, ["enfermagem"], clusters=["SAÚDE"]),)
        ofertas = (oferta(0, ["radiologia"], cluster="SAÚDE"),)
        puro = Problem(source=Path("b.xlsx"), teachers=docentes, transmissions=ofertas,
                       criterion=CRITERION_CLUSTER_PURE)
        preferencial = Problem(source=Path("b.xlsx"), teachers=docentes, transmissions=ofertas,
                               criterion=CRITERION_CLUSTER_PREFERRED)
        self.assertEqual(build_eligibility(puro), build_eligibility(preferencial))


if __name__ == "__main__":
    unittest.main()
