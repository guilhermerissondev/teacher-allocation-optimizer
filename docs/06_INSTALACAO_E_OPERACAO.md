# Instalação e operação

Versão: **2.0.0**.

## Pré-requisitos

A versão de **uso** exige apenas Python 3.12 ou 3.13, 64 bits, estável. O
frontend é distribuído compilado em `frontend/dist`, e as fontes são servidas da
própria pasta: a aplicação não faz nenhuma requisição de rede.

A versão de **desenvolvimento da interface** exige adicionalmente Node.js 20.19+,
22.12+ ou superior. Node não é necessário para executar nem para apresentar.

O `construir_frontend.ps1` procura o Node em duas etapas: primeiro em
`.venv\Scripts`, e só então no PATH do sistema. Quando o ambiente virtual traz
o próprio Node, a compilação usa a cadeia de ferramentas que acompanha a pasta.

Esse Node do `.venv` **não** é recriado pelo `instalar.ps1`: ele não vem do
`requirements.lock`. Em uma máquina nova, instale o Node pelo sistema ou
provisione-o no ambiente virtual antes de compilar a interface.

Depois de alterar qualquer arquivo em `frontend/src`, recompile e atualize o
manifesto com um único comando:

```powershell
.\scripts\construir_frontend.ps1
```

O script valida a versão do Node, roda `npm ci` a partir do `package-lock.json`,
compila com verificação de tipos e regenera o `MANIFESTO_RELEASE.json`. Sem essa
última etapa a verificação de integridade acusa divergência e a aplicação recusa
iniciar.

## Requisitos

Ambiente de desenvolvimento:

- Windows 10 ou 11 de 64 bits;
- Python 3.12 ou 3.13 estável, 64 bits;
- Node.js 20.19 ou superior, ou 22.12 ou superior, somente para compilar o frontend;
- navegador Edge ou Chrome;
- espaço livre para uploads, cópias de fonte e resultados.

Excel não é necessário para o solver, mas é recomendado para abrir os arquivos XLSX.

O launcher aceita somente Python 3.12 ou 3.13 estável, 64 bits. Versões prerelease ou fora dessa faixa são rejeitadas.

## Abertura pelo OPTIMAL.bat

`OPTIMAL.bat` é o atalho recomendado para quem apenas vai usar a aplicação. Antes
de iniciar qualquer coisa ele confere as dependências desta máquina com
`scripts\verificar_dependencias.py`, que compara o interpretador em uso e a lista
inteira do `requirements.lock` — as mesmas travas que o instalador aplica.

- Tudo presente: o lote informa que as dependências já estão instaladas e segue
  direto para a inicialização.
- Falta alguma coisa: o lote diz o que falta e pergunta se deve instalar.
  Respondendo `S`, ele executa `scripts\instalar.ps1`, confere de novo e só então
  inicia; respondendo `N`, ele encerra sem iniciar, porque a aplicação não
  funciona sem as dependências.
- Sem Python homologado: essa é a única dependência que o lote não instala
  sozinho. Ele aponta a origem oficial do download e encerra.

A instalação assistida precisa de conexão com a internet, porque o
`requirements.lock` é aplicado a partir do índice de pacotes.

O verificador também roda sozinho, o que ajuda no diagnóstico:

    .venv\Scripts\python.exe scripts\verificar_dependencias.py

Os códigos de saída são 0 (tudo instalado), 1 (faltam dependências), 2 (Python
não homologado) e 3 (não foi possível verificar).

## Instalação assistida

Na raiz do pacote:

    powershell -ExecutionPolicy Bypass -File scripts\instalar.ps1

O instalador cria .venv, instala as dependências e executa a verificação estrutural do pacote.

## Preparação Python manual

A partir da raiz da versão 2.0:

    python -m venv .venv
    .venv\Scripts\Activate.ps1
    python -m ensurepip --upgrade
    python -m pip install --require-hashes -r requirements.lock

Para uma distribuição oficial, use o arquivo de dependências travado fornecido no pacote, não um ambiente global.

## Build do frontend

    Set-Location frontend
    npm ci
    npm run build
    Set-Location ..

O diretório frontend/dist deve conter index.html e assets. Node.js e node_modules não precisam acompanhar o produto final.

## Diretório de dados

Os dados operacionais reais ficam por padrão na pasta data da instalação, ao lado do OPTIMAL.bat:

    <pasta onde a aplicação foi aberta>\data

O caminho é identificado automaticamente a partir do próprio pacote, portanto copiar a pasta da aplicação leva junto uploads, banco e resultados. A linha "Dados operacionais:" impressa na inicialização mostra o diretório realmente em uso.

Se a pasta da instalação não aceitar escrita (Program Files, unidade de rede protegida), o padrão passa a ser %LOCALAPPDATA%\Institution\AlocacaoDocente\v<versão>.

Defina ALOCACAO_DATA_DIR ou use --dados somente quando precisar de outra pasta gravável e estável.

O diretório conterá planilhas e dados pessoais. Não deve ser sincronizado ou compartilhado automaticamente.

