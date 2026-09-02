# Regras de negócio

## Fonte e escopo

A rodada recebe uma planilha XLSX com as abas MAPA PEDAGÓGICO e DOCENTES. Os cabeçalhos são validados por nome; a ordem física das colunas pode variar.

A interface aceita módulos 51, 52, 53 e 54. Em cada execução, somente registros do módulo selecionado participam do problema.

## Ofertas consideradas

O solver trabalha apenas com linhas que atendem simultaneamente:

- SINERGIA igual a Curso Único ou Curso Responsável;
- FORMATO_AULA igual a AO VIVO;
- módulo igual ao módulo selecionado.

Linhas sinérgicas permanecem informativas e não são ofertas do problema. O catálogo de Cenários também é limitado às ofertas efetivamente presentes na rodada-base; não deve exibir todo o mapa pedagógico.

O grão esperado é CURRÍCULO + COD_DISCIPLINA. Cada oferta mantém sua linha de origem para rastreabilidade.

## Duração e etapas

Cada transmissão representa 2 horas semanais. O módulo é dividido em duas etapas de cinco semanas.

| ORDEM | Primeira etapa | Segunda etapa |
|---|---:|---:|
| 1ª | 2 h | 0 h |
| 2ª | 0 h | 2 h |
| ESTENDIDA | 2 h | 2 h |

ORDEM é a fonte canônica para a etapa. METODOLOGIA pode gerar alerta de divergência, mas não redefine a etapa no solver.

Uma oferta de 1ª e outra de 2ª podem reutilizar a mesma capacidade e o mesmo horário porque não ocorrem na mesma etapa. ESTENDIDA ocupa as duas.

## Cluster como referência da candidatura

A aba DOCENTES aceita uma coluna **CLUSTER**, com os grupos em que o docente
atua, separados por vírgula. Ela é opcional: bases anteriores ao contrato 2.4
não a trazem e continuam valendo.

Quando a base declara o cluster do docente, ele passa a ser a referência dos
métodos por cluster: a candidatura compara o cluster do docente com o da
oferta, diretamente. Sem essa coluna, o motor mantém a regra anterior — expande
os perfis aceitos pela oferta para a **união dos perfis de todas as ofertas do
cluster** e compara pelo perfil.

A diferença importa quando a taxonomia de perfil está incompleta: pela união de
perfis, um perfil que aparece em dois clusters costura os dois num grupo só, e a
candidatura atravessa fronteiras que a coordenação não reconhece. Pelo cluster
declarado isso não acontece.

Três regras seguem valendo nos dois modos:

- oferta **sem** CLUSTER não forma grupo e continua restrita ao próprio perfil;
- `PERFIL_EXATO` ignora o cluster por completo, dos dois lados;
- `CLUSTER_PREFERENCIAL` difere de `CLUSTER_PURO` apenas no desempate, que
  favorece a aderência exata de perfil entre soluções já ótimas — a candidatura
  é a mesma.

A coluna `BASE_ELEGIBILIDADE` da aba ALOCACOES distingue os caminhos:
`PERFIL_EXATO`, `CLUSTER_DECLARADO` (pelo cluster do docente) e `CLUSTER`
(pela união de perfis do cluster).

## Carga do docente na planilha de resultado

A `CH_LETIVA` é um teto **semanal**, então a comparação acontece dentro de cada
metade de cinco semanas, nunca contra a soma do módulo. A aba DOCENTES declara
isso por etapa, em vez de colapsar as duas numa única coluna:

| Bloco | Colunas |
| --- | --- |
| Capacidade | CH_CONTRATADA, CH_LETIVA, CH_LETIVA_ALOCÁVEL |
| Composição por ordem | QTD_1ª_ORDEM, QTD_2ª_ORDEM, QTD_ESTENDIDA, QTD_TRANSMISSÕES |
| 1ª etapa (semanas 1–5) | QTD_DISCIPLINAS_1ª_ETAPA, CH_ALOCADA_1ª_ETAPA, CH_DISPONÍVEL_1ª_ETAPA, UTILIZAÇÃO_1ª_ETAPA |
| 2ª etapa (semanas 6–10) | QTD_DISCIPLINAS_2ª_ETAPA, CH_ALOCADA_2ª_ETAPA, CH_DISPONÍVEL_2ª_ETAPA, UTILIZAÇÃO_2ª_ETAPA |
| Consolidado | CH_ALOCADA_PICO, CH_DISPONÍVEL, UTILIZAÇÃO_PICO, EXCEDE_CH_LETIVA |

