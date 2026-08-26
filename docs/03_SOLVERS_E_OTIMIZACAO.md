# Solvers e otimização

## Pipeline comum

Os dois motores executam:

1. seleção e cópia da entrada;
2. validação;
3. carga do problema;
4. otimização;
5. auditoria independente;
6. escrita de resultados;
7. atualização do manifesto e status.

O hash da fonte é conferido antes e depois da cópia e novamente entre fases relevantes. Uma alteração inesperada gera falha de snapshot.

## Modelo matemático principal

Para cada oferta e docente elegível existe uma variável binária de atribuição. Cada oferta possui também uma variável binária de não alocação.

Restrição fundamental:

    soma das atribuições elegíveis + não alocada = 1

O modelo também possui:

- carga total por docente;
- carga por docente e etapa;
- indicador de docente utilizado;
- restrição de capacidade por etapa;
- limite total de duas disciplinas para Stricto;
- no máximo uma oferta por docente, etapa, dia e horário.

## Otimização lexicográfica

O CP-SAT resolve objetivos sequenciais. Após cada fase, o melhor valor é fixado como restrição da fase seguinte.

| Fase | Objetivo | Fração do tempo |
|---|---|---|
| 1 | Minimizar ofertas não alocadas | 0,30 / 0,26 |
| 2 | Maximizar docentes ativos utilizados | 0,25 / 0,22 |
| 3 | Maximizar score ponderado por CH_LETIVA | 0,20 / 0,17 |
| 4 | Minimizar não alocadas com candidato único | 0,15 / 0,13 |
| 5 | Maximizar alocações com perfil exato | — / 0,12 |
| Final | Canonicalizar por desempate de ótimo único | 0,10 / 0,10 |

A segunda fração vale quando a fase 5 está ativa. A fase 5 só existe no critério
CLUSTER_PREFERENCIAL; em PERFIL_EXATO e CLUSTER_PURO as frações permanecem
idênticas às da versão 1.0.

A fase 5 é executada depois de todos os ótimos de negócio estarem fixados como
restrição, portanto ela não pode reduzir cobertura, docentes utilizados, score
de CH nem proteção de candidato único. Ela apenas escolhe, entre soluções já
ótimas e empatadas, a de maior aderência de perfil. Seu status entra no conjunto
de fases exigidas: se ela não for provada ótima, a rodada não é publicada como
OPTIMAL.

A canonicalização mantém todos os ótimos fixados e resolve um desempate final
cujo ótimo é **único**: minimizar a soma, sobre as atribuições escolhidas, do
índice do docente multiplicado por um primo próprio de cada oferta.

O primo é o que garante a unicidade. Sem ele, duas ofertas trocando de docente
entre si se cancelariam e o total empataria; com ele, empatar exigiria que uma
combinação inteira de diferenças zerasse.

Como o ótimo é único, o determinismo passa a ser propriedade do **modelo**, e não
da busca: qualquer solver correto converge para a mesma solução, com qualquer
número de workers, qualquer semente e em qualquer máquina. Essa garantia é mais
forte que a da versão 1.0, que dependia de a fase final rodar com um único
worker e semente fixa.

A mudança também removeu um gargalo severo. Com os quatro ótimos fixados como
igualdades, um worker sozinho não encontrava sequer uma solução viável em
modelos grandes, porque perdia o portfólio de estratégias que o CP-SAT executa
em paralelo. No critério por cluster, a fase final passou de não terminar em
duas horas para concluir em segundos.

### Prova de canonicidade

A canonicidade pode ser verificada em tempo de execução: proíbe-se a solução
encontrada, exige-se o mesmo valor de desempate e pergunta-se ao solver se
existe outra. `INFEASIBLE` prova que a solução publicada é a única possível sob
os ótimos fixados.

A verificação é **opcional** porque custa mais que toda a otimização: no modelo
por cluster ela consome cerca de dez vezes o tempo das cinco fases somadas. O
campo `canonicity_proven` do manifesto tem três estados, e a distinção importa:

| Valor | Significado |
|---|---|
| `true` | a solução publicada é provadamente a única canônica |
| `false` | existe outra solução com o mesmo valor de desempate |
| `null` | a prova não foi pedida, ou não coube no orçamento |

O orçamento usa tempo **determinístico**, não de relógio: a prova é uma
atestação que vai para o manifesto, e um teto de relógio a tornaria
irreprodutível entre máquinas.

## Critério de elegibilidade

O critério escolhido na importação altera apenas o conjunto de candidatos de
cada oferta. Capacidade por etapa, limite Stricto, choque de horário, atividade
e função reconhecida continuam obrigatórios nos três métodos.

Como o conjunto de perfis de um cluster contém os perfis de cada oferta daquele
cluster, a elegibilidade por cluster é um superconjunto da elegibilidade por
perfil exato. Isso significa que trocar de PERFIL_EXATO para um método por
cluster nunca reduz a cobertura possível.

Ofertas com CLUSTER em branco permanecem restritas ao próprio perfil e são
listadas em `profile_fallback_offers` nos diagnósticos.

## Perfis de execução

O perfil traduz uma garantia de negócio em parâmetros de parada do CP-SAT.

| Perfil | Fase 1 | Fases 2 a 4 | Status exigido |
|---|---|---|---|
| PROVA_COMPLETA | prova, sem teto | prova, sem teto | OPTIMAL |
| COBERTURA_PROVADA | prova, sem teto | teto determinístico | COBERTURA_PROVADA |
| MARGEM_ACEITA | folga absoluta em ofertas | teto determinístico | OTIMO_COM_MARGEM |
| EXPLORACAO_RAPIDA | teto determinístico | teto determinístico | FEASIBLE |

Os tetos usam tempo **determinístico**, e não de relógio. Um teto de relógio
produziria resultados diferentes em máquinas diferentes, o que anularia a
reprodutibilidade que a canonicalização garante.

Uma rodada só é publicada quando entrega **ao menos** a garantia prometida pelo
perfil. Entregar mais é aceito: um resultado OPTIMAL satisfaz qualquer perfil.
Entregar menos é falha, ainda que a solução seja utilizável.

### Vocabulário de status

| Status | Significado |
|---|---|
| OPTIMAL | todas as fases exigidas foram provadas |
| COBERTURA_PROVADA | a cobertura máxima está provada; o desempate entre soluções de mesma cobertura, não |
| OTIMO_COM_MARGEM | a solução está, comprovadamente, a no máximo N ofertas do ótimo |
| FEASIBLE | solução utilizável, sem prova de otimalidade |

### O que o perfil não muda

Elegibilidade, capacidade por etapa, limite Stricto, choque de horário e a
auditoria independente são idênticos em todos os perfis. Uma rodada de
exploração rápida pode ser reprovada pela auditoria — e deve, se a solução
violar alguma regra.

## Status PARCIAL e OPTIMAL

São dimensões diferentes:

- PARCIAL indica que pelo menos uma oferta ficou sem alocação;
- OPTIMAL indica que o CP-SAT provou os melhores valores das fases exigidas.

Assim, uma solução PARCIAL e OPTIMAL é válida: há pendências, mas não existe solução com maior cobertura sob as regras atuais.

## Limite de tempo

Não há limite padrão. Quando configurado, o tempo é repartido entre as fases.

Sem a opção de permitir não ótimo, uma solução FEASIBLE não é publicada como resultado oficial concluído. A interface principal solicita prova ótima.

## Paralelismo e determinismo

Todas as fases, inclusive a canonicalização, usam vários workers. Até a versão
1.0 a fase final rodava com um único worker, porque o determinismo dependia da
ordem de busca. Isso deixou de ser necessário: o desempate canônico tem ótimo
único, então a mesma solução é obtida com qualquer número de workers e qualquer
semente.

Paralelismo melhora a busca, mas o tempo de parede varia conforme CPU, memória e
outras tarefas. A prova matemática e os valores objetivos são mais informativos
do que comparar apenas tempo de parede — e é por isso que os tetos dos perfis
usam tempo determinístico.