## Inicialização normal

Use:

    OPTIMAL.bat

ou, pulando a verificação de dependências:

    iniciar.cmd

ou:

    .\iniciar.ps1

O launcher verifica o pacote, valida a porta, configura a pasta de dados, inicia Uvicorn sem reload e abre o navegador após o health check.

Para verificar sem iniciar:

    python executar.py --verificar

## Inicialização manual do backend

    Set-Location backend
    python run.py

Abra:

    http://127.0.0.1:8000

Verifique:

    http://127.0.0.1:8000/api/health

Todos os indicadores do health check devem estar disponíveis antes da demonstração.

## Base de demonstração

Use exclusivamente:

    exemplos\BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx

Ela deve permanecer separada dos dados reais gravados no diretório operacional.

## Operação diária

1. Inicie a aplicação.
2. Selecione o módulo.
3. Faça upload da planilha.
4. Analise a validação.
5. Corrija bloqueios ou confirme ressalvas.
6. Execute o motor principal.
7. Aguarde estado terminal.
8. Verifique solver e auditoria.
9. Analise Dashboard e Insights.
10. Crie cenários somente após existir baseline concluída.
11. Encerre a aplicação ao terminar.

## Validação

| Status | Conduta |
|---|---|
| APROVADO | Pode executar |
| APROVADO_COM_RESSALVAS | Ler pendências e confirmar conscientemente |
| REPROVADO | Corrigir a base e reenviar |

Baixe a planilha de pendências para localizar planilha, coluna e linhas afetadas.

## Execução

O motor principal não possui limite de tempo padrão e exige ótimo. Não encerre o computador durante a execução.

Se o servidor for reiniciado, jobs ativos passam a INTERROMPIDA. Inicie uma nova rodada após verificar os arquivos.

## Artefatos de uma rodada

- fonte copiada;
- relatório de validação;
- ocorrências;
- auditoria;
- resultado_alocacao.xlsx;
- resumo_alocacao.json;
- manifesto.json;
- status.json;
- stdout e stderr operacionais no diretório do job.

Antes de compartilhar, confirme:

- resultado CONCLUIDA;
- solver_status OPTIMAL;
- auditoria APROVADO;
- hashes dos artefatos válidos.

## Cenários

Crie nomes que expliquem a hipótese, por exemplo: “Retorno de docentes licenciados” ou “Redistribuição de quarta-feira”.

Execute uma mudança por vez quando quiser medir impacto isolado. Para uma proposta composta, registre a justificativa de cada alteração.

Homologar muda o resultado oficial do módulo para a simulação aprovada. Exporte evidências antes da decisão.

## Reset

Use reset somente quando tiver certeza de que os artefatos não são mais necessários.

- Último remove o item mais recente do escopo.
- Todos remove todo o histórico daquele escopo.
- Rodada-base remove cenários dependentes.
- Operação ativa bloqueia o reset.

Faça backup antes de excluir uma rodada usada em decisão.

## Backup

Com a aplicação encerrada, gere um ZIP íntegro do banco e dos arquivos vinculados:

    python scripts\backup_restore.py backup `
      --dados ".\data" `
      --saida "D:\Backups\alocacao-docente-2.0.0.zip"

O comando recusa uma aplicação ativa, valida o SQLite, registra versão e SHA-256 e publica o ZIP somente ao final. Não copie apenas o SQLite: ele contém referências aos arquivos das rodadas.

## Restauração

1. encerre a aplicação;
2. escolha um diretório de destino inexistente ou vazio;
3. execute:

       python scripts\backup_restore.py restore `
         --arquivo "D:\Backups\alocacao-docente-2.0.0.zip" `
         --dados "D:\AlocacaoDocente\dados-restaurados"

4. inicie a aplicação apontando `ALOCACAO_DATA_DIR` para o destino;
5. verifique `/api/health`;
6. abra a rodada oficial, o cenário homologado e baixe um artefato.

## Encerramento

Encerre pelo launcher ou pelo terminal que iniciou o servidor. Evite finalizar processos do solver isoladamente.

## Release Windows

O pacote de apresentação deve:

- incluir frontend/dist;
- iniciar sem reload;
- usar 127.0.0.1;
- configurar diretório de dados fora da pasta do programa;
- verificar a porta 8000;
- aguardar o health check;
- abrir o navegador;
- manter logs locais;
- impedir duas instâncias;
- incluir dependências, licenças e checksum.

Enquanto os motores forem chamados como scripts por um interpretador, um único executável PyInstaller não é suficiente. Use runtime Python controlado ou executáveis separados para servidor e motores.

## Integridade do release

Gerar o manifesto após fechar o conteúdo:

    python scripts\integridade_release.py --gerar

Verificar antes de compartilhar:

    python scripts\integridade_release.py --verificar

Gerar o ZIP determinístico e o checksum:

    python scripts\empacotar_release.py

O arquivo MANIFESTO_RELEASE.json registra versão, tamanho e SHA-256 dos arquivos distribuíveis. Dados operacionais, caches e o próprio manifesto são excluídos da soma.
