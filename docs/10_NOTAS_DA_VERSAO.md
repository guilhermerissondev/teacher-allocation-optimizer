# Notas da versão

## Ferramenta de Alocação Docente 2.0.0

Status: release técnica para produção local mono-usuário em Windows.

Esta versão transforma o critério de elegibilidade, antes fixo em perfil exato,
em uma escolha explícita do usuário na tela de importação.

### CH letiva alocável como denominador da utilização

A aba DOCENTES ganhou a coluna **CH_LETIVA_ALOCÁVEL**, e folgas e percentuais
passaram a usá-la no lugar da `CH_LETIVA` cheia.

O motivo é de modelagem. Cada transmissão consome um bloco fixo de horas
semanais, então a fração que não fecha um bloco nunca esteve disponível: um
regente de 12h contratadas com 9h letivas recebe no máximo quatro disciplinas de
2h. As 8h são o teto real, e dividir a carga pelas 9h fazia o corpo docente
inteiro parecer menos ocupado do que o modelo permite. Na base de demonstração,
o regime T12 do Professor Regente cai de 774h para 688h de capacidade e a
utilização de pico sobe de 40,83% para 45,93%.

O arredondamento já existia no Dashboard desde a vBeta 1.0, mas só lá: a
planilha e a tela reportavam capacidades diferentes para o mesmo corpo docente
— 1.294h contra 1.208h na base de demonstração. Agora coincidem.

**O resultado da alocação não muda.** A restrição de inteiros do solver já
produzia o mesmo piso, então o conjunto de soluções viáveis é idêntico; o que
muda é o denominador dos relatórios. `EXCEDE_CH_LETIVA` também mantém o valor,
porque uma carga só ultrapassa a alocável quando já ultrapassava a contratada.
Índices que leem a utilização da aba DOCENTES — o score de risco e a mediana de
pico em Insights — sobem junto, e alguns docentes podem mudar de faixa de risco.

### Abertura por cargo na planilha de saída

A planilha final ganhou a aba **DOCENTES POR CARGO**, derivada da aba DOCENTES.
Ela reproduz a abertura de utilização docente do relatório semanal: cada cargo
abre nos regimes de contratação (T40, T20, T12..., com sufixo Mensalista no
contrato Stricto) e a tabela fecha em Total Geral, com headcount, CH contratada,
CH letiva alocável, CH alocada e utilização.

Como o motor apura o módulo inteiro e não um período isolado, a aba traz as
métricas das duas etapas e do pico, em vez de escolher uma delas. Cargos sem CH
letiva alocável — o contrato Stricto — registram NSA no lugar do percentual, e
não um denominador zerado.

### Cluster declarado no docente (contrato 2.4)

A aba DOCENTES passou a aceitar a coluna **CLUSTER**. Quando a base a informa,
ela vira a referência dos métodos por cluster, no lugar da união dos perfis das
ofertas do cluster.

O motivo é de fidelidade: a regra anterior fazia a candidatura por cluster
depender da qualidade da taxonomia de perfil. Um perfil presente em dois
clusters unia os dois num grupo só, e o docente virava candidato a ofertas de
uma área que a coordenação não reconhece como sua.

A coluna é opcional e a mudança é compatível: base sem ela produz exatamente o
mesmo resultado de antes. `PERFIL_EXATO` não foi afetado, e a distinção entre
`CLUSTER_PURO` e `CLUSTER_PREFERENCIAL` continua sendo só de desempate.
`BASE_ELEGIBILIDADE` ganhou o valor `CLUSTER_DECLARADO` para separar os dois
caminhos na auditoria.

### Revisão de apresentação e saída (agosto/2026)

Rodada de correções concentrada na camada de apresentação. O motor de
otimização — solver, auditoria e critérios de elegibilidade — não foi alterado.

**Carga docente por etapa.** A aba DOCENTES colapsava as duas metades do módulo
numa média, o que gravava 1 h para uma disciplina de 2 h sempre que ela ocupava
uma etapa só. As colunas passaram a declarar cada etapa separadamente, com
`CH_ALOCADA_PICO` para a comparação com a `CH_LETIVA` e `EXCEDE_CH_LETIVA` como
sinal de governança. O solver já impunha o teto por etapa; o defeito era só do
relatório. O indicador "Horas semanais médias no módulo" saiu da aba RESUMO,
substituído por "Docentes acima da CH_LETIVA em alguma etapa".

