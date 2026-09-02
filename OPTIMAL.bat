@echo off
setlocal EnableExtensions
rem A versao vem do arquivo VERSION para o banner nunca divergir do pacote.
set "RAIZ=%~dp0"
set "VERSAO=?"
if exist "%RAIZ%VERSION" set /p VERSAO=<"%RAIZ%VERSION"
set "VENV_PYTHON=%RAIZ%.venv\Scripts\python.exe"
set "VERIFICADOR=%RAIZ%scripts\verificar_dependencias.py"
set "INSTALADOR=%RAIZ%scripts\instalar.ps1"
set "CONSTRUTOR=%RAIZ%scripts\construir_frontend.ps1"
title OPTIMAL - Ferramenta de Alocacao Docente v%VERSAO%
echo.
echo   ============================================
echo       OPTIMAL - Alocacao Docente v%VERSAO%
echo   ============================================
echo.
echo   Verificando as dependencias necessarias...
echo.

if not exist "%VERIFICADOR%" goto :verificador_ausente
if not exist "%VENV_PYTHON%" goto :ambiente_ausente

rem O verificador confere o interpretador do .venv e a lista travada em
rem requirements.lock, que e a mesma que o instalador aplica.
"%VENV_PYTHON%" "%VERIFICADOR%"
if errorlevel 3 goto :falha_verificacao
if errorlevel 2 goto :ambiente_incompativel
if errorlevel 1 goto :oferecer_instalacao

echo.
echo   [OK] Todas as dependencias necessarias ja estao instaladas nesta maquina.
goto :iniciar

rem Sem .venv nao ha interpretador validado ainda: o instalador precisa de um
rem Python homologado do sistema para criar o ambiente. Quando o .venv existe, o
rem proprio verificador ja confirmou que o interpretador serve.
:ambiente_ausente
echo   [X] O ambiente com as dependencias (.venv) ainda nao existe nesta maquina.
call :detectar_python
if not defined PYTHON_HOMOLOGADO goto :python_ausente

:oferecer_instalacao
echo.
echo   A aplicacao nao funciona corretamente sem essas dependencias.
echo   A instalacao usa o Python ja presente na maquina, leva alguns minutos
echo   e precisa de conexao com a internet.
echo.
call :perguntar_instalacao
if not defined RESPOSTA_SIM goto :instalacao_recusada

echo.
echo   Instalando as dependencias. Aguarde...
echo.
if not exist "%INSTALADOR%" goto :instalador_ausente
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%INSTALADOR%"
if errorlevel 1 goto :falha_instalacao
if not exist "%VENV_PYTHON%" goto :falha_instalacao
echo.
echo   Conferindo novamente as dependencias...
echo.
"%VENV_PYTHON%" "%VERIFICADOR%"
if errorlevel 1 goto :falha_instalacao
echo.
echo   [OK] Dependencias instaladas com sucesso.
goto :iniciar

:iniciar
rem Um clone do repositorio nao traz frontend\dist: ele e artefato de
rem build e fica fora do controle de versao. Sem ele o executar.py aborta com
rem "Pacote incompleto", mensagem que nao diz o que fazer. A interface e
rem compilada aqui na primeira execucao; o construtor tambem regera o manifesto
rem de integridade, sem o que a verificacao acusaria divergencia em seguida.
if exist "%RAIZ%frontend\dist\index.html" goto :executar
echo.
echo   A interface ainda nao foi compilada nesta copia. Isso acontece ao
echo   clonar o repositorio, porque o resultado da compilacao nao e versionado.
echo   Compilando agora. Leva alguns minutos e precisa de conexao.
echo.
if not exist "%CONSTRUTOR%" goto :construtor_ausente
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CONSTRUTOR%"
if errorlevel 1 goto :falha_construcao
if not exist "%RAIZ%frontend\dist\index.html" goto :falha_construcao
echo.
echo   [OK] Interface compilada.

:executar
echo.
echo   Iniciando a aplicacao...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%RAIZ%iniciar.ps1" %*
set "CODIGO=%ERRORLEVEL%"
if not "%CODIGO%"=="0" goto :falha_execucao
exit /b 0

:falha_execucao
echo.
echo   [ERRO] A aplicacao encerrou com codigo %CODIGO%.
echo   Consulte docs\09_TROUBLESHOOTING.md para solucoes.
echo.
pause
exit /b %CODIGO%

:instalacao_recusada
echo.
echo   Instalacao cancelada. A aplicacao nao sera iniciada porque as
echo   dependencias necessarias nao estao presentes nesta maquina.
echo   Execute o OPTIMAL.bat novamente quando quiser instala-las.
echo.
pause
exit /b 1

