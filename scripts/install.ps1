param([switch]$WithSoundFont)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$environmentPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
Push-Location $projectRoot
try {
    if (-not (Test-Path -LiteralPath $environmentPython)) {
        & py -3.13 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Instale Python 3.13 x64 e tente novamente.' }
    }
    & $environmentPython -c 'import sys; assert sys.version_info[:2] == (3,13), "O lock foi validado com Python 3.13"'
    if ($LASTEXITCODE -ne 0) { throw 'Ambiente existente incompatível; preserve-o e use Python 3.13.' }
    & $environmentPython -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências.' }
    & $environmentPython -m pip install -e . --no-deps
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar o aplicativo.' }
    & $environmentPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Dependências incompatíveis.' }
    & $environmentPython -c 'import PySide6, pyqtgraph, numpy, scipy, sounddevice, spyder_kernels; print("Imports OK")'
    if ($LASTEXITCODE -ne 0) { throw 'Falha na verificação de imports.' }
    if ($WithSoundFont) { & (Join-Path $PSScriptRoot 'install_audio.ps1') }
    Write-Host 'Pronto. Execute .\.venv\Scripts\python.exe -m vocal_app'
} finally {
    Pop-Location
}
