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

`scripts/anonimizar_base_demo.py` continua disponível para o caso em que só se
deseja mascarar pessoas, preservando o catálogo. Nenhum dos dois utilitários
substitui uma avaliação formal de privacidade sobre bases reais.

O roteiro recomendado está em `docs/08_QUALIDADE_E_HOMOLOGACAO.md`.