:python_ausente
echo.
echo   [X] Python 64 bits estavel 3.12 ou 3.13 nao foi encontrado nesta maquina.
echo   Essa e a unica dependencia que este arquivo nao consegue instalar sozinho.
echo   Baixe em https://www.python.org/downloads/windows/ , marque a opcao
echo   "Add python.exe to PATH" e execute o OPTIMAL.bat novamente.
echo.
pause
exit /b 1

:ambiente_incompativel
echo.
echo   [X] O ambiente .venv desta pasta nao usa Python 64 bits estavel 3.12 ou 3.13.
echo   Apague a pasta .venv e execute o OPTIMAL.bat novamente para recria-la.
echo.
pause
exit /b 1

:falha_instalacao
echo.
echo   [ERRO] Nao foi possivel concluir a instalacao das dependencias.
echo   Confira as mensagens acima e a conexao com a internet, ou execute
echo   scripts\instalar.ps1 manualmente. Solucoes em docs\09_TROUBLESHOOTING.md.
echo.
pause
exit /b 1

:falha_verificacao
echo.
echo   [ERRO] Nao foi possivel verificar as dependencias desta maquina.
echo   Consulte docs\09_TROUBLESHOOTING.md para solucoes.
echo.
pause
exit /b 1

:verificador_ausente
echo   [ERRO] Arquivo scripts\verificar_dependencias.py nao encontrado.
echo   O pacote esta incompleto: obtenha novamente a versao completa do OPTIMAL.
echo.
pause
exit /b 1

:falha_construcao
echo.
echo   [ERRO] Nao foi possivel compilar a interface.
echo   A compilacao precisa do Node.js 20.19+, 22.12+ ou superior. Ele serve
echo   apenas para gerar a interface a partir do codigo-fonte: o pacote de
echo   distribuicao ja vem compilado e roda somente com Python.
echo   Baixe em https://nodejs.org/ e execute o OPTIMAL.bat novamente, ou rode
echo   scripts\construir_frontend.ps1 para ver a mensagem completa.
echo.
pause
exit /b 1

:construtor_ausente
echo   [ERRO] Arquivo scripts\construir_frontend.ps1 nao encontrado.
echo   O pacote esta incompleto: obtenha novamente a versao completa do OPTIMAL.
echo.
pause
exit /b 1

:instalador_ausente
echo   [ERRO] Arquivo scripts\instalar.ps1 nao encontrado.
echo   O pacote esta incompleto: obtenha novamente a versao completa do OPTIMAL.
echo.
pause
exit /b 1

rem ---------------------------------------------------------------------------
rem Sub-rotinas
rem ---------------------------------------------------------------------------

:detectar_python
rem Procura fora do .venv um interpretador homologado que o instalador possa usar.
set "PYTHON_HOMOLOGADO="
where py >nul 2>&1
if errorlevel 1 goto :detectar_python_no_path
py -3.13 "%VERIFICADOR%" --somente-interpretador --silencioso >nul 2>&1
if not errorlevel 1 set "PYTHON_HOMOLOGADO=py -3.13"
if defined PYTHON_HOMOLOGADO goto :eof
py -3.12 "%VERIFICADOR%" --somente-interpretador --silencioso >nul 2>&1
if not errorlevel 1 set "PYTHON_HOMOLOGADO=py -3.12"
if defined PYTHON_HOMOLOGADO goto :eof

:detectar_python_no_path
where python >nul 2>&1
if errorlevel 1 goto :eof
python "%VERIFICADOR%" --somente-interpretador --silencioso >nul 2>&1
if not errorlevel 1 set "PYTHON_HOMOLOGADO=python"
goto :eof

:perguntar_instalacao
rem Define RESPOSTA_SIM somente quando o usuario aceita instalar. O choice.exe e
rem o set /p descartam espacos a esquerda da mensagem, por isso a pergunta sai
rem num echo indentado e so a linha da resposta fica na coluna zero.
set "RESPOSTA_SIM="
echo   Deseja instalar as dependencias agora?
where choice >nul 2>&1
if errorlevel 1 goto :perguntar_sem_choice
choice /C SN /N /M "Digite S para instalar ou N para cancelar: "
if errorlevel 2 goto :eof
set "RESPOSTA_SIM=1"
goto :eof

:perguntar_sem_choice
set "RESPOSTA="
set /p "RESPOSTA=Digite S para instalar ou N para cancelar: "
if /i "%RESPOSTA%"=="s" set "RESPOSTA_SIM=1"
if /i "%RESPOSTA%"=="sim" set "RESPOSTA_SIM=1"
goto :eof
