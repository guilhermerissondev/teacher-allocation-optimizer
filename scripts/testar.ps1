$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$Python = if (Test-Path -LiteralPath $VenvPython) { $VenvPython } else { (Get-Command python -ErrorAction Stop).Source }
$env:PYTHONDONTWRITEBYTECODE = "1"

function Invoke-CheckedPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    # Com $ErrorActionPreference = "Stop", o Windows PowerShell 5.1 transforma
    # qualquer linha que um executável nativo escreva em stderr num erro
    # terminante. O unittest escreve seu relatório inteiro em stderr, e avisos
    # de depreciação de bibliotecas também. O único sinal confiável de falha é
    # o código de saída, então a preferência é relaxada apenas ao redor da
    # chamada nativa e a verificação fica explícita.
    $anterior = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $Python @Arguments
    }
    finally {
        $ErrorActionPreference = $anterior
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Comando Python falhou com código ${LASTEXITCODE}: $($Arguments -join ' ')"
    }
}

Push-Location (Join-Path $Root "backend")
try { Invoke-CheckedPython -m unittest discover -s tests -p "test_*.py" -v } finally { Pop-Location }

Push-Location (Join-Path $Root "engines\primary")
try { Invoke-CheckedPython -m unittest discover -s tests -p "test_*.py" -v } finally { Pop-Location }

Push-Location (Join-Path $Root "engines\scenarios")
try { Invoke-CheckedPython -m unittest discover -s tests -p "test_*.py" -v } finally { Pop-Location }

Push-Location $Root
try { Invoke-CheckedPython -m unittest discover -s "scripts\tests" -p "test_*.py" -v } finally { Pop-Location }

# A legibilidade da interface e verificavel: qualquer par tinta/superficie
# abaixo de 4.5:1 nos temas claro ou escuro reprova aqui.
Invoke-CheckedPython (Join-Path $Root "scripts\auditar_contraste.py")

Invoke-CheckedPython (Join-Path $Root "executar.py") --verificar
if (Test-Path -LiteralPath (Join-Path $Root "MANIFESTO_RELEASE.json")) {
    Invoke-CheckedPython (Join-Path $Root "scripts\integridade_release.py") --verificar
}
Write-Host "Todas as verificações automatizadas foram concluídas."
