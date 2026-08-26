"""Audita o contraste WCAG da interface nos temas claro e escuro.

Mede apenas pares que a folha de estilo realmente produz:

1. pares explicitos — uma mesma regra define `color` e `background` a partir de
   tokens, como nos selos de status, botoes e cartoes de indicador;
2. pares ambientais — cada tinta de texto contra as superficies de pagina, que
   sao o fundo herdado quando a regra nao declara um.

Limiares WCAG 2.1: 4.5:1 para texto normal, 3:1 para texto grande e para
elementos graficos. O script sai com codigo 1 se algum par real ficar abaixo
de 4.5, para poder ser usado como portao de verificacao.
"""
from __future__ import annotations

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
CSS = RAIZ / "frontend" / "src" / "styles.css"

# Tokens que carregam texto e, portanto, respondem ao limiar de 4.5.
TINTAS_TEXTO = {
    "--ink", "--ink-soft", "--muted", "--faint", "--accent", "--info",
    "--success", "--warning", "--critical", "--neutral", "--brand-primary",
}

# Tokens cuja superficie e, por definicao, escura nos dois temas. Eles nao sao
# medidos contra as superficies de pagina, e sim contra o fundo em que de fato
# aparecem, senao a auditoria reportaria uma falha que nao existe.
TINTAS_SOBRE_ESCURO = {"--brand-accent": "--brand-dark", "--on-dark": "--brand-dark",
                       "--on-accent": "--accent"}
SUPERFICIES_PAGINA = ["--ground", "--surface", "--surface-sunken", "--surface-raised"]

# Tokens de superficie, filete e lavagem. Nenhum deles pode colorir texto: a
# razao de contraste contra o proprio fundo fica perto de 1:1 e o texto some.
# Esta checagem existe porque um `color: var(--line)` passou despercebido pela
# medicao de pares — a regra declarava tinta sem declarar fundo.
TOKENS_NAO_TEXTUAIS = {
    "--line", "--line-strong", "--grid", "--ground", "--surface",
    "--surface-sunken", "--surface-raised", "--accent-wash", "--accent-edge",
    "--info-soft", "--success-soft", "--warning-soft", "--critical-soft",
    "--neutral-soft", "--tone-soft",
}


def rel_lum(cor: str) -> float:
    h = cor.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    canais = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canais]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contraste(a: str, b: str) -> float:
    alto, baixo = sorted((rel_lum(a), rel_lum(b)), reverse=True)
    return (alto + 0.05) / (baixo + 0.05)


def tokens_de(bloco: str) -> dict[str, str]:
    return dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;", bloco))


def temas(css: str) -> tuple[dict[str, str], dict[str, str]]:
    base = css.split("@media (prefers-color-scheme: dark)")[0]
    escuro_bloco = css.split(':root[data-theme="dark"] {')[1].split("\n}")[0]
    claro = tokens_de(base)
    escuro = dict(claro)
    escuro.update(tokens_de(escuro_bloco))
    return claro, escuro


def pares_explicitos(css: str) -> list[tuple[str, str, str]]:
    """Regras que declaram tinta e fundo juntas: o par e inequivoco."""
    corpo = css.split("/* ── Base ")[1]
    achados: list[tuple[str, str, str]] = []
    for seletor, corpo_regra in re.findall(r"([^{}]+)\{([^{}]*)\}", corpo):
        tinta = re.search(r"(?<!-)color\s*:\s*var\((--[a-z0-9-]+)\)", corpo_regra)
        fundo = re.search(r"background(?:-color)?\s*:\s*var\((--[a-z0-9-]+)\)", corpo_regra)
        if tinta and fundo:
            achados.append((seletor.strip().split("\n")[-1][:58], tinta.group(1), fundo.group(1)))
    return achados


def texto_com_token_de_superficie(css: str) -> list[tuple[str, str]]:
    """Regras que pintam texto com um token que nao e de tinta."""
    corpo = css.split("/* ── Base ")[1]
    achados: list[tuple[str, str]] = []
    for seletor, corpo_regra in re.findall(r"([^{}]+)\{([^{}]*)\}", corpo):
        for tinta in re.findall(r"(?<!-)color\s*:\s*var\((--[a-z0-9-]+)\)", corpo_regra):
            if tinta in TOKENS_NAO_TEXTUAIS:
                achados.append((seletor.strip().split("\n")[-1][:58], tinta))
    return achados



