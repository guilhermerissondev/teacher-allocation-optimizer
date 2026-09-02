# API e dados

## Convenções

- Base local: http://127.0.0.1:8000
- Formato padrão: JSON
- Upload: multipart/form-data
- Downloads: XLSX, JSON ou artefato registrado
- Documentação interativa em desenvolvimento: /docs
- Erros usam o campo detail

Não há autenticação na vBeta 2.0. A API não deve ser exposta em rede.

## Endpoints de operação

| Método | Rota | Finalidade |
|---|---|---|
| GET | /api/health | Verificar API, motores e diretório de dados |
| POST | /api/uploads | Enviar e validar XLSX; aceita `module`, `criterion`, `profile` e `margin_offers` |
| GET | /api/uploads/{upload_id}/validation.xlsx | Baixar pendências de validação |
| POST | /api/jobs | Criar rodada principal |
| GET | /api/jobs | Listar rodadas principais |
| GET | /api/analysis-jobs | Listar resultados concluídos analisáveis |
| DELETE | /api/jobs/primary?scope=latest ou all | Excluir rodada-base |
| GET | /api/jobs/{job_id} | Consultar estado da execução |
| GET | /api/jobs/{job_id}/validation | Consultar validação |
| GET | /api/jobs/{job_id}/summary | Consultar resumo sem decisões detalhadas |
| GET | /api/jobs/{job_id}/allocations | Consultar decisões paginadas |
| GET | /api/jobs/{job_id}/artifacts/{artifact_key} | Baixar artefato |
| GET | /api/dashboard/{job_id} | Gerar Dashboard filtrado |
| GET | /api/insights/{job_id} | Gerar Insights |
| POST | /api/batches/inspect | Ler os módulos presentes em cada planilha enviada |
| POST | /api/batches | Criar lote: um upload validado por módulo escolhido |
| GET | /api/batches | Listar lotes |
| GET | /api/batches/{batch_id} | Consultar lote com progresso e KPIs por módulo |
| POST | /api/batches/{batch_id}/runs | Enfileirar as rodadas dos módulos liberados |
| DELETE | /api/batches/{batch_id} | Excluir o lote do histórico com as rodadas e cenários dele |

## Endpoints de Cenários

| Método | Rota | Finalidade |
|---|---|---|
| POST | /api/scenarios | Criar cenário |
| GET | /api/scenarios | Listar cenários |
| DELETE | /api/scenarios?scope=latest ou all | Excluir cenários |
| GET | /api/scenarios/{scenario_id} | Consultar cenário |
| GET | /api/scenarios/{scenario_id}/catalog | Listar ofertas, docentes, cursos e clusters da baseline |
| POST | /api/scenarios/{scenario_id}/changes/batch | Aplicar a mesma alteração a várias linhas |
| DELETE | /api/scenarios/{scenario_id}/changes/{change_id} | Remover alteração |
| POST | /api/scenarios/{scenario_id}/policies | Criar ou substituir política |
| DELETE | /api/scenarios/{scenario_id}/policies/{policy_id} | Remover política |
| POST | /api/scenarios/{scenario_id}/runs | Executar simulação |
| GET | /api/scenarios/{scenario_id}/comparison | Comparar cenário e baseline |
| POST | /api/scenarios/{scenario_id}/promote | Homologar cenário |

## Endpoints de Estudos em lote

Um estudo aplica a mesma premissa a vários módulos do ano. Ele não executa nada
por conta própria: projeta a premissa em um cenário filho por módulo e usa os
mesmos endpoints de simulação, comparação e homologação de cenários.

| Método | Rota | Finalidade |
|---|---|---|
| GET | /api/studies/baselines | Listar lotes com rodada concluída, elegíveis como base |
| POST | /api/studies | Criar estudo sobre um lote e um conjunto de módulos |
| GET | /api/studies | Listar estudos |
| GET | /api/studies/{study_id} | Consultar estudo com o estado de cada módulo |
| GET | /api/studies/{study_id}/catalog | Listar a base docente compartilhada pelos módulos |
| GET | /api/studies/{study_id}/projection | Ver o efeito de cada premissa em cada módulo |
| POST | /api/studies/{study_id}/premises | Criar premissa e reprojetar o estudo |
| DELETE | /api/studies/{study_id}/premises/{premise_id} | Remover premissa e reprojetar |
| POST | /api/studies/{study_id}/runs | Enfileirar a simulação de todos os módulos aptos |
| GET | /api/studies/{study_id}/comparison | Comparar módulo a módulo, cada um com a sua baseline |
| DELETE | /api/studies/{study_id} | Excluir o estudo e os cenários filhos |

### Premissas do estudo

O alvo é a chave de negócio, não a linha da planilha:

| premise_type | target_type | field_name | Entidade |
|---|---|---|---|
| CAPACIDADE | TEACHER_BADGE | STATUS, CH_LETIVA | DOCENTES |
| COMPATIBILIDADE | TEACHER_BADGE | PERFIL_DISCIPLINA | DOCENTES |
| AGENDA | COURSE, DISCIPLINE | DIA_AULA, HORÁRIO, ORDEM | MAPA PEDAGÓGICO |