**Seleção de rodada.** O rótulo das opções concatenava contexto, módulo,
critério, perfil, rodada, data e arquivo, passava de 140 caracteres e era
cortado em todas as abas — problema que o processamento em lote agravou, por
gerar rodadas que só se distinguem pelo módulo. Um componente único passou a
mostrar apenas o que distingue as rodadas, agrupadas pelo lote de origem, com o
contexto completo numa legenda abaixo do campo.

**Cenários.** A divisão entre aplicar a uma entidade e aplicar em lote deixou de
existir: um só formulário atende os dois casos. Todos os alvos e filtros viraram
listas suspensas com busca e seleção múltipla, e os filtros passaram a se
restringir mutuamente, oferecendo apenas os valores ainda disponíveis. Campos que
eram de texto livre — perfil da disciplina — e de digitação numérica — CH letiva
— passaram a listar os valores praticados na base, com contagem.

**Insights.** A severidade e o texto dos cartões passaram a sair dos números da
rodada. Antes a cor vinha do assunto do cartão e a orientação era fixa, de modo
que uma rodada com cobertura completa ainda mandava atacar lacunas inexistentes.

**Exclusão de lote.** `DELETE /api/batches/{id}` remove um lote do histórico com
a mesma cascata e as mesmas proteções do reset de rodadas-base.

**Rota removida.** `POST /api/scenarios/{id}/changes` saiu: a rota em lote aceita
uma linha, aplica a mesma validação e devolve os mesmos registros.

**Suíte da interface.** O frontend passou a ter testes automatizados (Vitest e
Testing Library), integrados ao `scripts/testar.ps1`. A lógica de filtros
cruzados, seleção múltipla e rótulos de rodada deixou de depender apenas de
conferência visual.

**Diagnóstico de versão.** A barra lateral exibe o carimbo do build, para
distinguir numa olhada uma página servida do cache de uma recém-publicada.

### Critério de elegibilidade selecionável

- três métodos: PERFIL_EXATO, CLUSTER_PREFERENCIAL e CLUSTER_PURO;
- o padrão permanece PERFIL_EXATO, reproduzindo integralmente a versão 1.0;
- a candidatura por cluster usa a união dos perfis das ofertas do cluster e é,
  por construção, um superconjunto da candidatura por perfil exato;
- CLUSTER_PREFERENCIAL acrescenta uma quinta fase lexicográfica que desempata as
  soluções já ótimas em favor da aderência exata de perfil, sem alterar
  cobertura, docentes utilizados ou score de CH;
- ofertas com CLUSTER em branco permanecem restritas ao próprio perfil.

### Validação

- contrato 2.2 para 2.3;
- PERFIL_SEM_DOCENTE_ATIVO passa a considerar o critério selecionado;
- novo código informativo OFERTA_COBERTA_APENAS_POR_CLUSTER, severidade BAIXA,
  emitido apenas em CLUSTER_PREFERENCIAL;
- o critério é registrado nos metadados e nas premissas do relatório.

### Auditoria

- a compatibilidade de perfil é reconferida sob o critério vigente;
- novo código PERFIL_FORA_DO_CLUSTER para os métodos por cluster;
- novo código CRITERIO_DIVERGENTE quando o critério declarado pelo solver difere
  do critério auditado;
- novo código ADERENCIA_PERFIL_INCONSISTENTE quando a contagem de alocações com
  perfil exato diverge das atribuições;
- audit.checks passa a publicar critério e o split perfil exato versus cluster.

### Resultados publicados

- schema de saída 2 para 3;
- nova coluna BASE_ELEGIBILIDADE na aba ALOCACOES;
- novas linhas de critério e split no RESUMO;
- resumo_alocacao.json ganha eligibility_criterion, exact_profile_allocations,
  cluster_profile_allocations e eligibility_basis por decisão.

### Cenários

- o cenário herda obrigatoriamente o critério da rodada-base;
- a comparação expõe baseline_criterion, scenario_criterion e same_criterion, e
  a promoção exige critérios iguais;
- a política ALOCAR_CLUSTER é recusada quando a baseline já usa cluster, por ser
  redundante;
- policies.py e o critério de importação passam a compartilhar uma única
  definição de perfis do cluster.

### Compatibilidade

- as colunas criterion de uploads e jobs são criadas por migração automática com
  o valor PERFIL_EXATO, portanto rodadas anteriores continuam legíveis e mantêm
  o comportamento com que foram produzidas;
- o diretório operacional passou a ser a pasta data da própria instalação,
  identificada automaticamente; dados gravados por versões anteriores continuam
  em %LOCALAPPDATA%\UniCesumar\AlocacaoDocente\vbeta1.0 e a aplicação informa
  esse caminho na inicialização enquanto ele existir;