# Tokens desenhados para MARCA de grafico. Tinta de texto e marca de grafico
# tem limiares diferentes: texto precisa de 4.5:1 de contraste, marca precisa
# de croma minimo e separacao para daltonismo. Usar um no lugar do outro
# produz barras acinzentadas ou fora da banda de luminosidade.
TOKENS_DE_SERIE = {"--series-1", "--series-2", "--tone", "--grid"}


def series_divergentes(css: str) -> list[str]:
    """Legenda e marca da mesma serie precisam ler o mesmo token.

    O amostrador da legenda e a barra do grafico costumam ser declarados em
    lugares diferentes da folha. Quando um e reestilizado e o outro nao, a
    legenda passa a descrever cores que o grafico nao usa — foi o que
    aconteceu com o grafico por dia, cuja legenda mostrava dois teais quase
    iguais enquanto as barras eram teal e laranja.

    A comparacao e restrita: so entra a classe que aparece tanto num seletor
    de legenda quanto num seletor de marca. Comparar toda classe repetida
    acusaria variacao legitima — hover, tom, estado — e o portao viraria ruido.
    """
    corpo = css.split("/* ── Base ")[1]
    MARCAS = ("day-bars", "coverage-track", "bar-track", "cluster-bar-track",
              "stage-coverage-track", "diagnostic-track")
    na_legenda: dict[str, str] = {}
    na_marca: dict[str, str] = {}
    for seletor, regra in re.findall(r"([^{}]+)\{([^{}]*)\}", corpo):
        fundo = re.search(r"background(?:-color)?\s*:\s*var\((--[a-z0-9-]+)\)", regra)
        if not fundo:
            continue
        for parte in seletor.split(","):
            classes = re.findall(r"\.([a-z][\w-]*)", parte)
            if len(classes) < 2:
                continue
            alvo = classes[-1]
            if "legend" in parte:
                na_legenda[alvo] = fundo.group(1)
            elif any(m in parte for m in MARCAS):
                na_marca[alvo] = fundo.group(1)

    problemas: list[str] = []
    for classe in sorted(set(na_legenda) & set(na_marca)):
        if na_legenda[classe] != na_marca[classe]:
            problemas.append(
                f".{classe}: legenda usa {na_legenda[classe]} "
                f"mas a marca usa {na_marca[classe]}"
            )
    return problemas


def marcas_com_token_de_texto(css: str) -> list[str]:
    """Marca de grafico pintada com token de tinta de texto."""
    corpo = css.split("/* ── Base ")[1]
    suspeitas = ("legend", "day-bars", "coverage-track", "bar-track", "donut")
    achados: list[str] = []
    for seletor, regra in re.findall(r"([^{}]+)\{([^{}]*)\}", corpo):
        sel = seletor.strip().split("\n")[-1]
        if not any(s in sel for s in suspeitas):
            continue
        fundo = re.search(r"background(?:-color)?\s*:\s*var\((--[a-z0-9-]+)\)", regra)
        if fundo and fundo.group(1) in TINTAS_TEXTO:
            achados.append(f"{sel[:56]} usa {fundo.group(1)}, que e tinta de texto")
    return achados