`operation` é `SET` ou `ADJUST`, e `ADJUST` só se aplica a CH_LETIVA.

`target_values` é uma lista: cada alvo vira uma premissa, até 100 por
submissão e 50 por estudo. É o que permite mover três cursos de dia como uma
única operação.

A resposta da criação traz `study` e `projection`. A projeção informa, por
módulo, quantas linhas cada premissa alcançou e o motivo quando não alcançou
nenhuma — alvo ausente naquele módulo, valor já praticado ou CH acima do teto
contratado.

### Catálogo do estudo

`GET /api/studies/{id}/catalog` devolve os alvos possíveis. Os docentes vêm de
um módulo só, porque a base docente é comprovadamente idêntica entre eles.
Cursos e disciplinas são agregados de todos os módulos e trazem, por módulo,
quantas ofertas existem e quantas ficaram sem alocação na rodada-base — a
contagem que identifica o curso que vive com disciplina sem docente. O bloco
`practiced` lista os dias, horários e ordens efetivamente usados no ano.

### Resultado desatualizado

Cada módulo do estudo traz `stale`. Ele fica verdadeiro quando existe uma
simulação concluída cujas alterações não correspondem mais às premissas atuais;
nesse caso `kpis` vem nulo. Uma reprojeção que reescreve exatamente as mesmas
alterações não invalida a simulação.

### Homologação

Não existe rota de homologação de estudo. Cada módulo é homologado pelo cenário
filho, em `POST /api/scenarios/{scenario_id}/promote`, com os mesmos guardrails.

## Upload

Campos:

| Campo | Tipo | Regra |
|---|---|---|
| file | XLSX | Obrigatório, até 50 MB |
| module | inteiro | 51 a 54 |

O backend não aceita extensão diferente de XLSX. O arquivo é salvo como fonte.xlsx em diretório próprio.

## Criação de job

Corpo:

    {
      "upload_id": "identificador",
      "confirm_warnings": true,
      "require_optimal": true,
      "time_limit_seconds": null
    }

APROVADO_COM_RESSALVAS exige confirm_warnings. REPROVADO não pode seguir.

## Processamento em lote

Um lote executa vários módulos em uma operação, sem alterar o motor: cada
módulo vira uma rodada independente, validada e resolvida pelo mesmo pipeline.

Dois formatos de entrada são aceitos:

- **uma planilha por módulo** — o arquivo segue intacto para a validação;
- **uma planilha com vários módulos** — a coluna `MÓD` separa o arquivo em uma
  planilha por módulo antes da validação. `MAPA PEDAGÓGICO` fica só com as
  linhas daquele módulo e `DOCENTES` é copiada inteira, porque a aba não tem
  coluna de módulo e a capacidade é consumida dentro de cada módulo.

Regras do lote:

- cada módulo pedido precisa vir de exatamente uma planilha; duas origens para
  o mesmo módulo são recusadas, para não misturar bases sem o operador ver;
- um lote cobre no máximo `max_batch_modules` módulos (4 por padrão) e exige a
  fila do motor principal vazia;
- módulos reprovados na validação ficam registrados com o motivo e não são
  enfileirados; os demais seguem normalmente;
- ressalvas exigem confirmação explícita, como no envio individual;
- as rodadas correm em série, e cada módulo publica o seu próprio resultado
  oficial — o lote não cria um resultado combinado.

### Exclusão de um lote

`DELETE /api/batches/{batch_id}` remove o lote do histórico junto com o que ele
produziu: as rodadas do lote, os cenários construídos sobre elas e os uploads
que ficariam órfãos. Um upload ainda usado por outra rodada permanece.

A operação segue a mesma cascata do reset de rodadas-base, com quarentena antes
do commit e rollback se a remoção falhar no meio. Um lote com módulo na fila ou
em execução é recusado com `409`; um lote inexistente devolve `404`.

### Alteração de premissas nos Cenários

`POST /api/scenarios/{id}/changes/batch` é a única porta para registrar
alterações de campo. Ela aceita de 1 a 500 linhas, entrega os mesmos registros
que a rota individual entregava e aplica a mesma validação de alvo, por isso a
rota de linha única foi removida em vez de manter dois caminhos equivalentes.
Dois modos:

- `new_value` — o mesmo valor para todas as linhas selecionadas;
- `adjustment` — soma horas à `CH_LETIVA` de cada docente, preservando as
  diferenças de carga entre eles. Só se aplica a `CH_LETIVA`.

A resposta separa `applied` de `skipped`, e toda linha ignorada traz o motivo.
São ignoradas as linhas que já estão no valor pedido na rodada-base, as que
ficariam com carga negativa e as que passariam da `CH_CONTRATADA` — esta
última porque a validação reprova `CH_LETIVA` acima da contratada.


## Paginação

/allocations aceita:

- page, mínimo 1;
- page_size, entre 10 e 200;
- status;
- reason;
- search.

A busca percorre currículo, código e nome da disciplina, chapa e nome do docente.

## Filtros do Dashboard

Parâmetros repetíveis:

- order;
- day;
- time;
- cluster;
- course.