- MANIFESTO_RELEASE.json e o build do frontend precisam ser regerados.

### Interface

- navegação migrada das abas superiores para um trilho lateral fixo;
- tema claro e escuro com alternador Claro/Escuro/Auto, persistido no navegador;
- toda cor da interface passou a vir de tokens: nenhuma cor literal permanece
  fora dos blocos de tema, o que era a condição para o tema escuro funcionar;
- tipografia em três papéis: Sora nos títulos, Source Sans 3 no texto e IBM Plex
  Mono nos dados, com fontes servidas da própria pasta;
- par de cores das séries dos gráficos validado para protanopia e deuteranopia
  nos dois temas;
- estado deixou de depender apenas de cor: os selos ganharam marcador de forma;
- novo `scripts/construir_frontend.ps1`, que compila a interface e regenera o
  manifesto em um comando.

### Perfis de execução

- a importação passa a definir qual garantia a rodada entrega, com quatro
  perfis: Prova completa, Cobertura provada, Margem aceita e Exploração rápida;
- o padrão é Prova completa, idêntico ao comportamento anterior;
- a margem é expressa em **ofertas**, não em porcentagem, porque o objetivo da
  primeira fase é uma contagem de ofertas;
- os tetos usam tempo determinístico, preservando a reprodutibilidade entre
  máquinas;
- vocabulário de status ampliado: OPTIMAL, COBERTURA_PROVADA, OTIMO_COM_MARGEM
  e FEASIBLE;
- somente Prova completa pode ser promovida a resultado oficial, e o cenário
  herda o perfil da rodada-base;
- novas opções na CLI dos dois motores: `--perfil`, `--margem-ofertas` e
  `--provar-canonicidade`.

**Medição na base de demonstração.** Depois da correção da canonicalização, os
quatro perfis concluem em tempos praticamente iguais no critério por cluster —
entre 86 e 103 segundos — e todos alcançam OPTIMAL. Os perfis passam a valer
como declaração de garantia e como salvaguarda para bases maiores, e não como
alavanca de desempenho nesta base.

### Canonicalização

- a fase final deixou de remover o objetivo e passou a resolver um desempate
  com ótimo **único**: soma do índice do docente multiplicado por um primo
  próprio de cada oferta;
- o determinismo passou a ser propriedade do modelo, e não da busca: a mesma
  solução é obtida com qualquer número de workers, qualquer semente e em
  qualquer máquina — garantia mais forte que a da versão 1.0, que dependia de
  a fase final rodar com um único worker;
- a fase final voltou a usar todos os workers, o que removeu um gargalo severo:
  no critério por cluster ela não terminava em duas horas e agora conclui em
  segundos;
- nova verificação opcional de canonicidade, registrada em `canonicity_proven`
  com três estados (`true`, `false` e `null` para não pedida ou fora do
  orçamento), com orçamento em tempo determinístico;
- o tempo da verificação passou a integrar o total de CP-SAT do manifesto.

**Efeito sobre as atribuições publicadas.** O novo desempate escolhe um
representante diferente do conjunto de soluções igualmente ótimas. Em uma
rodada de referência do módulo 52, com critério de perfil exato, **todos os
indicadores permaneceram idênticos** — 377 alocadas, 25 pendentes, 222 docentes
utilizados, score 3.353, penalidade de escassez 2 e as mesmas horas por etapa —
mas **236 das 402 ofertas receberam outro docente**.

Rodadas já publicadas continuam válidas e não são reescritas. Porém, reprocessar
um módulo após a atualização produzirá uma distribuição de docentes
substancialmente diferente, sem qualquer mudança de cobertura ou de qualidade.
Quem já comunicou alocações à coordenação deve considerar isso antes de
reprocessar.

### Desempenho medido

Base de demonstração do módulo 52, 402 ofertas e 233 docentes:

| Critério | Antes | Agora |
|---|---|---|
| Perfil exato | 9 s | 8 s |
| Cluster puro | não concluía em 2 h | 98 s |

No critério por cluster a cobertura vai a 402 de 402 ofertas, contra 377 no
perfil exato, com todas as fases provadas ótimas e auditoria aprovada.

### Scripts de operação

- `testar.ps1` e `construir_frontend.ps1` deixaram de falhar no Windows
  PowerShell 5.1: a preferência de erro passou a ser relaxada ao redor de cada
  chamada nativa, porque `unittest` e `npm` escrevem saída de rotina em stderr e
  o interpretador a tratava como erro terminante;
- `construir_frontend.ps1` prefere o Node de `.venv\Scripts` e coloca o
  diretório no PATH durante a compilação — sem isso o `postinstall` do esbuild
  falha, já que ele invoca `node` como comando em um processo filho;
