"""Gera bases de demonstração com catálogo acadêmico inteiramente sintético.

O utilitário vai além do mascaramento de pessoas feito por
``anonimizar_base_demo.py``: substitui também o catálogo institucional
(código e nome de curso, currículo, código e nome de disciplina) por valores
inventados. O nome de curso segue o CLUSTER e o nome de disciplina segue a área
do PERFIL_DISCIPLINA, de modo que o catálogo continue coerente com as regras de
elegibilidade que a ferramenta demonstra.

O que é preservado, porque define o comportamento da ferramenta e não
identifica ninguém: CLUSTER, PERFIL_DISCIPLINA, MATRIZ, MÓD, ANO, ORDEM,
METODOLOGIA, FORMATO, ENTURMAÇÃO, SINERGIA, MODELO_CONTRATO, DIA_AULA,
HORÁRIO e as cargas horárias dos docentes.

As dependências funcionais exigidas pela validação são mantidas por
construção, porque o mapeamento é feito por valor distinto:
CURSO -> NOME_CURSO, CURSO -> CLUSTER, CURRÍCULO -> CURSO,
COD_DISCIPLINA -> NOME_DISCIPLINA, além da unicidade de
CURRÍCULO + COD_DISCIPLINA.

O resultado é determinístico: as mesmas origens produzem sempre as mesmas
substituições, e vários arquivos processados na mesma execução compartilham o
mesmo mapeamento, de modo que um curso mantém o nome sintético entre módulos.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from scripts.anonimizar_base_demo import (  # noqa: E402
    column_map,
    replace_badges,
    replace_distinct,
)

MAPA_SHEET = "MAPA PEDAGÓGICO"
DOCENTES_SHEET = "DOCENTES"

# Temas por cluster. Combinados com os sufixos e prefixos abaixo, cada cluster
# rende combinações suficientes para os catálogos reais sem repetição.
VOCABULARIO: dict[str, tuple[str, ...]] = {
    "AGRÁRIAS E MEIO AMBIENTE": (
        "PRODUÇÃO AGRÍCOLA", "MANEJO DO SOLO", "RECURSOS HÍDRICOS",
        "GESTÃO AMBIENTAL", "SUSTENTABILIDADE RURAL", "AGRICULTURA DE PRECISÃO",
        "CULTURAS PERENES", "FERTILIDADE E NUTRIÇÃO", "CONSERVAÇÃO DE BIOMAS",
        "SANIDADE VEGETAL", "LOGÍSTICA DO AGRONEGÓCIO", "ENERGIAS RENOVÁVEIS",
    ),
    "ALIMENTOS E BEBIDAS": (
        "TECNOLOGIA DE ALIMENTOS", "PROCESSOS DE BEBIDAS", "SEGURANÇA ALIMENTAR",
        "GASTRONOMIA APLICADA", "CONTROLE DE QUALIDADE ALIMENTAR",
        "PANIFICAÇÃO E CONFEITARIA", "CADEIA DO FRIO", "ANÁLISE SENSORIAL",
        "EMBALAGEM E CONSERVAÇÃO", "NUTRIÇÃO APLICADA",
        "FERMENTAÇÃO INDUSTRIAL", "GESTÃO DE COZINHAS",
    ),
    "ARTES E DESIGN": (
        "LINGUAGENS VISUAIS", "PRODUÇÃO ARTÍSTICA", "DESIGN DE SUPERFÍCIE",
        "ILUSTRAÇÃO DIGITAL", "CULTURA VISUAL", "CENOGRAFIA",
        "FOTOGRAFIA AUTORAL", "ANIMAÇÃO E MOVIMENTO", "DESIGN EDITORIAL",
        "ARTES INTEGRADAS", "MODELAGEM TRIDIMENSIONAL", "EXPRESSÃO GRÁFICA",
    ),
    "BEM-ESTAR": (
        "QUALIDADE DE VIDA", "PRÁTICAS INTEGRATIVAS",
        "ATIVIDADE FÍSICA APLICADA", "SAÚDE PREVENTIVA", "ESTÉTICA E CUIDADO",
        "TERAPIAS CORPORAIS", "NUTRIÇÃO E ESTILO DE VIDA",
        "GESTÃO DO ESTRESSE", "ERGONOMIA APLICADA", "PROMOÇÃO DA SAÚDE",
        "BEM-ESTAR OCUPACIONAL", "RECREAÇÃO E LAZER",
    ),
    "BEM-ESTAR ANIMAL": (
        "MANEJO ANIMAL", "ETOLOGIA APLICADA", "NUTRIÇÃO ANIMAL",
        "SANIDADE DE REBANHOS", "PRODUÇÃO PECUÁRIA", "CUIDADO DE PETS",
        "INSTALAÇÕES ZOOTÉCNICAS", "REPRODUÇÃO ANIMAL", "LEGISLAÇÃO ANIMAL",
        "ZOOTECNIA APLICADA", "CLÍNICA DE PEQUENOS ANIMAIS",
        "BIOSSEGURANÇA ANIMAL",
    ),
    "COMUNICAÇÃO": (
        "PRODUÇÃO DE CONTEÚDO", "MÍDIAS DIGITAIS", "NARRATIVAS AUDIOVISUAIS",
        "COMUNICAÇÃO ORGANIZACIONAL", "JORNALISMO DE DADOS",
        "PUBLICIDADE APLICADA", "RELAÇÕES PÚBLICAS", "ROTEIRO E EDIÇÃO",
        "COMUNICAÇÃO PÚBLICA", "BRANDING E REPUTAÇÃO", "RÁDIO E PODCAST",
        "ASSESSORIA DE IMPRENSA",
    ),
    "DESIGN": (
        "DESIGN GRÁFICO", "DESIGN DE PRODUTO", "EXPERIÊNCIA DO USUÁRIO",
        "DESIGN DE INTERIORES", "DESIGN DE MODA", "TIPOGRAFIA APLICADA",
        "PROTOTIPAGEM", "IDENTIDADE VISUAL", "DESIGN DE SERVIÇOS",
        "MATERIAIS E PROCESSOS", "DESIGN THINKING", "INTERFACES DIGITAIS",
    ),
    "EDUCAÇÃO": (
        "PRÁTICAS PEDAGÓGICAS", "GESTÃO ESCOLAR", "EDUCAÇÃO INCLUSIVA",
        "TECNOLOGIAS EDUCACIONAIS", "AVALIAÇÃO DA APRENDIZAGEM",
        "CURRÍCULO E DIDÁTICA", "EDUCAÇÃO INFANTIL",
        "PSICOLOGIA DA EDUCAÇÃO", "POLÍTICAS EDUCACIONAIS",
        "ALFABETIZAÇÃO E LETRAMENTO", "EDUCAÇÃO DE JOVENS E ADULTOS",
        "ORIENTAÇÃO EDUCACIONAL",
    ),
    "ENGENHARIAS": (
        "PROCESSOS INDUSTRIAIS", "MECÂNICA APLICADA", "SISTEMAS ELÉTRICOS",
        "MATERIAIS E ESTRUTURAS", "AUTOMAÇÃO INDUSTRIAL",
        "TERMODINÂMICA APLICADA", "ENGENHARIA DE PRODUÇÃO",
        "MANUTENÇÃO INDUSTRIAL", "CONTROLE E INSTRUMENTAÇÃO",
        "LOGÍSTICA INDUSTRIAL", "ENERGIA E EFICIÊNCIA",
        "SEGURANÇA DE PROCESSOS",
    ),
    "ENGENHARIAS E ARQUITETURA": (
        "PROJETO ARQUITETÔNICO", "ESTRUTURAS CIVIS", "CONFORTO AMBIENTAL",
        "URBANISMO APLICADO", "TOPOGRAFIA E GEOPROCESSAMENTO",
        "INSTALAÇÕES PREDIAIS", "PATOLOGIA DAS CONSTRUÇÕES",
        "PLANEJAMENTO DE OBRAS", "MATERIAIS DE CONSTRUÇÃO", "PAISAGISMO",
        "SANEAMENTO E INFRAESTRUTURA", "MODELAGEM DA INFORMAÇÃO",
    ),
    "EXATAS": (
        "CÁLCULO APLICADO", "ÁLGEBRA LINEAR", "PROBABILIDADE E ESTATÍSTICA",
        "FÍSICA GERAL", "QUÍMICA APLICADA", "GEOMETRIA ANALÍTICA",
        "MATEMÁTICA DISCRETA", "MÉTODOS NUMÉRICOS", "BIOESTATÍSTICA",
        "MATEMÁTICA FINANCEIRA", "PESQUISA OPERACIONAL", "MODELAGEM MATEMÁTICA",
    ),
    "HUMANAS": (
        "SOCIOLOGIA APLICADA", "FILOSOFIA CONTEMPORÂNEA", "ANTROPOLOGIA CULTURAL",
        "HISTÓRIA E SOCIEDADE", "PSICOLOGIA SOCIAL", "ÉTICA PROFISSIONAL",
        "CIÊNCIA POLÍTICA", "GEOGRAFIA HUMANA", "LEITURA E PRODUÇÃO TEXTUAL",
        "PENSAMENTO CONTEMPORÂNEO", "RELAÇÕES INTERPESSOAIS", "CULTURA E SOCIEDADE",
    ),
    "GESTÃO E NEGÓCIOS": (
        "GESTÃO EMPRESARIAL", "NEGÓCIOS DIGITAIS", "FINANÇAS CORPORATIVAS",
        "GESTÃO DE PESSOAS", "MARKETING ESTRATÉGICO", "LOGÍSTICA INTEGRADA",
        "EMPREENDEDORISMO", "CONTROLADORIA", "GESTÃO DA QUALIDADE",
        "COMÉRCIO EXTERIOR", "GESTÃO PÚBLICA", "ANÁLISE DE INVESTIMENTOS",
    ),
    "JURÍDICO": (
        "TEORIA DO DIREITO", "DIREITO PRIVADO", "DIREITO PÚBLICO",
        "PRÁTICA PROCESSUAL", "DIREITO DO TRABALHO", "DIREITO DIGITAL",
        "MEDIAÇÃO E ARBITRAGEM", "DIREITO EMPRESARIAL", "DIREITOS HUMANOS",
        "DIREITO TRIBUTÁRIO", "HERMENÊUTICA JURÍDICA", "DIREITO AMBIENTAL",
    ),
    "JURÍDICO E SEGURANÇA": (
        "SEGURANÇA PÚBLICA", "GESTÃO DE RISCOS", "CIÊNCIAS CRIMINAIS",
        "PERÍCIA E INVESTIGAÇÃO", "DIREITO PENAL APLICADO",
        "SEGURANÇA PRIVADA", "INTELIGÊNCIA E ANÁLISE", "DEFESA CIVIL",
        "LEGISLAÇÃO DE SEGURANÇA", "GESTÃO PENITENCIÁRIA", "CRIMINOLOGIA",
        "MEDIAÇÃO DE CONFLITOS",
    ),
    "LICENCIATURA": (
        "ENSINO DE LINGUAGENS", "ENSINO DE MATEMÁTICA", "ENSINO DE CIÊNCIAS",
        "ENSINO DE HISTÓRIA", "ENSINO DE GEOGRAFIA", "FORMAÇÃO DOCENTE",
        "ESTÁGIO SUPERVISIONADO", "LITERATURA E ENSINO", "ENSINO DE ARTES",
        "EDUCAÇÃO FÍSICA ESCOLAR", "ENSINO DE FILOSOFIA",
        "METODOLOGIAS DE ENSINO",
    ),
    "SAÚDE": (
        "FUNDAMENTOS CLÍNICOS", "SAÚDE COLETIVA", "ANATOMIA E FISIOLOGIA",
        "FARMACOLOGIA APLICADA", "ENFERMAGEM APLICADA",
        "DIAGNÓSTICO POR IMAGEM", "ANÁLISES CLÍNICAS",
        "URGÊNCIA E EMERGÊNCIA", "SAÚDE MENTAL", "REABILITAÇÃO FUNCIONAL",
        "EPIDEMIOLOGIA", "BIOSSEGURANÇA EM SAÚDE",
    ),
    "SAÚDE ANIMAL": (
        "CLÍNICA VETERINÁRIA", "PATOLOGIA ANIMAL", "FARMACOLOGIA VETERINÁRIA",
        "CIRURGIA DE PEQUENOS ANIMAIS", "DIAGNÓSTICO VETERINÁRIO",
        "SAÚDE PÚBLICA VETERINÁRIA", "PARASITOLOGIA ANIMAL",
        "ANESTESIOLOGIA VETERINÁRIA", "IMAGINOLOGIA ANIMAL",
        "NUTRIÇÃO CLÍNICA ANIMAL", "EMERGÊNCIA VETERINÁRIA",
        "EPIDEMIOLOGIA VETERINÁRIA",
    ),
    "SAÚDE E BEM-ESTAR": (
        "PROMOÇÃO DA SAÚDE", "CUIDADO INTEGRAL", "NUTRIÇÃO CLÍNICA",
        "FISIOTERAPIA APLICADA", "PSICOLOGIA DA SAÚDE", "ESTÉTICA APLICADA",
        "EDUCAÇÃO FÍSICA E SAÚDE", "SAÚDE DA FAMÍLIA", "GERONTOLOGIA",
        "TERAPIA OCUPACIONAL", "SAÚDE OCUPACIONAL", "PRÁTICAS DE CUIDADO",
    ),
    "TECNOLOGIA": (
        "DESENVOLVIMENTO DE SISTEMAS", "CIÊNCIA DE DADOS",
        "REDES E INFRAESTRUTURA", "SEGURANÇA DA INFORMAÇÃO",
        "COMPUTAÇÃO EM NUVEM", "INTELIGÊNCIA ARTIFICIAL", "BANCO DE DADOS",
        "ENGENHARIA DE SOFTWARE", "DEVOPS E AUTOMAÇÃO",
        "INTERNET DAS COISAS", "PROGRAMAÇÃO WEB", "ARQUITETURA DE SOFTWARE",
    ),
}

# Usado quando o cluster não está no catálogo acima e nas disciplinas de
# formação geral, que atravessam todos os cursos.
TEMAS_PADRAO: tuple[str, ...] = (
    "FORMAÇÃO GERAL", "PROJETO DE VIDA", "PENSAMENTO CRÍTICO",
    "COMUNICAÇÃO PROFISSIONAL", "ÉTICA E CIDADANIA", "EMPREGABILIDADE",
    "METODOLOGIA CIENTÍFICA", "DIVERSIDADE E INCLUSÃO", "SUSTENTABILIDADE",
    "INOVAÇÃO E CRIATIVIDADE", "PROJETO INTEGRADOR", "CULTURA DIGITAL",
)

# Conectores sem flexão de gênero, para que qualquer tema componha um nome
# gramaticalmente correto.
SUFIXOS_CURSO: tuple[str, ...] = (
    "", " E INOVAÇÃO", " E PROCESSOS", " E TECNOLOGIA", " E GESTÃO",
    " E PROJETOS", " E SUSTENTABILIDADE",
)

PREFIXOS_DISCIPLINA: tuple[str, ...] = (
    "FUNDAMENTOS DE", "TÓPICOS DE", "PRÁTICAS DE", "LABORATÓRIO DE",
    "SEMINÁRIOS DE", "PROJETO INTEGRADOR DE", "OFICINA DE", "ESTUDOS DE",
    "TÓPICOS AVANÇADOS DE", "METODOLOGIA DE", "PRINCÍPIOS DE", "ELEMENTOS DE",
    "ANÁLISE DE", "PLANEJAMENTO DE", "APLICAÇÕES DE", "TEORIAS DE",
)

# A área do PERFIL_DISCIPLINA decide o vocabulário da disciplina, para que o
# nome gerado continue coerente com o perfil exigido pela elegibilidade.
AREA_DE_PERFIL_PARA_VOCABULARIO: dict[str, str] = {
    "ALIMENTOS": "ALIMENTOS E BEBIDAS",
    "ARQUITETURA E URBANISMO": "ENGENHARIAS E ARQUITETURA",
    "ARTES": "ARTES E DESIGN",
    "CIÊNCIA DA INFORMAÇÃO": "TECNOLOGIA",
    "CIÊNCIA EXATA E DA TERRA": "EXATAS",
    "CIÊNCIAS AGRÁRIAS": "AGRÁRIAS E MEIO AMBIENTE",
    "CIÊNCIAS HUMANAS": "HUMANAS",
    "CIÊNCIAS SOCIAIS": "HUMANAS",
    "COMUNICAÇÃO": "COMUNICAÇÃO",
    "DESIGN": "DESIGN",
    "DIREITO": "JURÍDICO",
    "EDUCAÇÃO": "EDUCAÇÃO",
    "ENGENHARIA": "ENGENHARIAS",
    "ENGENHARIAS": "ENGENHARIAS",
    "EXATAS": "EXATAS",
    "EXATAS E AGRÁRIAS": "EXATAS",
    "EXATAS E DA TERRA": "EXATAS",
    "FINANÇAS E CONTABILIDADE": "GESTÃO E NEGÓCIOS",
    "GESTÃO": "GESTÃO E NEGÓCIOS",
    "HUMANAS": "HUMANAS",
    "SAÚDE": "SAÚDE",
    "TECNOLOGIA": "TECNOLOGIA",
}

VOCABULARIO_INSTITUCIONAL = "__INSTITUCIONAL__"


class GeracaoInsuficiente(RuntimeError):
    """O vocabulário acabou antes de cobrir todos os valores distintos."""


def _texto(valor: object) -> str:
    return str(valor or "").strip()


def _linhas_mapa(worksheet) -> list[dict[str, str]]:
    headers = column_map(worksheet)
    registros: list[dict[str, str]] = []
    for row in range(2, worksheet.max_row + 1):
        registro = {
            nome: _texto(worksheet.cell(row, coluna).value)
            for nome, coluna in headers.items()
        }
        if any(registro.values()):
            registro["__linha__"] = str(row)
            registros.append(registro)
    return registros


def _valor_dominante(contagem: Counter) -> str:
    # Empate resolvido pela ordem alfabética, para manter o resultado estável.
    return sorted(contagem.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _temas(cluster: str) -> tuple[str, ...]:
    return VOCABULARIO.get(cluster, TEMAS_PADRAO)


def _vocabulario_do_perfil(perfil: str) -> str:
    """Escolhe o vocabulário pela área do perfil exigido pela disciplina.

    PERFIL_DISCIPLINA pode trazer vários perfis separados por vírgula e uma
    hierarquia separada por ' - '. A área é o primeiro nível do primeiro perfil.
    """
    primeiro = perfil.split(",")[0].strip()
    area = primeiro.split(" - ")[0].strip().upper()
    if not area or area == "INSTITUCIONAL":
        return VOCABULARIO_INSTITUCIONAL
    return AREA_DE_PERFIL_PARA_VOCABULARIO.get(area, VOCABULARIO_INSTITUCIONAL)


def _nome_de_curso(cluster: str, indice: int) -> str:
    temas = _temas(cluster)
    combinacoes = len(temas) * len(SUFIXOS_CURSO)
    if indice >= combinacoes:
        raise GeracaoInsuficiente(
            f"vocabulário esgotado para cursos do cluster {cluster!r}: "
            f"{combinacoes} combinações para {indice + 1} nomes distintos"
        )
    tema = temas[indice % len(temas)]
    sufixo = SUFIXOS_CURSO[indice // len(temas)]
    return f"{tema}{sufixo}"


def _nome_de_disciplina(cluster: str, indice: int) -> str:
    temas = _temas(cluster)
    combinacoes = len(temas) * len(PREFIXOS_DISCIPLINA)
    if indice >= combinacoes:
        raise GeracaoInsuficiente(
            f"vocabulário esgotado para disciplinas do cluster {cluster!r}: "
            f"{combinacoes} combinações para {indice + 1} nomes distintos"
        )
    tema = temas[indice % len(temas)]
    prefixo = PREFIXOS_DISCIPLINA[indice // len(temas)]
    return f"{prefixo} {tema}"


def _preservar_grau(nome_original: str, tema: str) -> str:
    """Mantém o grau acadêmico do nome original e troca apenas a área."""
    if " EM " in nome_original:
        grau, _, _ = nome_original.partition(" EM ")
        return f"{grau} EM {tema}"
    return tema


class Catalogo:
    """Mapeamento determinístico do catálogo real para o catálogo sintético."""

    def __init__(self) -> None:
        # Contadores, e não valores únicos: a taxonomia de CLUSTER muda entre
        # módulos, então CURSO -> CLUSTER vale dentro de cada arquivo, não
        # entre arquivos. O nome sintético usa o cluster predominante.
        self.clusters_por_curso: dict[str, Counter] = {}
        self.cursos_por_curriculo: dict[str, Counter] = {}
        self.matriz_por_curriculo: dict[str, str] = {}
        self.clusters_por_nome_curso: dict[str, Counter] = {}
        self.perfis_por_nome_disciplina: dict[str, Counter] = {}
        # O vocabulário sintético usa termos acadêmicos correntes e pode
        # coincidir com o catálogo de origem. Guardamos os nomes originais
        # para descartar essas coincidências.
        self.nomes_originais: set[str] = set()

        self.cursos: dict[str, str] = {}
        self.nomes_de_curso: dict[str, str] = {}
        self.curriculos: dict[str, str] = {}
        self.disciplinas: dict[str, str] = {}
        self.nomes_de_disciplina: dict[str, str] = {}

    def coletar(self, registros: list[dict[str, str]]) -> None:
        # As dependências funcionais são verificadas dentro do arquivo, que é
        # o escopo em que a validação da ferramenta as exige.
        cluster_no_arquivo: dict[str, str] = {}
        curso_no_arquivo: dict[str, str] = {}
        for registro in registros:
            curso = registro.get("CURSO", "")
            cluster = registro.get("CLUSTER", "")
            curriculo = registro.get("CURRÍCULO", "")
            nome_curso = registro.get("NOME_CURSO", "")
            nome_disciplina = registro.get("NOME_DISCIPLINA", "")
            perfil = registro.get("PERFIL_DISCIPLINA", "")

            if curso and cluster:
                anterior = cluster_no_arquivo.setdefault(curso, cluster)
                if anterior != cluster:
                    raise ValueError(
                        f"CURSO {curso!r} aparece com CLUSTER {anterior!r} e {cluster!r} "
                        "no mesmo arquivo; a base viola CURSO -> CLUSTER e não "
                        "pode ser convertida"
                    )
                self.clusters_por_curso.setdefault(curso, Counter())[cluster] += 1
            if curriculo and curso:
                anterior = curso_no_arquivo.setdefault(curriculo, curso)
                if anterior != curso:
                    raise ValueError(
                        f"CURRÍCULO {curriculo!r} aparece com CURSO {anterior!r} e "
                        f"{curso!r} no mesmo arquivo; a base viola CURRÍCULO -> CURSO "
                        "e não pode ser convertida"
                    )
                self.cursos_por_curriculo.setdefault(curriculo, Counter())[curso] += 1
            if curriculo:
                self.matriz_por_curriculo.setdefault(
                    curriculo, registro.get("MATRIZ", "") or "0000"
                )
            if nome_curso:
                self.nomes_originais.add(nome_curso)
            if nome_disciplina:
                self.nomes_originais.add(nome_disciplina)
            if nome_curso and cluster:
                self.clusters_por_nome_curso.setdefault(nome_curso, Counter())[cluster] += 1
            if nome_disciplina:
                self.perfis_por_nome_disciplina.setdefault(
                    nome_disciplina, Counter()
                )[perfil] += 1

            codigo = registro.get("COD_DISCIPLINA", "")
            if codigo:
                self.disciplinas.setdefault(codigo, "")

    def construir(self) -> None:
        for indice, curso in enumerate(sorted(self.clusters_por_curso), start=1):
            self.cursos[curso] = f"CUR_{indice:03d}"

        for indice, codigo in enumerate(sorted(self.disciplinas), start=1):
            self.disciplinas[codigo] = f"DIS_{indice:04d}"

        usados_por_cluster: Counter = Counter()
        gerados: set[str] = set()
        for nome in sorted(self.clusters_por_nome_curso):
            cluster = _valor_dominante(self.clusters_por_nome_curso[nome])
            while True:
                tema = _nome_de_curso(cluster, usados_por_cluster[cluster])
                usados_por_cluster[cluster] += 1
                candidato = _preservar_grau(nome, tema)
                if candidato not in self.nomes_originais and candidato not in gerados:
                    break
            gerados.add(candidato)
            self.nomes_de_curso[nome] = candidato

        sequencias: Counter = Counter()
        for curriculo in sorted(self.cursos_por_curriculo):
            base = self.cursos[_valor_dominante(self.cursos_por_curriculo[curriculo])]
            matriz = self.matriz_por_curriculo.get(curriculo, "0000")
            chave = (base, matriz)
            sequencias[chave] += 1
            self.curriculos[curriculo] = f"{base}_{matriz}_{sequencias[chave]:02d}"

        usados_por_cluster = Counter()
        gerados = set()
        for nome in sorted(self.perfis_por_nome_disciplina):
            # O perfil predominante da disciplina define o vocabulário; assim o
            # nome gerado continua fazendo sentido diante do perfil exigido.
            perfil = _valor_dominante(self.perfis_por_nome_disciplina[nome])
            cluster = _vocabulario_do_perfil(perfil)
            while True:
                candidato = _nome_de_disciplina(cluster, usados_por_cluster[cluster])
                usados_por_cluster[cluster] += 1
                if candidato not in self.nomes_originais and candidato not in gerados:
                    break
            gerados.add(candidato)
            self.nomes_de_disciplina[nome] = candidato

def _aplicar(worksheet, catalogo: Catalogo) -> None:
    headers = column_map(worksheet)
    substituicoes = {
        "CURSO": catalogo.cursos,
        "NOME_CURSO": catalogo.nomes_de_curso,
        "CURRÍCULO": catalogo.curriculos,
        "COD_DISCIPLINA": catalogo.disciplinas,
        "NOME_DISCIPLINA": catalogo.nomes_de_disciplina,
    }
    for coluna_nome, mapeamento in substituicoes.items():
        coluna = headers.get(coluna_nome)
        if coluna is None:
            continue
        for row in range(2, worksheet.max_row + 1):
            cell = worksheet.cell(row, coluna)
            original = _texto(cell.value)
            if not original:
                continue
            cell.value = mapeamento.get(original, original)
            cell.number_format = "@"


def _limpar_metadados(workbook) -> None:
    for worksheet in workbook.worksheets:
        for row in worksheet.iter_rows():
            for cell in row:
                if cell.comment is not None:
                    cell.comment = None
                if cell.hyperlink is not None:
                    cell.hyperlink = None
    workbook.properties.creator = "Equipe de Alocação Docente"
    workbook.properties.lastModifiedBy = "Equipe de Alocação Docente"
    workbook.properties.title = "Base de demonstração sintética"
    workbook.properties.subject = "Demonstração pública da ferramenta"
    workbook.properties.description = (
        "Catálogo acadêmico e identificadores pessoais inteiramente sintéticos."
    )


def gerar(origens: list[Path], destinos: list[Path]) -> None:
    if len(origens) != len(destinos):
        raise ValueError("informe um --destino para cada --origem")

    catalogo = Catalogo()
    pastas: list = []
    try:
        for origem in origens:
            workbook = load_workbook(origem, keep_links=False)
            pastas.append(workbook)
            catalogo.coletar(_linhas_mapa(workbook[MAPA_SHEET]))

        catalogo.construir()

        for workbook, destino in zip(pastas, destinos):
            _aplicar(workbook[MAPA_SHEET], catalogo)
            replace_distinct(workbook[MAPA_SHEET], "COORDENADOR", "Coordenação")
            if DOCENTES_SHEET in workbook.sheetnames:
                replace_distinct(workbook[DOCENTES_SHEET], "NOME", "Docente")
                replace_badges(workbook[DOCENTES_SHEET])
                replace_distinct(workbook[DOCENTES_SHEET], "GESTOR", "Gestor")
            _limpar_metadados(workbook)
            destino.parent.mkdir(parents=True, exist_ok=True)
            workbook.save(destino)
    finally:
        for workbook in pastas:
            workbook.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gera bases de demonstração com catálogo acadêmico sintético. "
            "Processe todos os módulos na mesma execução para que compartilhem "
            "o mesmo mapeamento."
        )
    )
    parser.add_argument("--origem", type=Path, action="append", required=True)
    parser.add_argument("--destino", type=Path, action="append", required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    origens = [caminho.resolve() for caminho in arguments.origem]
    destinos = [caminho.resolve() for caminho in arguments.destino]
    gerar(origens, destinos)
    for destino in destinos:
        print(destino)