## GRASP

O GRASP é uma heurística opcional para construir uma solução inicial. Quando ativado:

- executa um número configurado de iterações;
- usa alpha e semente registrados;
- oferece hints ao CP-SAT;
- não substitui restrições, prova de ótimo ou auditoria.

Na configuração corrente da aplicação web, a execução padrão não exige GRASP. O CP-SAT permanece responsável pelo resultado final.

## Auditoria independente

A auditoria não confia apenas nos diagnósticos do solver. Ela reconstrói:

- quantidade de decisões;
- critério de elegibilidade declarado pelo solver, comparado com o critério
  auditado, gerando CRITERIO_DIVERGENTE quando diferem;
- compatibilidade de perfis segundo o critério vigente, gerando
  PERFIL_INCOMPATIVEL em PERFIL_EXATO e PERFIL_FORA_DO_CLUSTER nos métodos por
  cluster;
- contagem de alocações com perfil exato, comparada com a publicada pelo solver;
- status e função do docente;
- capacidade por etapa;
- limite Stricto;
- choques de horário;
- cargas totais e por etapa;
- contagens de docentes;
- motivos e status;
- valor do objetivo de não alocação.

Resultado reprovado não deve ser homologado.

## Publicação

Uma rodada concluída contém:

    rodada_###/
    ├── fonte/
    ├── validacao/
    ├── auditoria/
    ├── alocacao/
    ├── manifesto.json
    └── status.json

O manifesto usa caminhos relativos para os artefatos e registra tamanho e SHA-256.

## Motor de cenários

O motor secundário começa com as mesmas restrições acadêmicas do principal, mas recebe um snapshot de políticas.

Políticas suportadas pela experiência atual:

- ALOCAR_CLUSTER;
- PRIORIDADE;
- FIXAR.

Mudanças de campos são materializadas na cópia XLSX antes da otimização. Políticas são restrições ou extensões do solver e permanecem no arquivo de linhagem.

### Override de cluster

ALOCAR_CLUSTER amplia o conjunto de candidatos somente no cluster alvo. O par oferta-docente flexibilizado é registrado para que a auditoria do cenário não o confunda com compatibilidade exata.

Capacidade, atividade, função reconhecida, agenda e limite Stricto continuam obrigatórios.

### Prioridade

PRIORIDADE fixa a variável de não alocação em zero para o curso ou oferta. A política não cria capacidade nem elimina choque.

### Fixação

FIXAR obriga uma variável específica de atribuição a valer um. Se o par não existir no conjunto elegível, o cenário é rejeitado.

## Separação obrigatória

O backend chama:

- engines/primary/executar_pipeline.py para rodadas oficiais;
- engines/scenarios/executar_cenario.py para simulações.

O motor de Cenários nunca deve importar o solver principal em tempo de execução nem modificar seus arquivos. Uma promoção altera a referência oficial no banco, não o código do motor principal.

## Parâmetros auditáveis

Devem permanecer no manifesto ou nos diagnósticos:

- versão do pipeline;
- versão do schema de saída;
- versão do contrato de validação;
- módulo;
- critério de elegibilidade;
- alocações por perfil exato e por cluster;
- ofertas sem cluster que caíram no perfil exato;
- quantidade de workers;
- limite de tempo;
- exigência de ótimo;
- semente;
- iterações e alpha do GRASP;
- status de cada fase;
- tempo de CP-SAT e GRASP;
- score de capacidade;
- penalidade de candidato único;
- mapeamento de ORDEM para etapas;
- limite Stricto;
- fingerprints do código.

## Alterações que exigem homologação completa

- duração de uma transmissão;
- interpretação de ORDEM;
- capacidade ou limite Stricto;
- critérios de elegibilidade e a lista de métodos suportados;
- ordem ou fórmula dos objetivos;
- regra de choque;
- critérios de promoção;
- novos overrides no motor secundário;
- mudança de schema dos artefatos.

Nesses casos, solver, auditoria, reporting, testes e documentação devem ser revisados juntos.