Exemplo conceitual:

    /api/dashboard/{job_id}?order=1ª&day=SEGUNDA&cluster=SAÚDE

## Artefatos

artifact_key pode ser:

- manifest;
- status;
- qualquer chave existente em manifesto.artifacts, como source_copy, validation_report, validation_issues, audit_report, allocation_workbook e allocation_summary.

O backend resolve o caminho relativo ao diretório da rodada e bloqueia traversal para fora dele.

## Banco SQLite

### uploads

Registra nome original, arquivo salvo, módulo, critério de elegibilidade,
perfil de execução, margem aceita, status e caminhos da validação.

O campo `profile` aceita PROVA_COMPLETA, COBERTURA_PROVADA, MARGEM_ACEITA ou
EXPLORACAO_RAPIDA. Bases criadas antes da versão 2.0 são migradas com
PROVA_COMPLETA, preservando a garantia com que foram produzidas.

### jobs

Registra status, mensagem, módulo, critério de elegibilidade, exigência de ótimo, limite de tempo, rodada, PID, código de saída, tipo PRIMARY ou SCENARIO e cenário relacionado.

O campo `criterion` aceita PERFIL_EXATO, CLUSTER_PREFERENCIAL ou CLUSTER_PURO. Bases criadas antes da versão 2.0 são migradas com PERFIL_EXATO e preservam o comportamento anterior.

### scenarios

Registra baseline, nome, descrição, status e data de promoção.

### scenario_changes

Mantém uma alteração por cenário, entidade, linha e campo. Valores anterior e novo são serializados em JSON.

### scenario_policies

Mantém uma política por cenário, tipo, alvo e valor.

### scenario_runs

Relaciona cenário, job, planilha materializada e snapshot de alterações.

### scenario_studies

Registra lote-base, nome, descrição, status e os módulos escolhidos. Excluir o
lote exclui os estudos construídos sobre ele.

### scenario_study_premises

Mantém uma premissa por estudo, tipo, alvo e campo. O alvo é a chapa do docente,
e não a linha da planilha: ao fatiar a base anual por módulo, a linha muda de
lugar e a mesma premissa passaria a significar coisas diferentes em cada recorte.

### scenario_study_modules

Liga cada módulo do estudo à sua rodada-base e ao cenário filho projetado.
Remover o cenário filho remove o módulo do estudo; um estudo sem módulos é
descartado, porque já não descreve comparação alguma.

### official_results

Mantém um resultado oficial por módulo.

## Contrato da entrada

### MAPA PEDAGÓGICO

Campos esperados:

1. CURSO
2. NOME_CURSO
3. CURRÍCULO
4. COD_DISCIPLINA
5. NOME_DISCIPLINA
6. PERFIL_DISCIPLINA
7. MATRIZ
8. MÓD
9. ANO
10. ORDEM
11. VALIDADO
12. METODOLOGIA
13. FORMATO
14. PROVA
15. ENTURMAÇÃO
16. PERFIL
17. CLUSTER
18. COORDENADOR
19. MODELO_CONTRATO
20. SINERGIA
21. DIA_AULA
22. HORÁRIO
23. FORMATO_AULA

### DOCENTES

Campos esperados:

1. NOME
2. CHAPA
3. NM_FUNCAO
4. CH_CONTRATADA
5. CH_LETIVA
6. GESTOR
7. STATUS
8. PERFIL_DISCIPLINA

CHAPA deve ser única. Cargas devem ser inteiros não negativos.

## Saída

A planilha final inclui abas de ALOCACOES, DOCENTES e DOCENTES POR CARGO. O resumo JSON contém métricas e decisões usadas pela API.

DOCENTES POR CARGO é a abertura da utilização docente derivada de DOCENTES: cada cargo (NM_FUNCAO) abre nos regimes de contratação (T40, T20, T12..., com sufixo Mensalista no contrato Stricto) e a aba fecha em Total Geral. Traz headcount, CH contratada, CH letiva alocável, CH alocada e utilização por etapa e de pico. A CH letiva alocável é a soma da coluna `CH_LETIVA_ALOCÁVEL` da aba DOCENTES — a CH letiva arredondada para baixo ao múltiplo de uma transmissão —, e é ela que serve de denominador. Cargos sem CH letiva alocável registram NSA no lugar do percentual.

Campos críticos da decisão:

- linha e identificadores da oferta;
- etapa, agenda, cluster e curso;
- status;
- docente e chapa quando alocada;
- contrato calculado;
- quantidade de candidatos;
- motivo da não alocação;
- motivo da alocação.

## Integridade

- fórmulas em campos de dados são bloqueadas pela validação;
- a fonte é copiada antes do processamento;
- hashes são verificados entre fases;
- artefatos possuem tamanho e SHA-256;
- rodadas não são sobrescritas;
- downloads são limitados ao diretório da rodada.

## Evolução de schema

O manifesto possui schema_version. Mudanças incompatíveis devem:

1. incrementar a versão;
2. preservar leitura das rodadas ainda suportadas;
3. atualizar API, frontend, testes e documentação;
4. definir migração do SQLite quando necessário.

