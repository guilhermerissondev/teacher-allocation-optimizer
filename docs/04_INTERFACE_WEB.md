# Interface web

## Princípios

A interface organiza a decisão em uma sequência única:

    Processar → Entender → Diagnosticar → Simular

Ela usa linguagem de negócio, mantém estados de carregamento e erro visíveis e evita que o usuário precise acessar arquivos técnicos para interpretar a rodada.

## Navegação

O menu superior contém:

1. Processamento;
2. Dashboard;
3. Insights;
4. Cenários.

A rota é mantida no fragmento da URL, permitindo atualizar a página sem exigir configuração especial no servidor.

## Casca da aplicação

A navegação fica em um trilho lateral fixo, com o logotipo, os cinco módulos, o
alternador de tema e os créditos. Abaixo de 900 px de largura o trilho vira uma
faixa superior rolável.

### Tema

O alternador oferece Claro, Escuro e Auto. Em Auto nenhum atributo é gravado e
apenas `prefers-color-scheme` decide; nas outras opções a escolha é carimbada em
`data-theme` no elemento raiz e persistida em `localStorage`. Toda cor da
interface vem de tokens definidos na paleta clara completa e redefinidos nos dois
blocos de tema escuro, de modo que nenhuma cor exista somente dentro de um bloco
de tema.

### Tipografia

Sora nos títulos, Source Sans 3 no texto corrido e IBM Plex Mono nos dados —
chapas, códigos, versões, critérios e hashes. Os arquivos ficam em
`frontend/src/assets/fonts` e são carregados localmente.

## Processamento

### Rodada única ou lote

A tela de Processamento abre em **Rodada única**, que é o fluxo de sempre: uma
planilha, um módulo, uma rodada. A chave **Lote de módulos** troca o painel
para o envio de várias planilhas — ou de uma planilha anual.

Os dois modos seguem os mesmos quatro passos, com os mesmos controles: arquivo
de entrada, resultado da validação, acompanhamento e resultado. O que muda é
que cada passo do lote mostra uma linha por módulo em vez de uma só.

**Passo 1.** A aplicação lê a coluna `MÓD` de cada arquivo e mostra o que
encontrou antes de qualquer decisão: quantos módulos, quantas linhas cada um e
quais estão fora do intervalo 51–54. O operador marca os módulos a processar e
escolhe critério e perfil de execução uma vez para o lote inteiro — as mesmas
duas perguntas da rodada única, com as mesmas explicações.

**Passo 2.** Cada módulo aparece com o seu status de validação, quantas ofertas
alocáveis tem e quantas ocorrências foram encontradas. As ocorrências de um
módulo abrem na própria linha, e a planilha de pendências daquele módulo fica
disponível ali. Quando há ressalvas, a confirmação é pedida **depois** de elas
serem exibidas, como na rodada única — nunca antes.

**Passo 3.** As rodadas correm em série. Cada módulo tem o seu cartão com as
cinco etapas do motor, a mensagem corrente e, ao concluir, os indicadores e os
artefatos daquela rodada.

**Resultado.** Um consolidado soma a cobertura dos módulos do lote. Ele é um
apoio de leitura: cada módulo continua sendo uma rodada independente, e a
referência oficial é a rodada de cada módulo, não o consolidado.

### Seleção de módulo

A tela inicia com Selecione o Módulo. Nenhum módulo deve ser presumido visualmente. As opções são 51, 52, 53 e 54.

### As duas decisões da importação

Módulo, critério e perfil formam o contrato da rodada. Critério e perfil não são
listas suspensas: as alternativas ficam visíveis lado a lado, como cartões de
opção, cada uma com o resumo do que entrega.

A escolha foi deliberada. Esconder as alternativas atrás de uma lista obrigaria
quem decide a abrir, ler e fechar para comparar — e são decisões que mudam o
resultado. O controle é um radio nativo, então navegação por setas e leitura por
leitor de tela funcionam sem código adicional.

Cartões marcados como **padrão** reproduzem o comportamento das versões
anteriores. O perfil Prova completa é marcado como **homologável**, porque é o
único que pode virar o resultado oficial do módulo.

### Seleção do critério de elegibilidade

