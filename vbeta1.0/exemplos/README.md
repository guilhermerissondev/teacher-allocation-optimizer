# Bases de demonstração

`BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx` é uma base inteiramente sintética.
Além dos identificadores pessoais — nomes, chapas, gestores, coordenadores,
comentários, links e metadados —, o catálogo acadêmico também é inventado:
código e nome de curso, currículo, código e nome de disciplina não
correspondem a nenhum curso, disciplina ou instituição real.

O que foi preservado é o que faz a ferramenta se comportar como em produção:
cluster, perfil da disciplina, matriz, módulo, ano, ordem, metodologia,
formato, enturmação, sinergia, modelo de contrato, dia e horário de aula, além
das cargas horárias dos docentes. A rodada executada sobre esta base reproduz
as métricas registradas na homologação: 402 ofertas, 377 alocadas, 25 não
alocadas, 222 docentes utilizados, solver `OPTIMAL` e auditoria `APROVADO`.

O release não inclui resultados anteriores nem banco preenchido. A apresentação
começa com o upload dessa base e permite acompanhar todas as etapas reais.

O arquivo é o mesmo distribuído com a versão 2.0, o que torna as duas versões
comparáveis a partir da mesma entrada. Para regenerá-lo use
`scripts/gerar_base_demo_sintetica.py`, que acompanha a versão 2.0.
`scripts/anonimizar_base_demo.py`, incluído aqui, mascara apenas as pessoas e
preserva o catálogo. Nenhum dos dois substitui uma avaliação formal de
privacidade sobre bases reais.

O roteiro recomendado está em `docs/08_QUALIDADE_E_HOMOLOGACAO.md`.
