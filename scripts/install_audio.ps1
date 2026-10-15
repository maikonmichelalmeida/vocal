# Optional local guide. Sources and licenses: docs/audio.md. No global installation.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeDirectory = Join-Path $projectRoot 'runtime'
$bankDirectory = Join-Path $projectRoot 'soundfonts'
New-Item -ItemType Directory -Force $runtimeDirectory, $bankDirectory | Out-Null
$archive = Join-Path $runtimeDirectory 'fluidsynth.zip'
$bank = Join-Path $bankDirectory 'GeneralUser-GS.sf2'
$revision = '684543d5e5efaef08d02be50dcda8d552478fa60'
function Get-VerifiedFile($Url, $Path, $Sha256) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Invoke-WebRequest -Uri $Url -OutFile $Path
    }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Sha256) {
        throw "SHA256 inesperado: $Path. Arquivo preservado para inspeção."
    }
}
Get-VerifiedFile 'https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.1/fluidsynth-v2.6.1-win10-x64-cpp11.zip' $archive 'fab7a2e4b85675b66970f97a39bbc239729c5e0f237198b5922a6a73cbc8677c'
Get-VerifiedFile "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$revision/GeneralUser-GS.sf2" $bank '9575028c7a1f589f5770fccc8cff2734566af40cd26ed836944e9a5152688cfe'
Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $runtimeDirectory 'fluidsynth') -Force
Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/FluidSynth/fluidsynth/v2.6.1/LICENSE' -OutFile (Join-Path $runtimeDirectory 'fluidsynth\LICENSE-FluidSynth.txt')
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/mrbumpy409/GeneralUser-GS/$revision/documentation/LICENSE.txt" -OutFile (Join-Path $bankDirectory 'LICENSE-GeneralUser-GS.txt')
Set-Content -LiteralPath (Join-Path $bankDirectory 'SOURCE_REVISION.txt') -Value $revision -Encoding utf8
Write-Host 'Guia local instalado: FluidSynth 2.6.1 e GeneralUser GS. Licenças preservadas.'
