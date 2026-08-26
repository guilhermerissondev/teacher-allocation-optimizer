$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Frontend = Join-Path $Root "frontend"
$LockFile = Join-Path $Frontend "package-lock.json"

function Assert-NativeSuccess {
    param([Parameter(Mandatory = $true)][string]$Action)
    if ($LASTEXITCODE -ne 0) {
        throw "$Action falhou com código $LASTEXITCODE."
    }
}

function Invoke-Native {
    <#
        Com $ErrorActionPreference = "Stop", o Windows PowerShell 5.1 trata
        qualquer linha que um executável nativo escreva em stderr como erro
        terminante. O npm escreve avisos ali de rotina — cobertura de scripts
        de instalação, auditoria, versão nova disponível — e o script morria
        com a instalação bem-sucedida. O único sinal confiável de falha é o
        código de saída, então a preferência é relaxada ao redor da chamada e
        a verificação fica explícita.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Caminho,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Argumentos
    )
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Caminho @Argumentos } finally { $ErrorActionPreference = $anterior }
}

if (-not (Test-Path -LiteralPath $LockFile)) {
    throw "Arquivo de dependências travadas ausente: $LockFile"
}

# O Node de dentro do .venv tem precedência: quando ele existe, a compilação
# usa a mesma cadeia de ferramentas que acompanha a pasta, sem depender do que
# estiver instalado na máquina. Se não existir, cai para o Node do sistema.
$NodeLocal = Join-Path $Root ".venv\Scripts\node.exe"
$NpmLocal = Join-Path $Root ".venv\Scripts\npm.cmd"
if ((Test-Path -LiteralPath $NodeLocal) -and (Test-Path -LiteralPath $NpmLocal)) {
    $NodePath = $NodeLocal
    $NpmPath = $NpmLocal
    $Origem = "do .venv do projeto"
}
else {
    $Node = Get-Command node -ErrorAction SilentlyContinue
    if (-not $Node) {
        throw "Node.js não encontrado. Instale a versão 20.19+, 22.12+ ou superior e execute novamente. O Node é necessário apenas para desenvolver a interface; a versão de apresentação roda somente com Python."
    }
    $Npm = Get-Command npm -ErrorAction SilentlyContinue
    if (-not $Npm) {
        throw "npm não encontrado no PATH, ainda que o Node esteja instalado."
    }
    $NodePath = $Node.Source
    $NpmPath = $Npm.Source
    $Origem = "do sistema"
}

$Version = (& $NodePath --version).TrimStart("v")
$Parts = $Version.Split(".")
$Major = [int]$Parts[0]
$Minor = [int]$Parts[1]
$Supported = ($Major -eq 20 -and $Minor -ge 19) -or ($Major -eq 22 -and $Minor -ge 12) -or ($Major -gt 22)
if (-not $Supported) {
    throw "Node.js $Version não é homologado. Use 20.19+, 22.12+ ou superior."
}
Write-Host "Node.js $Version $Origem."

# Chamar o node por caminho absoluto não basta: o npm dispara scripts de
# instalação em processos filhos que invocam `node` como comando — o postinstall
# do esbuild é um deles, e é ele que baixa o binário da plataforma. Sem o
# diretório no PATH, `npm ci` falha com "node não é reconhecido".
$PathAnterior = $env:PATH
$env:PATH = (Split-Path -Parent $NodePath) + ";" + $env:PATH

Push-Location $Frontend
try {
    # `npm ci` respeita o package-lock.json e recria node_modules do zero,
    # garantindo que o build seja reprodutível a partir da própria pasta.
    Invoke-Native $NpmPath ci
    Assert-NativeSuccess "Instalação das dependências da interface"

    # O script `build` roda `tsc --noEmit` antes do Vite: erro de tipo
    # interrompe aqui, e não silenciosamente no bundle publicado.
    Invoke-Native $NpmPath run build
    Assert-NativeSuccess "Compilação da interface"
}
finally {
    Pop-Location
    $env:PATH = $PathAnterior
}

$Dist = Join-Path $Frontend "dist\index.html"
if (-not (Test-Path -LiteralPath $Dist)) {
    throw "A compilação terminou sem gerar frontend\dist\index.html."
}

# O dist fica fora do manifesto, mas a regeração continua aqui porque o build
# pode ter atualizado arquivos de origem rastreados; verificar em seguida
# garante que a aplicação inicia logo após compilar.
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { (Get-Command python -ErrorAction Stop).Source }
Invoke-Native $Python (Join-Path $Root "scripts\integridade_release.py") --gerar
Assert-NativeSuccess "Geração do manifesto de release"

Invoke-Native $Python (Join-Path $Root "scripts\integridade_release.py") --verificar
Assert-NativeSuccess "Verificação do manifesto de release"

Write-Host "Interface compilada e manifesto atualizado. Use iniciar.ps1 para abrir a aplicação."