Sob a pergunta **Quem pode assumir cada disciplina?**, três opções:

| Opção | Efeito |
|---|---|
| Perfil da disciplina | candidatura restrita à interseção exata de perfil |
| Cluster com perfil preferencial | candidatura pelos perfis do cluster, preferindo o perfil exato nos empates |
| Cluster puro | candidatura pelos perfis do cluster, sem preferência por perfil exato |

O padrão é Perfil da disciplina, que reproduz o comportamento da versão 1.0.
Trocar o critério limpa a validação já realizada, porque o relatório de
pendências depende do método escolhido.

O critério aparece no rótulo de toda rodada nas listas de seleção e como selo no
Dashboard. Rodadas de critérios diferentes não são comparáveis entre si.

### Seleção do perfil de execução

Sob a pergunta **Quanta prova a rodada precisa entregar?**, os quatro perfis.
Cada cartão diz o que a rodada prova e se ela pode ser homologada. Quando o
perfil é Margem aceita, aparece um campo adicional para a folga em ofertas.

Os três controles formam o contrato da rodada: módulo, critério e perfil. Todos
os três entram no rótulo de cada rodada nas listas de seleção e aparecem como
selo no Dashboard, porque rodadas com contratos diferentes não são comparáveis.

### Upload e validação

O usuário:

1. seleciona o módulo;
2. seleciona o critério de elegibilidade;
3. seleciona o perfil de execução;
3. envia um XLSX;
4. recebe o resultado da validação;
5. baixa pendencias_validacao.xlsx quando precisa corrigir a base;
6. confirma ressalvas quando aplicável;
7. inicia a alocação.

A coluna DETALHES da planilha de pendências deve apresentar explicação humana e acionável, não estruturas JSON ou nomes internos de programação.

### Acompanhamento

O frontend consulta periodicamente o job enquanto ele não é terminal. A tela apresenta:

- estado atual;
- mensagem;
- histórico das fases;
- resumo da solução;
- artefatos para download;
- tabela paginada de alocações;
- busca por disciplina, docente ou chapa.

### Rodadas

O histórico permite escolher uma rodada. Zerar rodadas-base oferece:

- somente o último;
- zerar todos;
- cancelar.

Cenários dependentes também são removidos e isso deve ser informado antes da confirmação.

### Seleção de alvos

Cada movimento de dados — capacidade, agenda e compatibilidade — usa um só
formulário. Não há modo individual separado do modo em lote: o alvo é sempre uma
lista suspensa com marcação múltipla, e escolher um registro ou doze muda apenas
o rótulo do botão. Com um único alvo, o painel de contexto da rodada-base
continua visível e o aviso de premissa inócua aparece antes do envio.

Os filtros vêm da própria rodada-base e também são listas suspensas: CH letiva,
cargo, status e gestor para docentes; cluster, curso, dia, ordem e situação na
base para ofertas. Dentro do mesmo filtro as escolhas somam; entre filtros
diferentes, restringem — a mesma regra dos filtros do Dashboard.

Os filtros conversam entre si: cada um oferece apenas os valores que ainda
existem depois dos outros. Escolher CH letiva de 0h deixa em Cargo somente os
cargos que têm alguém nessa faixa, e cada opção mostra quantos registros traz.
Uma escolha que deixa de existir sai da seleção, para o resultado nunca ficar em
zero sem explicação.

Com os filtros aplicados, **Selecionar os N filtrados** marca de uma vez tudo
que sobrou. O contador mostra quantos estão selecionados, quantos a lista
exibe e quantos existem no total.

Para `CH_LETIVA` há duas formas de aplicar: definir o mesmo valor para todos ou
ajustar em horas, somando ou subtraindo a partir da carga de cada docente. O
ajuste preserva as diferenças entre eles, que é o que se espera de um reforço
ou de um corte de capacidade.

Depois de aplicar, a tela informa quantas premissas entraram e lista, com o
motivo, as que ficaram de fora — linha que já estava no valor pedido, carga que
ficaria negativa ou CH acima da contratada.


## Dashboard

O Dashboard é recalculado a partir da planilha de resultado e do manifesto da rodada escolhida.

### Filtros