`QTD_DISCIPLINAS_1ª_ETAPA` soma as de 1ª ordem com as ESTENDIDA; a de 2ª etapa
soma as de 2ª ordem com as ESTENDIDA. Em `QTD_TRANSMISSÕES` a ESTENDIDA conta
uma vez só, porque é uma disciplina, ainda que ocupe as duas metades.

### CH letiva alocável

`CH_LETIVA` guarda o valor da base. `CH_LETIVA_ALOCÁVEL` é o teto que a
alocação alcança de fato: como cada transmissão consome um bloco fixo de horas
semanais, a sobra que não fecha um bloco não tem como ser ocupada. Um regente
de 12h contratadas com 9h letivas recebe no máximo quatro disciplinas de 2h —
8h — e a nona hora fica ociosa por construção.

**Folgas e percentuais usam a alocável**, não a `CH_LETIVA`. Manter a fração no
divisor fazia todo o corpo docente parecer menos ocupado do que o modelo
permite. O solver não muda com isso: a restrição de inteiros já produzia o mesmo
piso, e o conjunto de soluções viáveis é idêntico — o que muda é o denominador
dos relatórios.

`CH_ALOCADA_PICO` é a maior das duas etapas: é ela que se compara com a
`CH_LETIVA_ALOCÁVEL`, e `CH_DISPONÍVEL` é a folga garantida nas dez semanas.
`EXCEDE_CH_LETIVA` marca `SIM` quando alguma etapa ultrapassa o teto, `NSA`
para docentes Stricto — que preservam `CH_LETIVA` zero e usam um limite próprio
de disciplinas por módulo — e `NAO` no restante. O indicador correspondente na
aba RESUMO é **Docentes acima da CH_LETIVA em alguma etapa**.

## Critério de elegibilidade

A partir da versão 2.0, o critério é escolhido explicitamente na tela de
importação, junto com o módulo, e vale para toda a rodada.

| Critério | Perfis aceitos na candidatura | Desempate por perfil exato |
|---|---|---|
| PERFIL_EXATO | Os perfis da própria oferta | não se aplica |
| CLUSTER_PREFERENCIAL | Os perfis de todas as ofertas do cluster | sim |
| CLUSTER_PURO | Os perfis de todas as ofertas do cluster | não |

O conjunto de perfis de um cluster é a união dos perfis de todas as ofertas
alocáveis daquele cluster. Como a própria oferta pertence ao seu cluster, a
candidatura por cluster **contém** a candidatura por perfil exato: nenhum
docente elegível por perfil deixa de ser elegível por cluster.

Consequência: CLUSTER_PREFERENCIAL e CLUSTER_PURO têm o mesmo conjunto de
candidatos e, portanto, a mesma cobertura, os mesmos docentes utilizados e o
mesmo score de CH. Eles só diferem em qual das soluções empatadas é publicada.

### Ofertas sem cluster

Uma oferta com CLUSTER em branco não forma grupo. Nos dois métodos por cluster
ela permanece avaliada pelo próprio perfil, porque agregar todas as linhas sem
cluster produziria um conjunto sem significado pedagógico. As linhas nessa
condição são registradas no diagnóstico da rodada.

### Efeito sobre a validação

O relatório de pendências acompanha o critério escolhido:

| Critério | PERFIL_SEM_DOCENTE_ATIVO |
|---|---|
| PERFIL_EXATO | ressalva ALTA quando não há docente ativo de perfil compatível |
| CLUSTER_PREFERENCIAL | ALTA apenas quando não há candidato nem pelo cluster; havendo cluster e não perfil exato, emite OFERTA_COBERTA_APENAS_POR_CLUSTER com severidade BAIXA |
| CLUSTER_PURO | ALTA apenas quando não há candidato pelo cluster; o perfil exato não gera ocorrência |

### Efeito sobre Cenários

