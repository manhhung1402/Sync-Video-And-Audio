$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$specFile = Join-Path $PSScriptRoot "SyncVideo-Audio-full.spec"
$distRoot = Join-Path $projectRoot "dist-full"
$workRoot = Join-Path $projectRoot "build\pyinstaller-full"

Push-Location $PSScriptRoot
try {
    python -m PyInstaller --noconfirm --clean $specFile `
        --distpath $distRoot `
        --workpath $workRoot
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller thất bại với exit code $LASTEXITCODE."
    }
} finally {
    Pop-Location
}

$appExe = Join-Path $distRoot "SyncVideo-Audio\SyncVideo-Audio.exe"
Write-Host "Đã build payload full: $appExe"

$iscc = Get-Command iscc -ErrorAction SilentlyContinue
if (-not $iscc) {
    $localIsccPath = Join-Path $projectRoot "tools\InnoSetup\ISCC.exe"
    if (Test-Path -LiteralPath $localIsccPath) {
        $iscc = Get-Item -LiteralPath $localIsccPath
    }
}
if ($iscc) {
    $isccCommand = if ($iscc.PSObject.Properties.Name -contains "Source") { $iscc.Source } else { $iscc.FullName }
    & $isccCommand (Join-Path $PSScriptRoot "SyncVideo-Audio.iss")
    if ($LASTEXITCODE -ne 0) {
        throw "Inno Setup thất bại với exit code $LASTEXITCODE."
    }
    Write-Host "Đã build installer trong dist-installer."
} else {
    Write-Warning "Chưa có Inno Setup (iscc); payload full đã sẵn sàng, installer sẽ được build khi iscc được cài."
}
