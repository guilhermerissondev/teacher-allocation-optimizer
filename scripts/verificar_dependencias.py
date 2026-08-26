"""Confere se as dependências de execução já estão presentes na máquina.

O `OPTIMAL.bat` chama este verificador antes de iniciar a aplicação. O código de
saída informa ao lote qual caminho seguir, e o texto impresso é a mensagem que o
usuário lê no console:

* 0 — interpretador homologado e todas as dependências travadas instaladas;
* 1 — interpretador homologado, mas faltam dependências (cabe oferecer a
  instalação assistida pelo scripts/instalar.ps1);
* 2 — o Python que executou este arquivo não é 64 bits estável 3.12 ou 3.13;
* 3 — não foi possível concluir a verificação (arquivo de travas ilegível).

A referência é o `requirements.lock`, o mesmo arquivo que o instalador aplica com
`--require-hashes`. Conferir a lista travada inteira, e não apenas as
dependências diretas, é o que garante que um ambiente pela metade seja detectado
antes de a aplicação tentar subir.
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK_FILE = ROOT / "requirements.lock"
SUPPORTED_VERSIONS = {(3, 12), (3, 13)}
MAXIMO_LISTADO = 8

CODIGO_OK = 0
CODIGO_DEPENDENCIAS_AUSENTES = 1
CODIGO_PYTHON_INCOMPATIVEL = 2
CODIGO_ERRO = 3

# No requirements.lock cada dependência abre uma linha na coluna zero; hashes e
# comentários de origem vêm indentados logo abaixo.
LINHA_TRAVADA = re.compile(r"^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?\s*==\s*([^\s\;]+)")


def interpretador_homologado() -> bool:
    return (
        sys.version_info.releaselevel == "final"
        and sys.version_info[:2] in SUPPORTED_VERSIONS
        and struct.calcsize("P") * 8 == 64
    )


def descricao_interpretador() -> str:
    return f"Python {sys.version.split()[0]} ({struct.calcsize('P') * 8} bits)"


def dependencias_travadas(lock_file: Path = LOCK_FILE) -> list[tuple[str, str]]:
    """Extrai os pares nome/versão fixados no arquivo de travas."""
    travadas: list[tuple[str, str]] = []
    for linha in lock_file.read_text(encoding="utf-8").splitlines():
        if not linha or linha[0].isspace() or linha.startswith("#"):
            continue
        correspondencia = LINHA_TRAVADA.match(linha)
        if correspondencia is not None:
            travadas.append((correspondencia.group(1), correspondencia.group(2)))
    return travadas


def conferir(
    travadas: list[tuple[str, str]],
) -> tuple[list[str], list[tuple[str, str, str]]]:
    """Separa o que não está instalado do que está em versão diferente da travada."""
    ausentes: list[str] = []
    divergentes: list[tuple[str, str, str]] = []
    for nome, esperada in travadas:
        try:
            instalada = version(nome)
        except PackageNotFoundError:
            ausentes.append(nome)
            continue
        if instalada != esperada:
            divergentes.append((nome, instalada, esperada))
    return ausentes, divergentes


def enumerar(nomes: list[str]) -> str:
    if len(nomes) <= MAXIMO_LISTADO:
        return ", ".join(nomes)
    restantes = len(nomes) - MAXIMO_LISTADO
    return f"{', '.join(nomes[:MAXIMO_LISTADO])} e mais {restantes}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Confere se as dependências de execução estão instaladas.",
    )
    parser.add_argument(
        "--somente-interpretador",
        action="store_true",
        help="Confere apenas se o Python em uso é homologado, sem checar pacotes.",
    )
    parser.add_argument(
        "--silencioso",
        action="store_true",
        help="Não imprime o relatório; devolve apenas o código de saída.",
    )
    parser.add_argument(
        "--travas",
        type=Path,
        default=LOCK_FILE,
        help="Arquivo de dependências travadas (padrão: requirements.lock).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    argumentos = parse_args(argv)

    def relatar(mensagem: str) -> None:
        if not argumentos.silencioso:
            print(mensagem)

    if not interpretador_homologado():
        relatar(
            f"  [X] {descricao_interpretador()} não é homologado: "
            "a aplicação exige Python 64 bits estável 3.12 ou 3.13."
        )
        return CODIGO_PYTHON_INCOMPATIVEL
    if argumentos.somente_interpretador:
        relatar(f"  [OK] {descricao_interpretador()} homologado.")
        return CODIGO_OK
    relatar(f"  [OK] {descricao_interpretador()} homologado.")

    try:
        travadas = dependencias_travadas(argumentos.travas)
    except OSError as excecao:
        relatar(f"  [X] Não foi possível ler {argumentos.travas.name}: {excecao}.")
        return CODIGO_ERRO
    except UnicodeError:
        relatar(f"  [X] O arquivo {argumentos.travas.name} não está em UTF-8.")
        return CODIGO_ERRO
    if not travadas:
        relatar(f"  [X] Nenhuma dependência declarada em {argumentos.travas.name}.")
        return CODIGO_ERRO

    ausentes, divergentes = conferir(travadas)
    if not ausentes and not divergentes:
        relatar(
            f"  [OK] As {len(travadas)} dependências estão instaladas "
            "nas versões homologadas."
        )
        return CODIGO_OK

    if ausentes:
        estao = "está instalada" if len(ausentes) == 1 else "estão instaladas"
        relatar(
            f"  [X] {len(ausentes)} de {len(travadas)} dependências não {estao}: "
            f"{enumerar(ausentes)}."
        )
    if divergentes:
        estao = "está" if len(divergentes) == 1 else "estão"
        detalhes = [
            f"{nome} {instalada} (esperada {esperada})"
            for nome, instalada, esperada in divergentes
        ]
        relatar(
            f"  [X] {len(divergentes)} de {len(travadas)} dependências {estao} em "
            f"versão divergente: {enumerar(detalhes)}."
        )
    return CODIGO_DEPENDENCIAS_AUSENTES


if __name__ == "__main__":
    raise SystemExit(main())