O cenário herda obrigatoriamente o critério da rodada-base, porque comparar
rodadas de critérios diferentes mediria duas regras e não uma mudança de
premissa. Quando a baseline já usa um método por cluster, a política
ALOCAR_CLUSTER é recusada por ser redundante.

## Perfil de execução

Além do módulo e do critério, a importação define **qual garantia** a rodada
deve entregar. O perfil não altera nenhuma restrição acadêmica nem o que a
auditoria reconfere: ele governa apenas quanta prova de otimalidade é exigida.

| Perfil | Garante | Vira oficial |
|---|---|---|
| Prova completa | todas as fases provadas ótimas | **sim** |
| Cobertura provada | não existe alocação com mais cobertura; desempates limitados no tempo | não |
| Margem aceita | solução comprovadamente a no máximo N ofertas do melhor possível | não |
| Exploração rápida | nenhuma garantia de otimalidade | não |

O padrão é **Prova completa**, que reproduz o comportamento das versões
anteriores.

### Por que a margem é medida em ofertas

O objetivo da primeira fase é uma contagem de ofertas não alocadas. Uma folga
absoluta de 2 significa, literalmente, que a solução está no máximo duas ofertas
abaixo da melhor possível — e isso está provado, não estimado.

### Somente prova completa vira referência oficial

Perfis que abrem mão de prova aceleram a exploração, mas não podem ser
promovidos. O resultado oficial de um módulo não pode certificar menos do que
certificava antes. Um cenário só é promovível quando ele e sua rodada-base
usaram Prova completa.

### O cenário herda o perfil da baseline

Pela mesma razão que herda o critério: comparar uma baseline provada com um
cenário limitado no tempo mediria dois regimes de garantia, e não uma mudança
de premissa.

## Candidatura e alocação

Um docente entra na lista básica de candidatos quando:

- está ATIVO;
- possui função reconhecida;
- possui pelo menos um perfil compatível após normalização, conforme o critério
  escolhido: os perfis da oferta em PERFIL_EXATO, ou os perfis do cluster nos
  dois métodos por cluster;
- possui capacidade para ao menos uma transmissão;
- a oferta possui dia e horário utilizáveis.

A decisão final também precisa respeitar:

- capacidade em cada etapa;
- limite específico de Stricto;
- ausência de choque no mesmo dia, horário e etapa;
- políticas adicionais, somente quando o motor de cenários é usado.

Perfis separados por vírgula são alternativas. Não há correspondência parcial
por texto em nenhum dos critérios; o que muda entre eles é apenas o conjunto de
perfis considerado aceitável para a oferta.

## Funções reconhecidas

| NM_FUNCAO | Família |
|---|---|
| PROFESSOR DE ENSINO SUPERIOR EAD | EAD interno |
| PROFESSOR REGENTE | EAD interno |
| PROFESSOR DE ENSINO SUPERIOR PRESENCIAL | Stricto/presencial |

Outras funções não recebem alocação.

## Regra Stricto/presencial

No solver, PROFESSOR DE ENSINO SUPERIOR PRESENCIAL pode receber no máximo duas disciplinas distintas no módulo. Com 2 horas por transmissão, a capacidade operacional especial é de 4 horas para a decisão do solver.

Essa regra é aplicada mesmo quando CH_LETIVA está zerada na fonte. A planilha original não é reescrita para simular carga; a exceção existe no domínio, no solver e na auditoria.

O limite é por módulo, não por etapa. Duas disciplinas na primeira e duas na segunda excederiam o máximo de duas.

## Capacidade exibida no Dashboard

O Dashboard aplica a mesma regra de CH letiva alocável descrita acima, com uma
diferença de escopo:

- usa a CH_LETIVA registrada para todos os docentes ativos, inclusive presencial;
- considera apenas horas que formam transmissões completas;
- arredonda para baixo ao múltiplo de 2.

Exemplo: CH_LETIVA de 9 horas contribui com 8 horas de capacidade utilizável.

Até a revisão de setembro/2026 esse arredondamento existia só no Dashboard, e a
aba DOCENTES dividia pela `CH_LETIVA` cheia. As duas superfícies reportavam
capacidades diferentes para o mesmo corpo docente. Hoje a soma de
`CH_LETIVA_ALOCÁVEL` da planilha e a capacidade ativa do Dashboard coincidem.