def fundo_herdado(css: str, tema: dict[str, str]) -> list[tuple[float, str]]:
    """Texto cuja regra declara so a cor e herda o fundo do elemento pai.

    A medicao de pares explicitos exige tinta e fundo na MESMA regra. O caso que
    escapa dela e o mais traicoeiro: `.cartao.destaque` pinta o fundo escuro e
    `.cartao.destaque > span` pinta so a cor, herdando aquele fundo. Foi assim
    que o indicador de cobertura ficou com contraste 1.64 no tema claro — tinta
    de superficie clara sobre cartao escuro.

    O ancestral e resolvido por prefixo de seletor, que cobre as formas usadas
    nesta folha: descendente e filho direto.
    """
    corpo = css.split("/* ── Base ")[1]
    regras = re.findall(r"([^{}]+)\{([^{}]*)\}", corpo)

    fundos: dict[str, str] = {}
    for seletor, regra in regras:
        m = re.search(r"background(?:-color)?\s*:\s*var\((--[a-z0-9-]+)\)", regra)
        if not m:
            continue
        for parte in seletor.split(","):
            fundos[" ".join(parte.split())] = m.group(1)

    def ancestral(seletor: str) -> str | None:
        partes = re.split(r"\s*>\s*|\s+", " ".join(seletor.split()))
        while len(partes) > 1:
            partes = partes[:-1]
            for candidato in (" > ".join(partes), " ".join(partes)):
                if candidato in fundos:
                    return fundos[candidato]
        return None

    achados: list[tuple[float, str]] = []
    for seletor, regra in regras:
        if re.search(r"background(?:-color)?\s*:", regra):
            continue
        tinta = re.search(r"(?<!-)color\s*:\s*var\((--[a-z0-9-]+)\)", regra)
        if not tinta:
            continue
        for parte in seletor.split(","):
            parte = " ".join(parte.split())
            token_fundo = ancestral(parte)
            if not token_fundo:
                continue
            if tinta.group(1) not in tema or token_fundo not in tema:
                continue
            razao = contraste(tema[tinta.group(1)], tema[token_fundo])
            if razao < 4.5:
                achados.append(
                    (razao, f"{parte[:44]}  [{tinta.group(1)} sobre {token_fundo} herdado]")
                )
    return achados


def auditar() -> int:
    css = CSS.read_text(encoding="utf-8")
    claro, escuro = temas(css)
    explicitos = pares_explicitos(css)

    divergentes = series_divergentes(css)
    if divergentes:
        print(f"\n{'=' * 72}\nLEGENDA DIVERGENTE DA MARCA\n{'=' * 72}")
        for aviso in divergentes:
            print(f"  [FALHA ]  {aviso}")

    marcas = marcas_com_token_de_texto(css)
    if marcas:
        print(f"\n{'=' * 72}\nMARCA DE GRAFICO COM TOKEN DE TEXTO\n{'=' * 72}")
        for aviso in marcas:
            print(f"  [FALHA ]  {aviso}")

    indevidos = texto_com_token_de_superficie(css)
    if indevidos:
        print(f"\n{'=' * 72}\nTEXTO COM TOKEN DE SUPERFICIE\n{'=' * 72}")
        for seletor, tinta in indevidos:
            print(f"  [FALHA ]  {seletor}  usa {tinta} como cor de texto")

    falhas = len(indevidos) + len(divergentes) + len(marcas)
    for nome, tema in (("CLARO", claro), ("ESCURO", escuro)):
        print(f"\n{'=' * 72}\nTEMA {nome}\n{'=' * 72}")
        problemas: list[tuple[float, str]] = []

        for seletor, tinta, fundo in explicitos:
            if tinta not in tema or fundo not in tema:
                continue
            razao = contraste(tema[tinta], tema[fundo])
            if razao < 4.5:
                problemas.append((razao, f"{seletor}  [{tinta} sobre {fundo}]"))

        for tinta, fundo in sorted(TINTAS_SOBRE_ESCURO.items()):
            if tinta in tema and fundo in tema:
                razao = contraste(tema[tinta], tema[fundo])
                if razao < 4.5:
                    problemas.append((razao, f"(par fixo)  [{tinta} sobre {fundo}]"))

        problemas.extend(fundo_herdado(css, tema))

        for tinta in sorted(TINTAS_TEXTO):
            if tinta not in tema:
                continue
            for sup in SUPERFICIES_PAGINA:
                if sup not in tema:
                    continue
                razao = contraste(tema[tinta], tema[sup])
                if razao < 4.5:
                    problemas.append((razao, f"(ambiente)  [{tinta} sobre {sup}]"))

        problemas.sort()
        for razao, descricao in problemas:
            nivel = "FALHA" if razao < 3.0 else "abaixo"
            print(f"  [{nivel:6s}] {razao:5.2f}  {descricao}")
        if not problemas:
            print("  nenhum par real abaixo de 4.5:1")
        falhas += len(problemas)

    print(f"\npares explicitos analisados: {len(explicitos)}")
    print(f"total de pares reais abaixo de 4.5: {falhas}")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(auditar())