A ordem é ORDEM, DIA, HORÁRIO, CLUSTER e CURSO.

- múltiplos valores na mesma dimensão usam OU;
- dimensões diferentes usam E;
- Limpar filtros volta ao recorte completo;
- opções extensas possuem busca;
- o total de ofertas do recorte deve permanecer visível.

### KPIs

O contrato atual inclui:

- cobertura percentual;
- ofertas alocadas e total;
- não alocadas;
- uso de docentes;
- docentes ativos, usados e sem alocação;
- quantidade por 1ª, 2ª e ESTENDIDA;
- demanda da primeira e da segunda etapa;
- delta demanda menos capacidade por etapa;
- capacidade letiva ativa utilizável.

Delta positivo indica déficit bruto. A nota metodológica precisa permanecer próxima do KPI.

### Gráficos

**Disciplinas e professores por dia:** barras lado a lado com valores explícitos.

**Horas demandadas por cluster:** barras horizontais ranqueadas com valor e participação de todos os clusters. Não há categoria Outros.

**Diagnósticos complementares:** motivos de não alocação, horas por etapa e demais cartões devem conservar unidade e fonte.

## Insights

Insights aprofunda a interpretação da rodada sem modificar os dados.

### Indicadores

Os KPIs de destaque são:

- cobertura;
- cursos abaixo de 90%;
- disciplinas sem cobertura;
- horas de demanda não alocada;
- alocações de candidato único;
- horas em RPA/NF como proxy.

Estatísticas adicionais de capacidade, concentração, utilização, risco, outliers e Pareto sustentam oportunidades e diagnósticos do serviço, mesmo quando não aparecem como cartões principais.

### Cobertura por curso e disciplina

O gráfico de cursos deve mostrar todos os cursos, não apenas um top 12. Para cada curso, exibe alocadas e não alocadas, com identificação dos dias associados às lacunas.

O gráfico de horários mais críticos complementa essa leitura e inclui:

- dia e horário;
- quantidade de lacunas;
- cursos afetados;
- curso mais recorrente;
- perfil mais recorrente.

### Diagnósticos

A tela apresenta:

- distribuição de carga docente;
- risco docente;
- composição por cluster, dia, coordenação e contrato;
- motivos das lacunas;
- oportunidades priorizadas;
- insights automáticos;
- metodologia e limitações.

Os cartões de oportunidade tiram a urgência dos números da rodada, não do assunto
do cartão, e a cor acompanha a severidade apurada: `crítica`, `alta`, `média`,
`monitorar` e `resolvido`. Um indicador zerado fica verde e diz que não há ação
pendente, em vez de repetir a orientação de um problema que não existe.

O mesmo número pode mudar de significado: docentes ativos sem alocação são
`alta` quando ainda há lacuna aberta — a capacidade existe e não encaixou — e
`monitorar` quando a cobertura já está completa.

Horas externas não devem ser apresentadas como custo monetário; qualquer hora
acima de zero entra como `média`, para pedir atenção sem competir com lacuna de
cobertura.

## Cenários

### Passos visuais

1. escolher rodada-base;
2. criar cenário com nome e objetivo;
3. escolher movimento;
4. configurar alterações ou políticas;
5. executar simulação;
6. comparar;
7. homologar, se elegível.

### Busca

Seletores extensos de ofertas e docentes possuem campo digitável. A busca por oferta considera disciplina, código, curso e linha; a busca por docente considera nome, chapa, função, status e perfil.

### Movimentos

- Reforçar ou reduzir capacidade;
- Reorganizar agenda;
- Ampliar compatibilidade;
- Alocar docentes do cluster;
- Proteger prioridades acadêmicas;
- Fixar decisões.

### Comparação

A comparação deve deixar claro:

- baseline;
- cenário;
- variação absoluta e percentual;
- ofertas alteradas;
- guardrails de validação, solver e auditoria;
- elegibilidade para homologação.

### Resets

A aba possui controles separados para rodadas-base e cenários salvos. Cada controle oferece último, todos ou cancelar.

### Estudo em lote

A aba abre com um seletor de modo. **Cenário de um módulo** é o padrão e mantém
o fluxo descrito acima. **Estudo em lote** repete a mesma pergunta ao longo dos
módulos do ano.