Essa capacidade é bruta. Ela não é reduzida por perfil, agenda ou cluster. Por isso, o delta de capacidade é um sinal gerencial e não uma prova de que todas as horas podem cobrir qualquer disciplina.

O solver principal continua usando sua própria regra de elegibilidade e, para Stricto, o limite de duas disciplinas. Não se deve usar o KPI do Dashboard como substituto da restrição do solver.

## Choque de horário

Há choque quando o mesmo docente é escolhido para duas ofertas com:

- mesmo dia;
- mesmo horário;
- pelo menos uma etapa em comum.

Dia NSA ou horário inválido impede a candidatura daquela oferta e deve aparecer como agenda inválida.

## Objetivos de negócio

O solver principal preserva a seguinte ordem:

1. minimizar ofertas não alocadas;
2. maximizar docentes ativos com alguma alocação;
3. favorecer alocações em docentes de maior CH_LETIVA;
4. proteger ofertas com exatamente um candidato elegível;
5. somente em CLUSTER_PREFERENCIAL, maximizar as alocações com perfil exato;
6. escolher uma solução canônica entre empates.

Uma prioridade posterior nunca pode piorar o ótimo fixado nas anteriores.

## Motivos da decisão

Para oferta alocada, MOTIVO_ALOCACAO descreve por que o docente foi escolhido.

Para oferta não alocada, MOTIVO deve distinguir pelo menos:

- AGENDA_INVALIDA;
- SEM_DOCENTE_COM_PERFIL_E_CARGA;
- CAPACIDADE_LETIVA_ESGOTADA;
- CHOQUE_DE_HORARIO;
- CAPACIDADE_E_HORARIO_COMBINADOS.

O número de candidatos elegíveis também é publicado.

## Contrato publicado

MODELO_CONTRATO na entrada é aceito apenas por compatibilidade e não influencia o solver.

| Docente selecionado | MODELO_CONTRATO de saída |
|---|---|
| Professor EAD ou Professor Regente | CLT EAD |
| Professor presencial | CLT STRICTO |
| Sem alocação | A DEFINIR |

MODELO_CONTRATO_ORIGEM não integra o contrato publicado.

## Filtros do Dashboard

A ordem visual é:

1. ORDEM;
2. DIA;
3. HORÁRIO;
4. CLUSTER;
5. CURSO.

Dentro do mesmo filtro, várias escolhas são combinadas por OU. Entre filtros diferentes, aplica-se E.

Todos os clusters devem aparecer no gráfico de demanda; não existe agregação em Outros.

## Regras de Cenários

Um cenário parte obrigatoriamente de uma rodada principal concluída.

### Reforçar ou reduzir capacidade

Permite alterar, na cópia:

- STATUS do docente;
- CH_LETIVA do docente.

### Reorganizar agenda

Permite alterar, na oferta:

- DIA_AULA;
- HORÁRIO;
- ORDEM.

### Ampliar compatibilidade

Permite alterar PERFIL_DISCIPLINA de docente ou oferta.

### Alocar docentes do cluster

Para um cluster escolhido, o motor secundário pode recuperar uma oferta mesmo sem compatibilidade exata de perfil quando:

- o docente está ativo;
- possui função reconhecida;
- possui capacidade;
- não possui choque;
- tem ao menos um perfil presente no conjunto de perfis daquele cluster.

É uma flexibilização de negócio, não uma nova regra do solver oficial. A auditoria do cenário reconhece e registra esse override.

### Proteger prioridades acadêmicas

Curso ou oferta marcada como prioridade não pode ficar sem cobertura no cenário. Se as demais restrições tornarem isso impossível, o cenário falha em vez de publicar uma solução inconsistente.

### Fixar decisões

Preserva a alocação da baseline para uma oferta e recalcula o restante. A fixação só é aceita para o docente efetivamente alocado e ainda elegível.

## Comparação e homologação

A comparação apresenta, entre outros:

- cobertura da baseline e do cenário;
- variação de ofertas alocadas e não alocadas;
- variação de docentes usados;
- variação de horas internas e externas;
- diferença por etapa;
- trocas de docente e status por oferta.

Um cenário só pode ser promovido quando:

- sua validação é aceitável;
- todas as fases lexicográficas exigidas são OPTIMAL;
- a auditoria é APROVADO;
- a execução foi concluída.

Há um único resultado oficial por módulo. Promover outro cenário substitui a referência oficial, sem apagar os artefatos anteriores.

## Exclusão de rodadas e cenários

Os controles permitem excluir somente o último item ou todos.

- Zerar cenários remove os cenários escolhidos e suas execuções.
- Zerar rodadas-base remove a rodada escolhida, seu upload e cenários dependentes.
- Nenhuma exclusão é permitida enquanto um item afetado estiver QUEUED ou RUNNING.

A ação é destrutiva e exige confirmação na interface.

## Regras do estudo em lote

Um estudo aplica a mesma premissa a vários módulos do ano letivo. Ele é
orquestração, e não uma segunda regra de negócio: cada módulo vira um cenário
independente, resolvido, auditado e comparado pelo mesmo caminho de sempre.

### Os módulos são independentes

Cada módulo é resolvido separadamente, e a CH letiva do docente é reposta
integralmente em cada um. Demitir alguém "a partir do módulo 51" significa
aplicar a mesma premissa aos módulos 51 a 54 e ler o efeito em cada um; não há
consumo acumulado de capacidade de um módulo para o seguinte.

### O alvo é a chave de negócio

A premissa aponta para a chapa do docente, o código do curso ou o da disciplina
— nunca para a linha da planilha. O recorte por módulo copia a aba DOCENTES
inteira e filtra o MAPA PEDAGÓGICO, de modo que a linha de uma oferta muda de
módulo para módulo. Amarrar a premissa ao número da linha faria a mesma pergunta
significar coisas diferentes em cada recorte: "mover o curso ADM para quarta" só
é a mesma pergunta no ano inteiro quando o alvo é o curso.

Um alvo pode não existir em algum módulo — uma disciplina que só é ofertada no
primeiro semestre, por exemplo. O módulo é reportado sem efeito, com o motivo, e
fica fora da fila.

### A base docente precisa ser a mesma

O estudo só é criado quando todas as rodadas-base escolhidas compartilham a
mesma aba DOCENTES, verificada por impressão digital. Bases divergentes fariam a
mesma chapa apontar para pessoas diferentes, e a comparação entre módulos
deixaria de responder à pergunta feita.

### A projeção é reescrita por inteiro

Criar ou remover uma premissa reprojeta o estudo do zero em cada módulo editável.
É o que garante que apagar uma premissa apague exatamente o que ela havia
produzido, sem rastrear a origem de cada célula. Módulos já homologados ou em
simulação são preservados e reportados como tal.

### Recusas são individuais e explícitas

Uma premissa pode valer em um módulo e cair em outro: o valor já é o praticado,
a CH passaria do teto contratado ou o alvo não existe ali. A recusa é registrada
com o motivo, por módulo, e nunca aplicada em silêncio.

### Homologação módulo a módulo

O estudo não homologa nada por conta própria. Cada módulo é homologado pelo seu
cenário filho, sob os mesmos guardrails: validação aprovada, solver ÓTIMO,
auditoria aprovada, mesmo critério da baseline e perfil de prova completa.

### Resultado desatualizado não é resultado

Quando as premissas mudam, a simulação já calculada deixa de responder à
pergunta que está na tela. O módulo passa a ser exibido como desatualizado e os
seus indicadores somem até a nova execução. É a proteção contra o erro mais
perigoso da ferramenta: ler a cobertura da simulação anterior como se fosse a
resposta da premissa nova.

Uma reprojeção que reescreve exatamente as mesmas alterações não invalida nada,
porque a planilha materializada seria idêntica.

### Escopo desta versão

O estudo em lote cobre capacidade, compatibilidade e agenda. As políticas de
cluster e de prioridade seguem disponíveis apenas no cenário de um módulo.
Fixar decisões é por oferta individual e não tem chave que atravesse módulos com
significado.

Uma premissa de agenda alcança as ofertas que o solver trata naquele módulo, que
são as mesmas que o cenário de um módulo oferece para edição. Linhas de apoio —
sinérgicas e não ao vivo — não são movidas junto, exatamente como já acontece no
fluxo de um módulo.
