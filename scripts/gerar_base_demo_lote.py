"""Monta a base de demonstração do processamento em lote.

As duas bases de demonstração existentes cobrem a rodada única: cada uma tem um
módulo só. O lote precisa também do outro formato aceito — uma planilha anual,
com vários módulos na mesma aba, que a aplicação separa antes de validar.

Esta base é derivada das duas já publicadas, e não de dados reais. Duas coisas
precisam de cuidado ao juntá-las:

1. **Elas foram anonimizadas em execuções separadas.** O mesmo `CUR_001`
   designa cursos diferentes em cada uma, e 167 chapas colidem apontando para
   pessoas distintas. Juntar sem reidentificar produziria dependências
   funcionais inconsistentes (`CURSO -> NOME_CURSO`, `CURSO -> CLUSTER`), que a
   validação reprova. Por isso os identificadores da segunda base ganham um
   espaço próprio.

2. **Cluster e perfil da disciplina continuam compartilhados.** São vocabulários
   institucionais, e é o que faz o critério por cluster e a compatibilidade de
   perfil terem sentido sobre o corpo docente inteiro.

Os cursos são distribuídos entre os módulos 51 a 54, cada curso inteiro em um
módulo só, equilibrando a quantidade de ofertas. Nenhuma oferta é duplicada:
cada linha aparece uma única vez, em um módulo único.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Any

from openpyxl import Workbook, load_workbook

MAPA_SHEET = "MAPA PEDAGÓGICO"
DOCENTES_SHEET = "DOCENTES"
MODULOS = (51, 52, 53, 54)

# Colunas cujo valor identifica uma entidade da segunda base e, por isso,
# precisa de um espaço próprio ao conviver com a primeira.
COLUNAS_REIDENTIFICADAS = ("CURSO", "CURRÍCULO", "COD_DISCIPLINA")

REPO_ROOT = Path(__file__).resolve().parents[1]
PADRAO_ORIGENS = (
    REPO_ROOT / "exemplos" / "BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx",
    REPO_ROOT / "exemplos" / "BASE_DEMONSTRACAO_ANONIMIZADA_M53.xlsx",
)
PADRAO_DESTINO = REPO_ROOT / "exemplos" / "BASE_DEMONSTRACAO_ANONIMIZADA_LOTE_ANUAL.xlsx"


def _ler(caminho: Path, aba: str) -> tuple[list[str], list[tuple[Any, ...]]]:
    workbook = load_workbook(caminho, read_only=True, data_only=True)
    try:
        if aba not in workbook.sheetnames:
            raise SystemExit(f"{caminho.name}: aba {aba} ausente.")
        worksheet = workbook[aba]
        linhas = list(worksheet.iter_rows(min_row=1, values_only=True))
        cabecalho = [str(valor or "").strip() for valor in linhas[0]]
        corpo = [
            linha
            for linha in linhas[1:]
            if any(valor is not None and str(valor).strip() for valor in linha)
        ]
        return cabecalho, corpo
    finally:
        workbook.close()


def _texto(linha: tuple[Any, ...], indices: dict[str, int], coluna: str) -> str:
    posicao = indices.get(coluna)
    if posicao is None or posicao >= len(linha):
        return ""
    return str(linha[posicao] or "").strip()


def _e_oferta(linha: tuple[Any, ...], indices: dict[str, int]) -> bool:
    """Mesma regra do motor: só estas linhas viram ofertas do problema."""
    sinergia = _texto(linha, indices, "SINERGIA").upper()
    formato = _texto(linha, indices, "FORMATO_AULA").upper()
    return sinergia in {"CURSO ÚNICO", "CURSO RESPONSÁVEL"} and formato == "AO VIVO"


def _reidentificar(
    linha: tuple[Any, ...],
    indices: dict[str, int],
    colunas: tuple[str, ...],
    sufixo: str,
) -> list[Any]:
    """Move os identificadores da linha para um espaço próprio."""
    valores = list(linha)
    for coluna in colunas:
        posicao = indices.get(coluna)
        if posicao is None or posicao >= len(valores):
            continue
        atual = str(valores[posicao] or "").strip()
        if atual:
            valores[posicao] = f"{atual}{sufixo}"
    return valores


def _distribuir_cursos(
    ofertas_por_curso: dict[str, int],
) -> dict[str, int]:
    """Cada curso inteiro em um módulo, equilibrando as ofertas entre eles.

    Manter o curso inteiro no mesmo módulo preserva a leitura pedagógica: os
    filtros por curso e por cluster continuam significando alguma coisa dentro
    de cada rodada.
    """
    carga = {modulo: 0 for modulo in MODULOS}
    destino: dict[str, int] = {}
    # Cursos maiores primeiro: o guloso só equilibra bem se as peças grandes
    # forem colocadas antes das pequenas.
    ordenados = sorted(
        ofertas_por_curso.items(), key=lambda item: (-item[1], item[0])
    )
    for curso, total in ordenados:
        escolhido = min(MODULOS, key=lambda modulo: (carga[modulo], modulo))
        destino[curso] = escolhido
        carga[escolhido] += total
    return destino


def gerar(origens: list[Path], destino: Path) -> dict[str, Any]:
    if len(origens) < 2:
        raise SystemExit("Informe ao menos duas bases de origem.")

    cabecalho_mapa: list[str] = []
    cabecalho_docentes: list[str] = []
    mapa: list[list[Any]] = []
    docentes: list[list[Any]] = []

    for posicao, origem in enumerate(origens):
        cab_mapa, linhas_mapa = _ler(origem, MAPA_SHEET)
        cab_doc, linhas_doc = _ler(origem, DOCENTES_SHEET)
        if not cabecalho_mapa:
            cabecalho_mapa, cabecalho_docentes = cab_mapa, cab_doc
        elif cab_mapa != cabecalho_mapa or cab_doc != cabecalho_docentes:
            raise SystemExit(
                f"{origem.name}: cabeçalhos diferentes da primeira base; "
                "as origens precisam do mesmo contrato de colunas."
            )

        indices_mapa = {nome: i for i, nome in enumerate(cab_mapa)}
        indices_doc = {nome: i for i, nome in enumerate(cab_doc)}
        # A primeira base fica como está; as seguintes ganham um espaço próprio.
        sufixo = "" if posicao == 0 else f"_B{posicao}"

        for linha in linhas_mapa:
            mapa.append(
                _reidentificar(linha, indices_mapa, COLUNAS_REIDENTIFICADAS, sufixo)
                if sufixo
                else list(linha)
            )

        for linha in linhas_doc:
            docentes.append(list(linha))

    # As duas bases numeram os docentes a partir de 001, então metade do quadro
    # combinado sairia com nome e chapa repetidos. Renumerar o conjunto inteiro
    # devolve uma série contínua, que é o que uma base anual teria de fato.
    indices_doc = {nome: i for i, nome in enumerate(cabecalho_docentes)}
    posicao_nome = indices_doc["NOME"]
    posicao_chapa = indices_doc["CHAPA"]
    largura = max(3, len(str(len(docentes))))
    for ordem, valores in enumerate(docentes, start=1):
        valores[posicao_nome] = f"Docente {ordem:0{largura}d}"
        # A chapa precisa continuar com doze dígitos: a validação cobra o
        # formato, e o Dashboard usa a chapa como identidade do docente.
        valores[posicao_chapa] = f"{900_000_000_000 + ordem}"

    indices_mapa = {nome: i for i, nome in enumerate(cabecalho_mapa)}
    ofertas_por_curso: dict[str, int] = defaultdict(int)
    for linha in mapa:
        if _e_oferta(tuple(linha), indices_mapa):
            ofertas_por_curso[_texto(tuple(linha), indices_mapa, "CURSO")] += 1
    # Cursos sem oferta alocável ainda precisam de um módulo: eles entram como
    # linha de apoio da rodada em que o curso caiu.
    for linha in mapa:
        curso = _texto(tuple(linha), indices_mapa, "CURSO")
        ofertas_por_curso.setdefault(curso, 0)

    modulo_do_curso = _distribuir_cursos(dict(ofertas_por_curso))
    posicao_modulo = indices_mapa["MÓD"]
    for linha in mapa:
        curso = _texto(tuple(linha), indices_mapa, "CURSO")
        linha[posicao_modulo] = modulo_do_curso.get(curso, MODULOS[0])

    workbook = Workbook()
    aba_mapa = workbook.active
    aba_mapa.title = MAPA_SHEET
    aba_mapa.append(cabecalho_mapa)
    for linha in mapa:
        aba_mapa.append(linha)
    aba_doc = workbook.create_sheet(DOCENTES_SHEET)
    aba_doc.append(cabecalho_docentes)
    for linha in docentes:
        aba_doc.append(linha)
    destino.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(destino)
    workbook.close()

    por_modulo: dict[int, dict[str, int]] = {
        modulo: {"linhas": 0, "ofertas": 0, "cursos": 0} for modulo in MODULOS
    }
    cursos_por_modulo: dict[int, set[str]] = defaultdict(set)
    for linha in mapa:
        modulo = int(linha[posicao_modulo])
        por_modulo[modulo]["linhas"] += 1
        cursos_por_modulo[modulo].add(_texto(tuple(linha), indices_mapa, "CURSO"))
        if _e_oferta(tuple(linha), indices_mapa):
            por_modulo[modulo]["ofertas"] += 1
    for modulo in MODULOS:
        por_modulo[modulo]["cursos"] = len(cursos_por_modulo[modulo])

    return {
        "destino": destino,
        "linhas": len(mapa),
        "docentes": len(docentes),
        "por_modulo": por_modulo,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera a base anual de demonstração do processamento em lote a "
            "partir das bases de módulo já publicadas."
        )
    )
    parser.add_argument("--origem", type=Path, action="append")
    parser.add_argument("--destino", type=Path, default=PADRAO_DESTINO)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    origens = args.origem or list(PADRAO_ORIGENS)
    faltando = [str(item) for item in origens if not item.is_file()]
    if faltando:
        raise SystemExit("Base de origem inexistente: " + ", ".join(faltando))

    resumo = gerar(origens, args.destino)
    print(f"Base de lote gerada: {resumo['destino']}")
    print(f"  {resumo['linhas']} linhas no mapa · {resumo['docentes']} docentes")
    for modulo, dados in resumo["por_modulo"].items():
        print(
            f"  módulo {modulo}: {dados['ofertas']} ofertas, "
            f"{dados['linhas']} linhas, {dados['cursos']} cursos"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