Passos visuais:

1. escolher o lote-base e os módulos, com atalhos "a partir do 51", "a partir do
   52" e "ano inteiro";
2. nomear o estudo e a pergunta que ele responde;
3. escolher o movimento e os alvos na janela de seleção;
4. conferir a matriz de premissas × módulos;
5. simular todos os módulos aptos;
6. comparar o consolidado do ano e cada módulo;
7. homologar módulo a módulo, quando elegível.

#### Janela de seleção

O alvo é escolhido no mesmo tipo de janela do cenário de um módulo: filtros em
lista suspensa, contagem por valor, seleção múltipla e "selecionar os filtrados".
Dentro de um filtro as escolhas são OU, entre filtros são E, e cada filtro
oferece apenas o que ainda existe depois dos outros.

O que muda são os filtros, porque o alvo é outro:

- **Docente** — CH letiva, cargo, status e gestor, como no cenário de um módulo.
- **Curso ou disciplina** — em que módulos o alvo existe, situação na base (com
  lacuna ou totalmente alocado), dia praticado e, para disciplinas, o curso.

O filtro "com lacuna na base" é o que responde diretamente a "qual curso vive com
disciplina sem docente": ele reduz a lista aos alvos que a rodada oficial não
conseguiu cobrir.

Vários alvos podem ser escolhidos de uma vez, e cada um vira uma premissa.

#### Reorganizar agenda

O movimento aceita dois alvos: **curso inteiro** ou **disciplina específica**. Os
valores oferecidos para dia, horário e ordem são apenas os praticados no ano, com
a contagem de ofertas em cada um — sugerir um horário que a operação não usa não
ajuda a decidir.

#### Matriz de premissas

Cada linha é uma premissa e cada coluna é um módulo. A célula informa quantas
linhas da planilha daquele módulo a premissa alcançou, ou "sem efeito" com o
motivo no rótulo. É a tela que revela, antes de gastar uma simulação por módulo,
onde a premissa não encosta em nada — o docente não está naquele módulo, o valor
já é o praticado ou a CH passaria do teto contratado.

Um módulo sem alteração projetada não vai para a fila, e a tela diz quais são
antes da execução.

#### Execução e comparação

As simulações rodam em série no motor secundário: um estudo de quatro módulos
leva cerca de quatro vezes o tempo de um cenário único, e a tela avisa disso
antes do clique.

A comparação tem duas camadas: os deltas consolidados do ano — cobertura,
ofertas alocadas, ofertas sem alocação e docentes utilizados — e uma linha por
módulo, expansível para as ofertas recuperadas, perdidas e remanejadas.

#### Resultado desatualizado

Quando as premissas mudam, o módulo já simulado passa a exibir "premissas
mudaram · resultado desatualizado" no lugar do estado, e a cobertura simulada
some. O número antigo não pode ficar ao lado da premissa nova.

#### Homologação

Cada módulo é homologado separadamente, com os mesmos guardrails do cenário
único. Um módulo reprovado não bloqueia os demais, e o motivo do bloqueio
aparece na própria linha.

## Estados e mensagens

Estados mínimos:

- vazio;
- carregando;
- sucesso;
- atenção;
- erro recuperável;
- erro terminal;
- ação desabilitada com justificativa.

Mensagens devem dizer o que aconteceu e qual ação o usuário pode tomar. Códigos internos podem aparecer em documentação técnica, mas não como explicação principal.

## Acessibilidade

O frontend atual inclui:

- link para pular ao conteúdo;
- foco visível;
- labels em campos;
- texto oculto para leitores de tela;
- navegação por teclado em elementos nativos;
- redução de animações conforme preferência do sistema;
- layouts responsivos.

Antes de cada release, validar teclado completo, zoom de 200%, contraste, leitura das legendas, tabelas em tela estreita e anúncio de erros.

## Identidade visual

A paleta usa azul institucional, verde para resultado saudável, âmbar para atenção, vermelho para risco e cinza para estado neutro.

Ubuntu é a primeira fonte declarada, com Segoe UI como fallback. Se Ubuntu não for distribuída, a apresentação no Windows usará a fonte disponível no sistema.