- o PATH é restaurado ao final, com ou sem erro.

### Verificação

- interface compilada com Node.js 22.23.2 e Vite 7.3.6; `tsc --noEmit` sem erro;
- 224 testes Python aprovados: 29 de backend, 86 do motor principal, 93 do motor
  de cenários e 16 dos scripts de release.

## Ferramenta de Alocação Docente 1.0.0

Status: release técnica para produção local mono-usuário em Windows.

Esta versão consolida o motor oficial, a experiência web e o ambiente isolado de simulação.

## Destaques

### Processamento

- seleção explícita de módulo;
- validação antes da otimização;
- pendências em XLSX;
- detalhes de validação em linguagem acionável;
- confirmação de ressalvas;
- estados e mensagens de execução;
- tabela pesquisável de decisões;
- downloads dos artefatos.

### Dashboard

- filtros na ordem ORDEM, DIA, HORÁRIO, CLUSTER e CURSO;
- seleção múltipla com OU interno e E entre dimensões;
- capacidade baseada em CH_LETIVA utilizável em transmissões completas;
- CH ímpar arredondada para baixo, como 9h para 8h;
- deltas por primeira e segunda metade;
- agenda por dia;
- todos os clusters, sem agrupamento em Outros;
- diagnóstico de não alocadas;
- cobertura por etapa.

### Insights

- KPI de alocações com candidato único;
- cobertura de todos os cursos;
- identificação de dias das lacunas;
- horários críticos com cursos e perfis relacionados;
- fila de recuperação por disciplina;
- oportunidades de cobertura, escassez, capacidade e exposição externa;
- metodologia e limitações visíveis.

### Cenários

- motor secundário separado do solver principal;
- baseline obrigatoriamente principal e concluída;
- alterações de capacidade, agenda e perfil;
- busca digitável de ofertas e docentes;
- alocação flexível por cluster;
- proteção de prioridades;
- fixação de decisões;
- comparação baseline versus cenário;
- promoção condicionada a guardrails;
- resultado oficial por módulo.

### Governança

- reset do último item ou de todos;
- reset disponível nas abas de análise;
- exclusão em cascata de cenários dependentes;
- bloqueio de reset durante execução;
- manifesto, hashes e auditoria.

### Experiência

- estados de carregamento consistentes;
- badges de status e contexto;
- textos orientados à ação;
- foco visível, skip link e movimento reduzido;
- layout responsivo;
- frontend compilado servido pela própria API.

## Compatibilidade

- entrada XLSX com MAPA PEDAGÓGICO e DOCENTES;
- módulos 51 a 54;
- execução local em Windows;
- Edge e Chrome como navegadores alvo;
- schema de saída 2 nos motores atuais.

## Limitações conhecidas

- sem autenticação; uso somente em localhost;
- sem valores financeiros reais de RPA/NF;
- sem fonte de Planejado versus Realizado;
- frontend ainda sem suíte automatizada dedicada;
- dependências Python estão travadas com hashes e possuem SBOM transitivo; o pacote não inclui wheelhouse e a instalação inicial requer acesso ao índice configurado do pip;
- SQLite mantém referências de arquivo e requer backup conjunto;
- Ubuntu não é distribuída no pacote atual;
- o release é um ZIP com checksum SHA-256, sem MSI nem assinatura digital;

## Dados de demonstração

Somente exemplos/BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx pode acompanhar esta versão. Resultados anteriores com nomes, chapas ou caminhos locais não pertencem ao pacote. Dados reais são gravados na pasta data da instalação e não acompanham o pacote.

## Gates técnicos desta release

Executados em 16/07/2026:

- testes Python aprovados;
- build frontend aprovado;
- E2E principal e de cenário aprovado;
- backup e restauração íntegros;
- documentação revisada;
- base de demonstração aprovada;
- checksum gerado;
- MANIFESTO_RELEASE.json verificado por scripts/integridade_release.py;
- limitações comunicadas.

Continuam como aprovações externas: validação acadêmica das regras, teste em outra máquina Windows limpa, revisão humana completa de acessibilidade/navegadores e assinatura digital quando exigida pela política corporativa.

## Próximas evoluções candidatas

- autenticação e operação multiusuário;
- trilha de auditoria por usuário;
- valores financeiros de capacidade externa;
- ingestão de realizado;
- testes E2E e acessibilidade automatizados;
- migração versionada do SQLite;
- instalador e atualização assistida;
- políticas adicionais de cenário após validação de negócio.
