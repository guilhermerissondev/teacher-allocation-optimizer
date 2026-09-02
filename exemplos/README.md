# Bases de demonstração

`BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx` e
`BASE_DEMONSTRACAO_ANONIMIZADA_M53.xlsx` são bases inteiramente sintéticas.
Além dos identificadores pessoais — nomes, chapas, gestores, coordenadores,
comentários, links e metadados —, o catálogo acadêmico também é inventado:
código e nome de curso, currículo, código e nome de disciplina não
correspondem a nenhum curso, disciplina ou instituição real.

O que foi preservado é o que faz a ferramenta se comportar como em produção:
cluster, perfil da disciplina, matriz, módulo, ano, ordem, metodologia,
formato, enturmação, sinergia, modelo de contrato, dia e horário de aula, além
das cargas horárias dos docentes. Os nomes gerados seguem o cluster do curso e
a área do perfil da disciplina, de modo que a elegibilidade continue legível.

A equivalência foi verificada: a rodada executada sobre a base sintética produz
resumo de alocação, auditoria e relatório de validação idênticos aos da base de
origem — 402 ofertas, 377 alocadas, 25 não alocadas, 222 docentes utilizados,
solver `OPTIMAL` e auditoria `APROVADO`.

O release não inclui resultados anteriores nem banco preenchido. A apresentação
começa com o upload dessa base e permite acompanhar todas as etapas reais.

Para regenerar as planilhas, processe todos os módulos na mesma execução para
que compartilhem o mesmo mapeamento:

```powershell
python .\scripts\gerar_base_demo_sintetica.py `
  --origem <origem_m52.xlsx> --destino .\exemplos\BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx `
  --origem <origem_m53.xlsx> --destino .\exemplos\BASE_DEMONSTRACAO_ANONIMIZADA_M53.xlsx
```

## Base para o processamento em lote

`BASE_DEMONSTRACAO_ANONIMIZADA_LOTE_ANUAL.xlsx` cobre o outro formato que a
aplicação aceita: uma planilha anual, com vários módulos na mesma aba, que o
lote separa por `MÓD` antes de validar. As duas bases acima continuam servindo
ao formato de uma planilha por módulo.

| Módulo | Ofertas | Linhas do mapa | Cursos |
|---:|---:|---:|---:|
| 51 | 204 | 420 | 107 |
| 52 | 204 | 335 | 57 |
| 53 | 204 | 340 | 57 |
| 54 | 204 | 309 | 58 |

São 1.404 linhas e 433 docentes em uma única aba `DOCENTES` — que é como uma
exportação anual real se apresenta, já que a aba não tem coluna de módulo. A
capacidade continua sendo consumida dentro de cada módulo separadamente.

A base é derivada das duas anteriores, e não de dados novos. Duas correções
foram necessárias ao juntá-las, e valem como aviso para quem for repetir o
procedimento:

- **elas foram anonimizadas em execuções separadas**, então o mesmo `CUR_001`
  designava cursos diferentes e 167 chapas colidiam apontando para pessoas
  distintas. Sem reidentificar, as dependências `CURSO -> NOME_CURSO` e
  `CURSO -> CLUSTER` ficariam inconsistentes e a validação reprovaria;
- **as duas numeram os docentes a partir de 001**, o que duplicaria metade dos
  nomes. O quadro combinado é renumerado em série contínua.

Cluster e perfil da disciplina permanecem compartilhados de propósito: são
vocabulários institucionais, e é o que faz o critério por cluster ter sentido
sobre o corpo docente inteiro.

Cada curso fica inteiro em um módulo só, para que os filtros por curso e por
cluster continuem significando alguma coisa dentro de cada rodada. Nenhuma
oferta é duplicada.

Rodada de referência do lote, com perfil da disciplina e prova completa:

| Módulo | Alocadas | Cobertura | Solver | Auditoria |
|---:|---:|---:|---|---|
| 51 | 200 de 204 | 98,0% | OPTIMAL | APROVADO |
| 52 | 203 de 204 | 99,5% | OPTIMAL | APROVADO |
| 53 | 202 de 204 | 99,0% | OPTIMAL | APROVADO |
| 54 | 204 de 204 | 100,0% | OPTIMAL | APROVADO |

Consolidado: 809 de 816 ofertas, 99,1%, os quatro módulos em 26 segundos. A
cobertura é mais alta que a das bases de módulo único porque o corpo docente
combinado atende a módulos menores; o objetivo aqui é demonstrar o fluxo do
lote, não reproduzir a escassez de uma rodada real.

Para regenerar:

```powershell
python .\scripts\gerar_base_demo_lote.py
```

`scripts/anonimizar_base_demo.py` continua disponível para o caso em que só se
deseja mascarar pessoas, preservando o catálogo. Nenhum dos dois utilitários
substitui uma avaliação formal de privacidade sobre bases reais.

O roteiro recomendado está em `docs/08_QUALIDADE_E_HOMOLOGACAO.md`.
